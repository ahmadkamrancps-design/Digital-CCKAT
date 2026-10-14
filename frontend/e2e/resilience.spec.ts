import { test, expect, type BrowserContext, type Page } from './fixtures';
import type { Answer, AnswerWrite, Attempt, SubjectPaper } from '../src/types/attempt';

/** Browser storage/locks/network tests. Authentication and API are synthetic test fixtures only. */
async function backend(context: BrowserContext) {
  const now = Date.now();
  const start = new Date(now).toISOString();
  const expiry = new Date(now + 60_000).toISOString();
  const attempt: Attempt = { id: 'attempt-1', exam_id: 'exam-1', status: 'IN_PROGRESS', started_at: start, submitted_at: null,
    server_time: start, subjects: [{ id: 'subject-1', exam_subject_id: 'paper-1', subject_name: 'English', sequence: 1,
      duration_minutes: 1, status: 'ACTIVE', started_at: start, expires_at: expiry, submitted_at: null }] };
  let answer: Answer = { exam_question_id: 'q1', revision: 0, selected_option_id: null, short_answer_text: null, is_marked_for_review: false, last_saved_at: null };
  const controls = { offline: false, loseAcknowledgement: false, expire: false };
  const writes: AnswerWrite[] = [];
  const starts: string[] = [];
  const updateTime = () => {
    attempt.server_time = new Date(Date.now()).toISOString();
    if (controls.expire) {
      attempt.subjects[0].status = 'EXPIRED'; attempt.subjects[0].submitted_at = expiry;
      attempt.status = 'SUBMITTED'; attempt.submitted_at = expiry;
      attempt.server_time = expiry;
    }
  };
  await context.route('**/api/**', async (route) => {
    if (controls.offline) { await route.abort('internetdisconnected'); return; }
    updateTime();
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const send = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/me') return send({
      user: { id: 'browser-candidate', email: 'fixture@example.test', display_name: 'Browser Test', role: 'CANDIDATE' },
      candidate: { id: 'candidate-1', full_name: 'Browser Test', roll_number: 'CCK-TEST', status: 'APPROVED' },
      csrf_token: 'synthetic-test-csrf', session_expires_at: new Date(now + 3600_000).toISOString(),
    });
    if (path === '/api/candidate/attempts/attempt-1') return send(attempt);
    if (path.endsWith('/questions')) {
      const paper: SubjectPaper = { subject: attempt.subjects[0], server_time: attempt.server_time, questions: [{
        exam_question_id: 'q1', question_id: 'bank-q1', type: 'MCQ', prompt: 'Choose the word you want to save.', marks: '1.00',
        direction: 'ltr', language: 'en', sequence: 1, options: [{ id: 'a', text: 'Alpha' }, { id: 'b', text: 'Beta' }], answer,
      }] };
      return send(paper);
    }
    if (request.method() !== 'GET' && request.headers()['x-csrf-token'] !== 'synthetic-test-csrf') return send({ detail: 'CSRF required.' }, 403);
    if (path.endsWith('/presence')) return send({ server_time: attempt.server_time });
    if (path.includes('/answers/')) {
      if (attempt.subjects[0].status !== 'ACTIVE') return send({ detail: 'Subject is closed.' }, 410);
      const write = request.postDataJSON() as AnswerWrite;
      writes.push(write);
      const equal = write.selected_option_id === answer.selected_option_id && write.short_answer_text === answer.short_answer_text && write.is_marked_for_review === answer.is_marked_for_review;
      if (write.expected_revision !== answer.revision) {
        if (equal) return send({ answer, server_time: attempt.server_time });
        return send({ detail: { current_answer: answer } }, 409);
      }
      if (!equal) answer = { ...answer, ...write, revision: answer.revision + 1, last_saved_at: attempt.server_time };
      if (controls.loseAcknowledgement) {
        controls.loseAcknowledgement = false; controls.offline = true;
        await route.abort('connectionreset'); return;
      }
      return send({ answer, server_time: attempt.server_time });
    }
    if (path.endsWith('/start') || path.endsWith('/attempt')) starts.push(path);
    return send({ detail: 'Unexpected test request.' }, 404);
  });
  return { controls, writes, starts, attempt, answer: () => answer,
    changeAnswer: () => { answer = { ...answer, revision: answer.revision + 1, selected_option_id: 'b' }; } };
}

