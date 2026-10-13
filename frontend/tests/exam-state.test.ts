import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AnswerQueue } from '../src/features/exam/AnswerQueue';
import { ServerDeadline } from '../src/features/exam/ServerDeadline';
import { ApiError } from '../src/services/api';
import type { Answer, AnswerSaved, AnswerWrite } from '../src/types/attempt';

const answer = (id = 'q1', revision = 0, text: string | null = null): Answer => ({
  exam_question_id: id, revision, short_answer_text: text, selected_option_id: null,
  is_marked_for_review: false, last_saved_at: revision ? '2026-10-08T10:00:00Z' : null,
});
const saved = (id: string, request: AnswerWrite): AnswerSaved => ({
  answer: { ...answer(id, request.expected_revision + 1), ...request }, server_time: '2026-10-08T10:00:00Z',
});
const queues: AnswerQueue[] = [];
function makeQueue(send: (id: string, request: AnswerWrite) => Promise<AnswerSaved>, canWrite = () => true, ids = ['q1']) {
  const queue = new AnswerQueue(ids.map((id) => answer(id)), send, canWrite);
  queues.push(queue);
  return queue;
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { queues.splice(0).forEach((queue) => queue.dispose()); vi.useRealTimers(); });

describe('answer synchronization', () => {
  it.each([0, 408, 429, 503])('automatically backs off and retries transient failures (%s)', async (status) => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request))
      .mockRejectedValueOnce(new ApiError(status, 'Temporary failure'))
      .mockRejectedValueOnce(new ApiError(status, 'Temporary failure'));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: '24' }); await queue.flush();
    await vi.advanceTimersByTimeAsync(999); expect(send).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1); expect(send).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1999); expect(send).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1); expect(send).toHaveBeenCalledTimes(3);
    expect(send.mock.calls[0][1]).toEqual(send.mock.calls[2][1]);
    expect(queue.dirty()).toBe(false); expect(queue.getSnapshot().online).toBe(true);
  });

  it('never retries permanent validation failures automatically', async () => {
    const send = vi.fn().mockRejectedValue(new ApiError(422, 'Invalid answer'));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: '24' }); await queue.flush();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(send).toHaveBeenCalledTimes(1); expect(queue.dirty()).toBe(true);
  });

  it('stops scheduled retries when the deadline passes', async () => {
    let writable = true;
    const send = vi.fn().mockRejectedValue(new ApiError(0, 'Offline'));
    const queue = makeQueue(send, () => writable);
    queue.edit('q1', { short_answer_text: '24' }); await queue.flush();
    writable = false;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(send).toHaveBeenCalledTimes(1); expect(queue.dirty()).toBe(true);
  });

  it('debounces typing into one complete snapshot and acknowledges saved state', async () => {
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: 'پ' });
    await vi.advanceTimersByTimeAsync(100);
    queue.edit('q1', { short_answer_text: 'پاکستان', is_marked_for_review: true });
    await vi.advanceTimersByTimeAsync(349);
    expect(send).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(send).toHaveBeenCalledExactlyOnceWith('q1', {
      expected_revision: 0, selected_option_id: null, short_answer_text: 'پاکستان', is_marked_for_review: true,
    });
    expect(queue.dirty()).toBe(false);
    expect(queue.getSnapshot().cells.q1.confirmed.revision).toBe(1);
  });

  it('serializes edits during a slow request without replacing the latest draft', async () => {
    let acknowledge!: (value: AnswerSaved) => void;
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request))
      .mockImplementationOnce(() => new Promise<AnswerSaved>((resolve) => { acknowledge = resolve; }));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: '2' });
    const flush = queue.flush();
    queue.edit('q1', { short_answer_text: '24' });
    await vi.advanceTimersByTimeAsync(500);
    expect(send).toHaveBeenCalledTimes(1);
    acknowledge(saved('q1', send.mock.calls[0][1]));
    expect(await flush).toBe(true);
    expect(send.mock.calls[1][1]).toMatchObject({ expected_revision: 1, short_answer_text: '24' });
    expect(queue.getSnapshot().cells.q1.draft.short_answer_text).toBe('24');
  });

  it('revisits a question edited while a later question was being saved', async () => {
    let acknowledge!: (value: AnswerSaved) => void;
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request));
    const queue = makeQueue(send, () => true, ['q1', 'q2']);
    queue.edit('q1', { short_answer_text: 'first' });
    await queue.flush();
    send.mockImplementationOnce(() => new Promise<AnswerSaved>((resolve) => { acknowledge = resolve; }));
    queue.edit('q2', { short_answer_text: 'second' });
    const flush = queue.flush();
    queue.edit('q1', { short_answer_text: 'new first' });
    acknowledge(saved('q2', send.mock.calls[1][1]));
    expect(await flush).toBe(true);
    expect(send.mock.calls[2]).toEqual(['q1', expect.objectContaining({ expected_revision: 1, short_answer_text: 'new first' })]);
  });

  it('replays the exact unacknowledged request before saving a newer draft', async () => {
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request))
      .mockRejectedValueOnce(new ApiError(0, 'Network unavailable'));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: '24' });
    expect(await queue.flush()).toBe(false);
    queue.edit('q1', { short_answer_text: '25' });
    expect(await queue.retry()).toBe(true);
    expect(send.mock.calls[1][1]).toEqual(send.mock.calls[0][1]);
    expect(send.mock.calls[2][1]).toMatchObject({ expected_revision: 1, short_answer_text: '25' });
  });

  it.each([false, true])('requires an explicit conflict choice; keep draft=%s', async (keepDraft) => {
    const server = answer('q1', 7, 'server answer');
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request))
      .mockRejectedValueOnce(new ApiError(409, 'Conflict', { current_answer: server }));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: 'my answer' });
    expect(await queue.flush()).toBe(false);
    expect(await queue.retry()).toBe(false);
    expect(send).toHaveBeenCalledTimes(1);
    queue.resolve('q1', keepDraft);
    await queue.flush();
    expect(queue.dirty()).toBe(false);
    if (keepDraft) expect(send.mock.calls[1][1]).toMatchObject({ expected_revision: 7, short_answer_text: 'my answer' });
    else { expect(send).toHaveBeenCalledTimes(1); expect(queue.getSnapshot().cells.q1.draft.short_answer_text).toBe('server answer'); }
  });

  it('does not let refreshed server data overwrite a pending draft', () => {
    const queue = makeQueue(async (id, request) => saved(id, request), () => true, ['q1', 'q2']);
    queue.edit('q1', { short_answer_text: 'local' });
    queue.mergeConfirmed([answer('q1', 4, 'remote'), answer('q2', 4, 'other')]);
    expect(queue.getSnapshot().cells.q1).toMatchObject({ confirmed: { revision: 0 }, draft: { short_answer_text: 'local' } });
    expect(queue.getSnapshot().cells.q2).toMatchObject({ confirmed: { revision: 4 }, draft: { short_answer_text: 'other' } });
  });

  it.each([401, 403, 410])('locks after a server rejection (%s) and never claims saved', async (status) => {
    const send = vi.fn().mockRejectedValue(new ApiError(status, 'Access closed'));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: 'answer' });
    expect(await queue.flush()).toBe(false);
    expect(queue.locked).toBe(true);
    queue.edit('q1', { short_answer_text: 'later' });
    await queue.retry();
    expect(send).toHaveBeenCalledTimes(1);
    expect(queue.getSnapshot().cells.q1.draft.short_answer_text).toBe('answer');
    expect(queue.dirty()).toBe(true);
  });

  it('keeps unsaved drafts but sends no writes once the deadline passes', async () => {
    let writable = true;
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request));
    const queue = makeQueue(send, () => writable);
    queue.edit('q1', { short_answer_text: 'draft' });
    writable = false;
    expect(await queue.flush()).toBe(false);
    queue.edit('q1', { short_answer_text: 'late edit' });
    expect(send).not.toHaveBeenCalled();
    expect(queue.getSnapshot().cells.q1.draft.short_answer_text).toBe('draft');
  });

  it('cancels queued work when the authenticated account is removed', async () => {
    const send = vi.fn(async (id: string, request: AnswerWrite) => saved(id, request));
    const queue = makeQueue(send);
    queue.edit('q1', { short_answer_text: 'private' }); queue.dispose();
    await vi.advanceTimersByTimeAsync(1000);
    expect(send).not.toHaveBeenCalled();
  });
});

describe('server-derived countdown', () => {
  it('uses monotonic elapsed time despite device-clock changes', async () => {
    const deadline = new ServerDeadline();
    deadline.sync('2026-10-08T10:01:00Z', '2026-10-08T10:00:00Z', performance.now());
    expect(deadline.seconds()).toBe(60);
    vi.setSystemTime(new Date('2030-01-01'));
    await vi.advanceTimersByTimeAsync(10_000);
    expect(deadline.seconds()).toBe(50);
    vi.setSystemTime(new Date('2000-01-01'));
    await vi.advanceTimersByTimeAsync(50_000);
    expect(deadline.seconds()).toBe(0);
    expect(deadline.writable()).toBe(false);
  });
  it('does not add response transit time or extend an existing deadline on revalidation', async () => {
    const deadline = new ServerDeadline();
    const requested = performance.now();
    await vi.advanceTimersByTimeAsync(2_000);
    deadline.sync('2026-10-08T10:01:00Z', '2026-10-08T10:00:00Z', requested);
    expect(deadline.seconds()).toBe(58);
    deadline.sync('2026-10-08T10:01:00Z', '2026-10-08T10:00:00Z', performance.now());
    expect(deadline.seconds()).toBe(58);
  });
});
