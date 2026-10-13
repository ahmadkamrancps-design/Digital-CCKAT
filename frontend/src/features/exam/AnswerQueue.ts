import { ApiError } from '../../services/api';
import type { Answer, AnswerFields, AnswerSaved, AnswerWrite } from '../../types/attempt';
import type { RecoveryCell, RecoveryJournal } from '../../storage/recovery';

export interface AnswerCell {
  confirmed: Answer;
  draft: AnswerFields;
  error?: string;
  conflict?: Answer;
  /** Keep the exact unacknowledged request for safe retries after an ambiguous network failure. */
  request?: AnswerWrite;
  retryable?: boolean;
}
export interface AnswerSnapshot {
  cells: Record<string, AnswerCell>;
  saving: boolean;
  localSaving: boolean;
  localError: string | null;
  online: boolean;
  restored: boolean;
}
const fields = (answer: AnswerFields): AnswerFields => ({
  selected_option_id: answer.selected_option_id,
  short_answer_text: answer.short_answer_text,
  is_marked_for_review: answer.is_marked_for_review,
});
const same = (a: AnswerFields, b: AnswerFields) => a.selected_option_id === b.selected_option_id
  && a.short_answer_text === b.short_answer_text && a.is_marked_for_review === b.is_marked_for_review;

function conflictAnswer(error: unknown, id: string): Answer | undefined {
  if (!(error instanceof ApiError) || error.status !== 409) return;
  const detail = error.detail;
  if (typeof detail !== 'object' || detail === null || !('current_answer' in detail)) return;
  const answer = detail.current_answer;
  if (typeof answer !== 'object' || answer === null) return;
  if ('exam_question_id' in answer && answer.exam_question_id === id
    && 'revision' in answer && Number.isInteger(answer.revision) && Number(answer.revision) >= 0
    && 'selected_option_id' in answer && (answer.selected_option_id === null || typeof answer.selected_option_id === 'string')
    && 'short_answer_text' in answer && (answer.short_answer_text === null || typeof answer.short_answer_text === 'string')
    && 'is_marked_for_review' in answer && typeof answer.is_marked_for_review === 'boolean'
    && 'last_saved_at' in answer && (answer.last_saved_at === null || typeof answer.last_saved_at === 'string')) return answer as Answer;
}

/** Persist local state before sending; serialize server writes against acknowledged revisions. */
export class AnswerQueue {
  private snapshot: AnswerSnapshot;
  private listeners = new Set<() => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private running?: Promise<boolean>;
  private active = true;
  private retryTimer?: ReturnType<typeof setTimeout>;
  private failures = 0;
  private persistence: Promise<boolean> = Promise.resolve(true);
  private localVersion = 0;
  private disposed?: Promise<void>;
  locked = false;

