import type { Answer, AnswerFields, AnswerWrite } from '../types/attempt';

export interface RecoveryScope { userId: string; attemptId: string; subjectId: string }
export interface RecoveryCell { confirmed: Answer; draft: AnswerFields; request?: AnswerWrite }
export interface RecoveryJournal {
  initial: RecoveryCell[];
  save(cells: RecoveryCell[]): Promise<void>;
  clear(): Promise<void>;
  release(): Promise<void>;
}
interface RecoveryRecord extends RecoveryScope {
  key: string;
  schema: 1;
  epoch: number;
  generation: number;
  cells: RecoveryCell[];
}
export const RECOVERY_DATABASE = 'cck-answer-recovery';
const DRAFTS = 'drafts';
const ACCOUNTS = 'accounts';
const storageMessage = 'Local recovery is unavailable. Keep this window open and retry local saving. Contact your proctor if this continues.';
export class RecoveryError extends Error {}
export const recoveryKey = (scope: RecoveryScope) => JSON.stringify([scope.userId, scope.attemptId, scope.subjectId]);

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) { reject(new RecoveryError(storageMessage)); return; }
    let stopped = false;
    const timer = setTimeout(() => { stopped = true; reject(new RecoveryError(storageMessage)); }, 5000);
    const request = indexedDB.open(RECOVERY_DATABASE, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore(DRAFTS, { keyPath: 'key' }).createIndex('user', 'userId');
      db.createObjectStore(ACCOUNTS);
    };
    request.onsuccess = () => {
      clearTimeout(timer);
      if (stopped) { request.result.close(); return; }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = request.onblocked = () => {
      clearTimeout(timer); stopped = true; reject(new RecoveryError(storageMessage));
    };
  });
}

/** Resolve only on transaction completion, never on an individual put's success event. */
async function transaction<T>(mode: IDBTransactionMode, work: (tx: IDBTransaction, result: (value: T) => void, fail: (error: Error) => void) => void): Promise<T> {
  const db = await openDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction([DRAFTS, ACCOUNTS], mode, { durability: 'strict' });
      let value: T;
      let failure: Error | undefined;
      const timer = setTimeout(() => { failure = new RecoveryError(storageMessage); tx.abort(); }, 5000);
      tx.oncomplete = () => { clearTimeout(timer); resolve(value); };
      tx.onabort = () => { clearTimeout(timer); reject(failure || new RecoveryError(storageMessage)); };
      const fail = (error: Error) => { failure = error; tx.abort(); };
      try { work(tx, (result) => { value = result; }, fail); }
      catch { fail(new RecoveryError(storageMessage)); }
    });
  } finally { db.close(); }
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
function fields(value: unknown): AnswerFields {
  if (!object(value) || !(value.selected_option_id === null || typeof value.selected_option_id === 'string')
    || !(value.short_answer_text === null || (typeof value.short_answer_text === 'string' && Array.from(value.short_answer_text).length <= 500))
    || typeof value.is_marked_for_review !== 'boolean') throw new RecoveryError('The recovery copy could not be validated. Keep this window open and contact your proctor.');
  return { selected_option_id: value.selected_option_id, short_answer_text: value.short_answer_text, is_marked_for_review: value.is_marked_for_review };
}
function cells(value: unknown): RecoveryCell[] {
  if (!Array.isArray(value) || value.length > 10_000) throw new RecoveryError('The recovery copy could not be validated. Contact your proctor.');
  const ids = new Set<string>();
  return value.map((cell: unknown) => {
    if (!object(cell) || !object(cell.confirmed)) throw new RecoveryError('Invalid recovery copy. Contact your proctor.');
    const answer = cell.confirmed;
    if (typeof answer.exam_question_id !== 'string' || ids.has(answer.exam_question_id) || !integer(answer.revision)
      || !(answer.last_saved_at === null || typeof answer.last_saved_at === 'string')) throw new RecoveryError('Invalid recovery copy. Contact your proctor.');
    ids.add(answer.exam_question_id);
    const confirmed: Answer = { ...fields(answer), exam_question_id: answer.exam_question_id, revision: answer.revision, last_saved_at: answer.last_saved_at };
    let request: AnswerWrite | undefined;
    if (cell.request !== undefined) {
      if (!object(cell.request) || !integer(cell.request.expected_revision)) throw new RecoveryError('Invalid recovery request. Contact your proctor.');
      request = { ...fields(cell.request), expected_revision: cell.request.expected_revision };
    }
    return { confirmed, draft: fields(cell.draft), ...(request ? { request } : {}) };
  });
}

