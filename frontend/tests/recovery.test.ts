import { describe, expect, it, vi } from 'vitest';
import { openRecovery, clearUserRecovery, RECOVERY_DATABASE, recoveryKey, type RecoveryCell, type RecoveryScope } from '../src/storage/recovery';
import { AnswerQueue } from '../src/features/exam/AnswerQueue';
import { ApiError } from '../src/services/api';
import type { Answer, AnswerSaved, AnswerWrite } from '../src/types/attempt';

const scope: RecoveryScope = { userId: 'user-a', attemptId: 'attempt-a', subjectId: 'subject-a' };
const base = (revision = 0, text: string | null = null): Answer => ({ exam_question_id: 'q1', revision,
  short_answer_text: text, selected_option_id: null, is_marked_for_review: false, last_saved_at: null });
const cell = (text = 'پاکستان'): RecoveryCell => ({ confirmed: base(), draft: { ...base(), short_answer_text: text } });
const ack = (id: string, write: AnswerWrite): AnswerSaved => ({ answer: { ...base(write.expected_revision + 1), ...write, exam_question_id: id }, server_time: '2026-10-08T10:00:00Z' });

async function putRaw(transform: (record: Record<string, unknown>) => void) {
  const db = await new Promise<IDBDatabase>((resolve) => { const request = indexedDB.open(RECOVERY_DATABASE, 1); request.onsuccess = () => resolve(request.result); });
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('drafts', 'readwrite');
      const store = tx.objectStore('drafts'); const read = store.get(recoveryKey(scope));
      read.onsuccess = () => { transform(read.result); store.put(read.result); };
      tx.oncomplete = () => resolve(); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

describe('IndexedDB recovery boundary', () => {
  it('restores Unicode drafts and exact unacknowledged requests after reopening', async () => {
    let journal = await openRecovery(scope);
    const original = cell(); original.request = { ...original.draft, expected_revision: 0 };
    try { await journal.save([original]); } finally { await journal.release(); }
    await Promise.resolve();
    journal = await openRecovery(scope);
    try { expect(journal.initial).toEqual([{ confirmed: base(), draft: {
      selected_option_id: null, short_answer_text: 'پاکستان', is_marked_for_review: false,
    }, request: { selected_option_id: null, short_answer_text: 'پاکستان', is_marked_for_review: false, expected_revision: 0 } }]); }
    finally { await journal.release(); }
  });

  it('isolates candidates, attempts, and subjects', async () => {
    const first = await openRecovery(scope);
    try { await first.save([cell('private')]); } finally { await first.release(); }
    for (const other of [{ ...scope, userId: 'other' }, { ...scope, attemptId: 'other' }, { ...scope, subjectId: 'other' }]) {
      const journal = await openRecovery(other);
      try { expect(journal.initial).toEqual([]); } finally { await journal.release(); }
    }
  });

  it('refuses a second writer until the first tab releases ownership', async () => {
    const first = await openRecovery(scope);
    try {
      await first.save([cell('first tab')]);
      await expect(openRecovery(scope)).rejects.toThrow('already open in another tab');
    } finally { await first.release(); }
    await Promise.resolve();
    const next = await openRecovery(scope);
    try { expect(next.initial[0].draft.short_answer_text).toBe('first tab'); } finally { await next.release(); }
  });

  it('detects a changed local generation instead of silently overwriting it', async () => {
    const journal = await openRecovery(scope);
    try {
      await journal.save([cell('original')]);
      await putRaw((record) => { record.generation = 99; record.cells = [cell('newer tab')]; });
      await expect(journal.save([cell('stale')])).rejects.toThrow('changed in another tab');
    } finally { await journal.release(); }
    await Promise.resolve();
    const next = await openRecovery(scope);
    try { expect(next.initial[0].draft.short_answer_text).toBe('newer tab'); } finally { await next.release(); }
  });

  it('does not overwrite corrupt data or mistake it for a successful recovery', async () => {
    const journal = await openRecovery(scope);
    try { await journal.save([cell()]); await putRaw((record) => { record.cells = [{ bad: 'invalid' }]; }); }
    finally { await journal.release(); }
    await Promise.resolve();
    await expect(openRecovery(scope)).rejects.toThrow('Invalid recovery copy');
  });

  it('clears only the signed-out account and prevents old writers recreating its copies', async () => {
    const first = await openRecovery(scope);
    const other = await openRecovery({ ...scope, userId: 'user-b' });
    try {
      await first.save([cell('A')]); await other.save([cell('B')]);
      await clearUserRecovery('user-a');
      await expect(first.save([cell('late write')])).rejects.toThrow('session ended');
    } finally { await first.release(); await other.release(); }
    await Promise.resolve();
    const reloaded = await openRecovery(scope);
    const preserved = await openRecovery({ ...scope, userId: 'user-b' });
    try { expect(reloaded.initial).toEqual([]); expect(preserved.initial[0].draft.short_answer_text).toBe('B'); }
    finally { await reloaded.release(); await preserved.release(); }
  });

  it('fails clearly when persistent storage or tab ownership is unavailable', async () => {
    const original = globalThis.indexedDB;
    Object.defineProperty(globalThis, 'indexedDB', { configurable: true, value: undefined });
    try { await expect(openRecovery(scope)).rejects.toThrow('Local recovery is unavailable'); }
    finally { Object.defineProperty(globalThis, 'indexedDB', { configurable: true, value: original }); }
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
    await expect(openRecovery(scope)).rejects.toThrow('supported browser');
  });
});

describe('durable answer recovery', () => {
  it('commits the recovery snapshot before sending a server write', async () => {
    const journal = await openRecovery(scope);
    const save = vi.spyOn(journal, 'save');
    const send = vi.fn(async (id: string, write: AnswerWrite) => {
      expect(save).toHaveBeenCalled();
      const persisted = save.mock.calls.at(-1)![0][0];
      expect(persisted.request).toEqual(write);
      return ack(id, write);
    });
    const queue = new AnswerQueue([base()], send, () => true, journal);
    try { queue.edit('q1', { short_answer_text: '24' }); expect(await queue.flush()).toBe(true); }
    finally { await queue.dispose(); }
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('restores an offline draft after the page closes and syncs it without manual retry', async () => {
    let journal = await openRecovery(scope);
    const first = new AnswerQueue([base()], async () => { throw new ApiError(0, 'Offline'); }, () => true, journal);
    first.edit('q1', { short_answer_text: 'پاکستان', is_marked_for_review: true });
    expect(await first.flush()).toBe(false); await first.dispose();
    journal = await openRecovery(scope);
    const send = vi.fn(async (id: string, write: AnswerWrite) => ack(id, write));
    const reopened = new AnswerQueue([base()], send, () => true, journal);
    try {
      await reopened.restore(journal.initial);
      expect(reopened.getSnapshot()).toMatchObject({ restored: true, cells: { q1: { draft: { short_answer_text: 'پاکستان' } } } });
      expect(await reopened.reconnect()).toBe(true);
      expect(send.mock.calls[0][1]).toMatchObject({ expected_revision: 0, short_answer_text: 'پاکستان', is_marked_for_review: true });
    } finally { await reopened.dispose(); }
  });

  it('recognizes an acknowledgement lost before reload and preserves a newer local edit', async () => {
    const journal = await openRecovery(scope);
    let server = base();
    const first = new AnswerQueue([base()], async (id, write) => { server = ack(id, write).answer; throw new ApiError(0, 'Lost response'); }, () => true, journal);
    first.edit('q1', { short_answer_text: '24' }); await first.flush();
    first.edit('q1', { short_answer_text: '25' }); await first.dispose();
    const nextJournal = await openRecovery(scope);
    const send = vi.fn(async (id: string, write: AnswerWrite) => ack(id, write));
    const next = new AnswerQueue([server], send, () => true, nextJournal);
    try {
      await next.restore(nextJournal.initial); await next.reconnect();
      expect(send).toHaveBeenCalledExactlyOnceWith('q1', expect.objectContaining({ expected_revision: 1, short_answer_text: '25' }));
    } finally { await next.dispose(); }
  });

  it('never silently replaces a newer server answer with an offline draft', async () => {
    const journal = await openRecovery(scope);
    await journal.save([cell('offline answer')]); await journal.release(); await Promise.resolve();
    const nextJournal = await openRecovery(scope);
    const send = vi.fn(async (id: string, write: AnswerWrite) => ack(id, write));
    const next = new AnswerQueue([base(8, 'new server answer')], send, () => true, nextJournal);
    try {
      await next.restore(nextJournal.initial); expect(await next.reconnect()).toBe(false);
      expect(next.getSnapshot().cells.q1.conflict?.short_answer_text).toBe('new server answer');
      expect(next.getSnapshot().cells.q1.draft.short_answer_text).toBe('offline answer');
      expect(send).not.toHaveBeenCalled();
      next.resolve('q1', true); await next.flush();
      expect(send.mock.calls[0][1]).toMatchObject({ expected_revision: 8, short_answer_text: 'offline answer' });
    } finally { await next.dispose(); }
  });

  it('preserves unsent work after expiry without transmitting it, and clears only fully saved closures', async () => {
    const journal = await openRecovery(scope);
    await journal.save([cell('late unsent')]); await journal.release(); await Promise.resolve();
    const nextJournal = await openRecovery(scope);
    const send = vi.fn(async (id: string, write: AnswerWrite) => ack(id, write));
    const next = new AnswerQueue([base()], send, () => false, nextJournal);
    try {
      await next.restore(nextJournal.initial); await next.reconnect(); await next.close([base()]);
      expect(next.dirty()).toBe(true); expect(send).not.toHaveBeenCalled();
    } finally { await next.dispose(); }
    const retained = await openRecovery(scope);
    try { expect(retained.initial[0].draft.short_answer_text).toBe('late unsent'); }
    finally { await retained.release(); }
    await Promise.resolve();
    const acknowledged = await openRecovery(scope);
    const closed = new AnswerQueue([base(1, 'late unsent')], send, () => false, acknowledged);
    try { await closed.restore(acknowledged.initial); await closed.close([base(1, 'late unsent')]); expect(closed.dirty()).toBe(false); }
    finally { await closed.dispose(); }
    const empty = await openRecovery(scope);
    try { expect(empty.initial).toEqual([]); } finally { await empty.release(); }
  });

  it('shows a storage failure, blocks unprotected edits/writes, and can recover after retry', async () => {
    const journal = await openRecovery(scope);
    const save = vi.spyOn(journal, 'save').mockRejectedValue(new Error('Storage full'));
    const send = vi.fn(async (id: string, write: AnswerWrite) => ack(id, write));
    const queue = new AnswerQueue([base()], send, () => true, journal);
    try {
      queue.edit('q1', { short_answer_text: 'important answer' });
      expect(await queue.flush()).toBe(false);
      expect(queue.getSnapshot().localError).toBe('Storage full'); expect(send).not.toHaveBeenCalled();
      queue.edit('q1', { short_answer_text: 'unprotected edit' });
      expect(queue.getSnapshot().cells.q1.draft.short_answer_text).toBe('important answer');
      save.mockRestore();
      expect(await queue.retryLocalSave()).toBe(true);
      expect(queue.getSnapshot().localError).toBeNull(); expect(send).toHaveBeenCalledTimes(1);
    } finally { await queue.dispose(); }
  });
});