  constructor(answers: Answer[], private readonly send: (id: string, answer: AnswerWrite) => Promise<AnswerSaved>,
    private readonly canWrite: () => boolean, private readonly journal?: RecoveryJournal) {
    this.snapshot = { cells: Object.fromEntries(answers.map((answer) => [answer.exam_question_id, {
      confirmed: answer, draft: fields(answer),
    }])), saving: false, localSaving: false, localError: null, online: navigator.onLine, restored: false };
  }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(id: string, patch: Partial<AnswerCell>) {
    this.snapshot = { ...this.snapshot, cells: { ...this.snapshot.cells, [id]: { ...this.snapshot.cells[id], ...patch } } };
    this.emit();
  }
  private emit() { this.listeners.forEach((listener) => listener()); }
  private checkpoint(): Promise<boolean> {
    if (!this.journal) return Promise.resolve(true);
    const version = ++this.localVersion;
    const content: RecoveryCell[] = Object.values(this.snapshot.cells).map((cell) => ({
      confirmed: { ...fields(cell.confirmed), exam_question_id: cell.confirmed.exam_question_id,
        revision: cell.confirmed.revision, last_saved_at: cell.confirmed.last_saved_at },
      draft: fields(cell.draft), ...(cell.request ? { request: { ...fields(cell.request), expected_revision: cell.request.expected_revision } } : {}),
    }));
    this.snapshot = { ...this.snapshot, localSaving: true }; this.emit();
    this.persistence = this.persistence.then(async () => {
      try {
        await this.journal!.save(content);
        if (version === this.localVersion) this.snapshot = { ...this.snapshot, localSaving: false, localError: null };
        this.emit(); return true;
      } catch (cause) {
        this.snapshot = { ...this.snapshot, localSaving: version !== this.localVersion,
          localError: cause instanceof Error ? cause.message : 'Local recovery failed. Keep this window open and retry local saving.' };
        this.emit(); return false;
      }
    });
    return this.persistence;
  }
  /** Reconcile a recovery copy only after fresh authenticated server paper/state is available. */
  async restore(saved: RecoveryCell[]) {
    for (const previous of saved) {
      const id = previous.confirmed.exam_question_id;
      const current = this.snapshot.cells[id];
      if (!current) throw new Error('Recovery questions do not match this subject. Contact your proctor.');
      const remote = current.confirmed;
      if (!previous.request && same(previous.draft, previous.confirmed)) continue;
      if (same(remote, previous.draft)) continue;
      const unchanged = remote.revision === previous.confirmed.revision && same(remote, previous.confirmed);
      const acknowledged = previous.request && remote.revision === previous.request.expected_revision + 1 && same(remote, previous.request);
      this.update(id, { draft: fields(previous.draft),
        request: unchanged ? previous.request : undefined,
        ...(unchanged || acknowledged ? {} : { conflict: remote, error: 'This answer changed in another session. Choose which answer to keep.' }),
      });
      this.snapshot = { ...this.snapshot, restored: true };
    }
    if (saved.length) await this.checkpoint();
  }
  dirty() { return Object.values(this.snapshot.cells).some((cell) => cell.request || !same(cell.confirmed, cell.draft)); }
  mergeConfirmed(answers: Answer[]) {
    for (const answer of answers) {
      const cell = this.snapshot.cells[answer.exam_question_id];
      if (cell && !cell.request && !cell.error && same(cell.confirmed, cell.draft) && answer.revision >= cell.confirmed.revision) {
        this.update(answer.exam_question_id, { confirmed: answer, draft: fields(answer) });
      }
    }
  }
  edit(id: string, patch: Partial<AnswerFields>) {
    if (!this.active || this.locked || !this.canWrite() || this.snapshot.localError) return;
    const cell = this.snapshot.cells[id];
    this.update(id, { draft: { ...cell.draft, ...patch } });
    void this.checkpoint();
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.flush(); }, 350);
  }
  flush(): Promise<boolean> {
    clearTimeout(this.timer);
    if (this.running) return this.running;
    this.running = this.drain().finally(() => { this.running = undefined; this.scheduleRetry(); });
    return this.running;
  }
  private async drain(): Promise<boolean> {
    this.snapshot = { ...this.snapshot, saving: true }; this.emit();
    try {
      // Serialize all writes. Each acknowledged revision is the base for the next edit.
      while (this.active && !this.locked && this.canWrite() && !this.snapshot.localError) {
        const id = Object.keys(this.snapshot.cells).find((key) => {
          const cell = this.snapshot.cells[key];
          return !cell.error && !cell.conflict && (cell.request || !same(cell.confirmed, cell.draft));
        });
        if (!id) break;
        const cell = this.snapshot.cells[id];
        const request = cell.request || { ...cell.draft, expected_revision: cell.confirmed.revision };
        this.update(id, { request });
        if (this.journal && !await this.checkpoint()) break;
        // Local storage can take time. Recheck the deadline and account after that await.
        if (!this.active || this.locked || !this.canWrite()) break;
        try {
          const result = await this.send(id, request);
          if (!this.active) return false;
          this.update(id, { confirmed: result.answer, request: undefined, error: undefined });
          this.failures = 0;
          this.snapshot = { ...this.snapshot, online: true };
          if (this.journal && !await this.checkpoint()) break;
        } catch (cause) {
          if (!this.active) return false;
          const conflict = conflictAnswer(cause, id);
          const retryable = cause instanceof ApiError && (cause.status === 0 || cause.status === 408 || cause.status === 429 || cause.status >= 500);
          if (cause instanceof ApiError && [401, 403, 410].includes(cause.status)) this.locked = true;
          this.update(id, {
            error: conflict ? 'This answer changed in another session. Choose which answer to keep.'
              : cause instanceof Error ? cause.message : 'Unable to save your answer.',
            conflict,
            request: retryable ? request : undefined,
            retryable,
          });
          if (retryable) { this.failures += 1; this.snapshot = { ...this.snapshot, online: false }; }
          if (this.journal) await this.checkpoint();
          if (retryable) break;
        }
      }
      return !this.dirty() && !this.snapshot.localError && !Object.values(this.snapshot.cells).some((cell) => cell.error);
    } finally { this.snapshot = { ...this.snapshot, saving: false }; this.emit(); }
  }
  retry() {
    clearTimeout(this.retryTimer);
    for (const [id, cell] of Object.entries(this.snapshot.cells)) {
      if (!cell.conflict) this.update(id, { error: undefined });
    }
    return this.flush();
  }
  resolve(id: string, keepDraft: boolean) {
    const cell = this.snapshot.cells[id];
    if (!cell.conflict || this.locked || !this.canWrite() || this.snapshot.localError) return;
    this.update(id, { confirmed: cell.conflict, draft: keepDraft ? cell.draft : fields(cell.conflict),
      conflict: undefined, error: undefined, request: undefined });
    void this.checkpoint();
    void this.flush();
  }
  private scheduleRetry() {
    clearTimeout(this.retryTimer);
    if (!this.active || this.locked || !this.canWrite() || this.snapshot.localError
      || !Object.values(this.snapshot.cells).some((cell) => cell.retryable && cell.error)) return;
    const delay = Math.min(30_000, 1000 * 2 ** Math.min(this.failures - 1, 5) * (1 + Math.random() * 0.2));
    this.retryTimer = setTimeout(() => { void this.reconnect(); }, delay);
  }
  /** Browser online is a hint. Actual request success/failure determines synchronization state. */
  reconnect() {
    clearTimeout(this.retryTimer);
    for (const [id, cell] of Object.entries(this.snapshot.cells)) {
      if (cell.retryable && !cell.conflict) this.update(id, { error: undefined });
    }
    return this.flush();
  }
  connectionLost() { this.snapshot = { ...this.snapshot, online: false }; this.emit(); }
  connectionConfirmed() { this.snapshot = { ...this.snapshot, online: true }; this.emit(); }
  async retryLocalSave() {
    if (await this.checkpoint()) return this.reconnect();
    return false;
  }
  async close(answers: Answer[]) {
    this.locked = true; clearTimeout(this.timer); clearTimeout(this.retryTimer);
    if (this.running) await this.running;
    // Closure never uploads drafts. Reconcile acknowledgements that may have been lost in transit.
    for (const answer of answers) {
      const cell = this.snapshot.cells[answer.exam_question_id];
      if (!cell) continue;
      this.update(answer.exam_question_id, { confirmed: answer,
        draft: !cell.request && same(cell.draft, cell.confirmed) ? fields(answer) : cell.draft, request: undefined,
        error: undefined, conflict: undefined, retryable: false });
    }
    if (this.journal) {
      await this.checkpoint();
      if (!this.dirty() && !this.snapshot.localError) {
        try { await this.journal.clear(); }
        catch { this.snapshot = { ...this.snapshot, localError: 'The recovery copy could not be cleared. Contact your proctor.' }; }
      }
    }
    this.emit();
  }
  dispose(): Promise<void> {
    if (this.disposed) return this.disposed;
    this.active = false; clearTimeout(this.timer); clearTimeout(this.retryTimer);
    // Finish pending disk writes before releasing cross-tab ownership. Do not wait for network.
    this.disposed = this.persistence.then(async () => { await this.journal?.release(); });
    return this.disposed;
  }
}