async function open(page: Page) {
  await page.goto('/exam?attempt=attempt-1');
  await expect(page.getByRole('radio', { name: 'Alpha' })).toBeEnabled();
}
async function offlineDraft(page: Page, context: BrowserContext, fixture: Awaited<ReturnType<typeof backend>>) {
  fixture.controls.offline = true; await context.setOffline(true);
  await page.getByRole('radio', { name: 'Alpha' }).check();
  await page.getByRole('button', { name: 'Mark for Review' }).click();
  await expect(page.getByText('Saved on this device · awaiting server confirmation')).toBeVisible();
}
test.beforeEach(async ({ page }) => { page.on('dialog', (dialog) => { void dialog.accept(); }); });

test('offline edits survive reload, then synchronize after authenticated reconnection', async ({ page, context }) => {
  const fixture = await backend(context); await open(page);
  await offlineDraft(page, context, fixture);
  await context.setOffline(false); // Assets can reload, while the synthetic API remains unavailable.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Unable to confirm access' })).toBeVisible();
  expect(fixture.answer().revision).toBe(0);
  fixture.controls.offline = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('radio', { name: 'Alpha' })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Mark for Review' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  expect(fixture.answer()).toMatchObject({ revision: 1, selected_option_id: 'a', is_marked_for_review: true });
  expect(fixture.starts).toHaveLength(0);
});

test('a lost acknowledgement is reconciled on reload without an extra logical save', async ({ page, context }) => {
  const fixture = await backend(context); await open(page);
  fixture.controls.loseAcknowledgement = true;
  await page.getByRole('radio', { name: 'Alpha' }).check();
  await expect.poll(() => fixture.answer().revision).toBe(1);
  await expect(page.getByText('Saved on this device · awaiting server confirmation')).toBeVisible();
  fixture.controls.offline = false;
  await page.reload();
  await expect(page.getByRole('radio', { name: 'Alpha' })).toBeChecked();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  expect(fixture.answer().revision).toBe(1); expect(fixture.writes).toHaveLength(1);
});

test('a second tab cannot edit until the first tab closes', async ({ page, context }) => {
  await backend(context); await open(page);
  const second = await context.newPage();
  await second.goto('/exam?attempt=attempt-1');
  await expect(second.getByRole('alert')).toContainText('already open in another tab');
  await expect(second.getByRole('radio')).toHaveCount(0);
  await page.close();
  await second.getByRole('button', { name: 'Retry questions' }).click();
  await expect(second.getByRole('radio', { name: 'Alpha' })).toBeEnabled();
});

test('offline expiry locks editing and never uploads the late draft on reconnection', async ({ page, context }) => {
  await page.clock.install();
  const fixture = await backend(context); await open(page);
  await offlineDraft(page, context, fixture);
  await page.clock.fastForward(61_000);
  await expect(page.getByRole('radio', { name: 'Alpha' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Finish' })).toBeDisabled();
  await expect(page.getByText('Test Submitted Successfully!')).toHaveCount(0);
  fixture.controls.expire = true; fixture.controls.offline = false;
  await context.setOffline(false);
  await page.clock.runFor(5000);
  await expect(page.getByRole('heading', { name: 'Subject time ended' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Only answers saved by the server are included');
  expect(fixture.writes).toHaveLength(0); expect(fixture.answer().revision).toBe(0);
});

test('restored stale drafts require a choice before replacing a newer server answer', async ({ page, context }) => {
  const fixture = await backend(context); await open(page);
  await offlineDraft(page, context, fixture);
  fixture.changeAnswer(); fixture.controls.offline = false; await context.setOffline(false);
  await expect(page.getByText('This answer changed in another session. Choose which answer to keep.')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Use server answer' })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Alpha' })).toBeChecked();
  expect(fixture.answer().selected_option_id).toBe('b');
  await page.getByRole('button', { name: 'Use server answer' }).click();
  await expect(page.getByRole('radio', { name: 'Beta' })).toBeChecked();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
});