/** Browser-managed exclusive ownership releases automatically if the tab crashes. */
async function acquire(key: string): Promise<() => Promise<void>> {
  if (!navigator.locks) throw new RecoveryError('Use a supported browser with secure local recovery enabled. Contact your proctor.');
  return new Promise((resolve, reject) => {
    const job = navigator.locks.request(`cck-exam:${key}`, { mode: 'exclusive', ifAvailable: true }, async (lock) => {
      if (!lock) { reject(new RecoveryError('This subject is already open in another tab. Close that tab, then retry questions here.')); return; }
      await new Promise<void>((release) => { resolve(async () => { release(); await job; }); });
    });
    void job.catch(() => reject(new RecoveryError(storageMessage)));
  });
}

export async function openRecovery(scope: RecoveryScope): Promise<RecoveryJournal> {
  const key = recoveryKey(scope);
  const unlock = await acquire(key);
  let released = false;
  let releasing: Promise<void> | undefined;
  const release = () => { released = true; return releasing ??= unlock(); };
  try {
    const loaded = await transaction<{ epoch: number; record: unknown }>('readonly', (tx, result) => {
      const epoch = tx.objectStore(ACCOUNTS).get(scope.userId);
      const record = tx.objectStore(DRAFTS).get(key);
      record.onsuccess = () => result({ epoch: epoch.result ?? 0, record: record.result });
    });
    if (!integer(loaded.epoch)) throw new RecoveryError('Invalid recovery account. Contact your proctor.');
    let generation = 0;
    let initial: RecoveryCell[] = [];
    if (loaded.record !== undefined) {
      const record = loaded.record;
      if (!object(record) || record.schema !== 1 || record.key !== key || record.userId !== scope.userId
        || record.attemptId !== scope.attemptId || record.subjectId !== scope.subjectId || record.epoch !== loaded.epoch
        || !integer(record.generation)) throw new RecoveryError('The recovery copy does not match this attempt. Contact your proctor.');
      generation = record.generation;
      initial = cells(record.cells);
    }
    const change = async (content?: RecoveryCell[]) => {
      if (released) throw new RecoveryError('Recovery ownership ended. Reload this page to verify access.');
      await transaction<void>('readwrite', (tx, result, fail) => {
        const epoch = tx.objectStore(ACCOUNTS).get(scope.userId);
        const drafts = tx.objectStore(DRAFTS);
        const current = drafts.get(key);
        current.onsuccess = () => {
          if ((epoch.result ?? 0) !== loaded.epoch) { fail(new RecoveryError('Your session ended. Sign in again to continue.')); return; }
          if ((current.result?.generation ?? 0) !== generation) { fail(new RecoveryError('The recovery copy changed in another tab. Keep this window open and contact your proctor.')); return; }
          if (content) {
            const record: RecoveryRecord = { ...scope, key, schema: 1, epoch: loaded.epoch, generation: generation + 1, cells: content };
            drafts.put(record);
          } else drafts.delete(key);
          result(undefined);
        };
      });
      generation = content ? generation + 1 : 0;
    };
    return { initial, save: (content) => change(cells(content)), clear: () => change(), release };
  } catch (cause) { await release(); throw cause instanceof RecoveryError ? cause : new RecoveryError(storageMessage); }
}

/** Explicit logout removes this account's copies and invalidates already-open writers atomically. */
export async function clearUserRecovery(userId: string): Promise<void> {
  await transaction<void>('readwrite', (tx, result) => {
    const accounts = tx.objectStore(ACCOUNTS);
    const epoch = accounts.get(userId);
    epoch.onsuccess = () => accounts.put((epoch.result ?? 0) + 1, userId);
    const drafts = tx.objectStore(DRAFTS);
    const cursor = drafts.index('user').openKeyCursor(IDBKeyRange.only(userId));
    cursor.onsuccess = () => {
      const row = cursor.result;
      if (row) { drafts.delete(row.primaryKey); row.continue(); }
    };
    result(undefined);
  });
}
