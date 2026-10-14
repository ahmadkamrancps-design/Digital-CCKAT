import { StrictMode } from 'react';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider } from '../src/features/auth/AuthProvider';
import type { SessionProfile } from '../src/types/auth';
import type { AnswerWrite, AssignedExam, Attempt, SubjectPaper } from '../src/types/attempt';

const profile: SessionProfile = {
  user: { id: 'candidate-user', email: 'approved@gmail.com', display_name: 'Registered Candidate', role: 'CANDIDATE' },
  candidate: { id: 'candidate', full_name: 'Registered Candidate', roll_number: 'CCK-104', status: 'APPROVED' },
  csrf_token: 'csrf-test', session_expires_at: '2026-10-08T20:00:00Z',
};
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }); }
const copy = <T,>(value: T): T => structuredClone(value);

/** Stateful HTTP fixture: requests use the real API client/CSRF headers and server response shapes. */
function backend() {
  const state: Attempt = {
    id: 'attempt-1', exam_id: 'exam-1', status: 'IN_PROGRESS', started_at: '2026-10-08T10:00:00Z', submitted_at: null,
    server_time: '2026-10-08T10:00:00Z', subjects: [
      { id: 'subject-1', exam_subject_id: 'paper-1', subject_name: 'English', sequence: 1, duration_minutes: 1,
        status: 'ACTIVE', started_at: '2026-10-08T10:00:00Z', expires_at: '2026-10-08T10:01:00Z', submitted_at: null },
      { id: 'subject-2', exam_subject_id: 'paper-2', subject_name: 'Urdu', sequence: 2, duration_minutes: 7,
        status: 'NOT_STARTED', started_at: null, expires_at: null, submitted_at: null },
    ],
  };
  const paper: SubjectPaper = { subject: state.subjects[0], server_time: state.server_time, questions: [
    { exam_question_id: 'q1', question_id: 'bank-q1', type: 'MCQ', prompt: 'Choose a word.', marks: '2.00', sequence: 1,
      direction: 'auto', language: 'en', options: [{ id: 'a', text: 'Alpha' }, { id: 'b', text: 'Beta' }],
      answer: { exam_question_id: 'q1', revision: 0, selected_option_id: null, short_answer_text: null, is_marked_for_review: false, last_saved_at: null } },
    { exam_question_id: 'q2', question_id: 'bank-q2', type: 'SHORT_ANSWER', prompt: 'مختصر جواب لکھیں', marks: '3.00', sequence: 2,
      direction: 'rtl', language: 'ur', options: [],
      answer: { exam_question_id: 'q2', revision: 0, selected_option_id: null, short_answer_text: null, is_marked_for_review: false, last_saved_at: null } },
  ] };
  const assigned: AssignedExam[] = [{ exam_id: 'exam-1', title: 'Assigned CCK Examination', is_start_authorized: true,
    scheduled_start: null, scheduled_end: null, attempt_id: state.id,
    subjects: state.subjects.map((subject) => ({ exam_subject_id: subject.exam_subject_id, name: subject.subject_name,
      duration_minutes: subject.duration_minutes, sequence: subject.sequence })) }];
  const controls = { failSave: 0, failSubmit: false, failReads: false, failSession: false, expire: false };
  const fetcher = vi.fn(async (path: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    if (path === '/api/me') {
      if (controls.failSession) throw new TypeError('network');
      return response(copy(profile));
    }
    if (method === 'GET' && controls.failReads) throw new TypeError('network');
    if (path === '/api/candidate/exams') return response(copy(assigned));
    if (path === '/api/candidate/exams/exam-1/attempt' && method === 'POST') return response(copy(state));
    if (path === '/api/candidate/attempts/attempt-1') {
      if (controls.expire) { state.subjects[0].status = 'EXPIRED'; state.subjects[0].submitted_at = state.subjects[0].expires_at; }
      return response(copy(state));
    }
    if (path.endsWith('/subject-1/questions')) return response(copy(paper));
    if (path.endsWith('/presence')) return response({ server_time: state.server_time });
    if (path.endsWith('/subject-1/start') && method === 'POST') {
      state.subjects[0].status = 'ACTIVE'; state.subjects[0].started_at = state.started_at;
      state.subjects[0].expires_at = '2026-10-08T10:01:00Z';
      return response(copy(state));
    }
    if (path.includes('/answers/') && method === 'PUT') {
      if (controls.failSave === 1) throw new TypeError('network');
      if (controls.failSave) return response({ detail: 'Subject closed.' }, controls.failSave);
      const question = paper.questions.find((item) => path.endsWith(`/${item.exam_question_id}`))!;
      const write = JSON.parse(String(options.body)) as AnswerWrite;
      if (write.expected_revision !== question.answer.revision) return response({ detail: { message: 'Changed answer', current_answer: copy(question.answer) } }, 409);
      question.answer = { ...question.answer, ...write, revision: question.answer.revision + 1, last_saved_at: state.server_time };
      return response({ answer: copy(question.answer), server_time: state.server_time });
    }
    if (path.endsWith('/subject-1/submit') && method === 'POST') {
      if (controls.failSubmit) throw new TypeError('network');
      state.subjects[0].status = 'SUBMITTED'; state.subjects[0].submitted_at = '2026-10-08T10:00:30Z';
      return response(copy(state));
    }
    throw new Error(`Unexpected fixture request: ${method} ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  return { state, paper, assigned, controls, fetcher };
}
function renderApp(path = '/exam?attempt=attempt-1', strict = false) {
  const app = <MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>;
  return render(strict ? <StrictMode>{app}</StrictMode> : app);
}
const prototype = HTMLDialogElement.prototype;
const oldShow = Object.getOwnPropertyDescriptor(prototype, 'showModal');
const oldClose = Object.getOwnPropertyDescriptor(prototype, 'close');
beforeAll(() => {
  Object.defineProperty(prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); } });
});
afterAll(() => {
  if (oldShow) Object.defineProperty(prototype, 'showModal', oldShow); else Reflect.deleteProperty(prototype, 'showModal');
  if (oldClose) Object.defineProperty(prototype, 'close', oldClose); else Reflect.deleteProperty(prototype, 'close');
});
beforeEach(() => { vi.stubEnv('VITE_ENABLE_UI_PREVIEW', 'false'); });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe('live CCK candidate workflow', () => {
  it('lists assigned exams rather than sample dates and subjects', async () => {
    backend(); renderApp('/dashboard');
    // Session restoration and the assignment request each require a React effect cycle.
    expect(await screen.findByRole('heading', { name: 'Assigned CCK Examination' }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Resume \/ view exam/ })).toHaveAttribute('href', '/exam?attempt=attempt-1');
    expect(screen.queryByText('15 March 2026')).not.toBeInTheDocument();
    expect(screen.getByText('7 Minutes')).toBeInTheDocument();
  });

  it('never starts a subject merely by opening its instructions', async () => {
    const fixture = backend();
    fixture.state.subjects[0].status = 'NOT_STARTED'; fixture.state.subjects[0].started_at = null; fixture.state.subjects[0].expires_at = null;
    renderApp();
    await screen.findByRole('button', { name: 'Start English' });
    expect(fixture.fetcher.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Start English' }));
    await screen.findByRole('heading', { name: 'Question 1 of 2' });
    expect(fixture.fetcher).toHaveBeenCalledWith('/api/candidate/attempts/attempt-1/subjects/subject-1/start', expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-test' }),
    }));
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('saves choices and review flags, navigates, accepts Urdu, and restores server answers after refresh', async () => {
    const fixture = backend(); const view = renderApp();
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await userEvent.click(screen.getByRole('button', { name: 'Mark for Review' }));
    await waitFor(() => expect(fixture.paper.questions[0].answer).toMatchObject({ selected_option_id: 'a', is_marked_for_review: true, revision: 1 }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('textbox')).toHaveAttribute('dir', 'rtl');
    await userEvent.type(screen.getByRole('textbox'), 'پاکستان');
    await waitFor(() => expect(fixture.paper.questions[1].answer.short_answer_text).toBe('پاکستان'));
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(screen.getByRole('radio', { name: 'Alpha' })).toBeChecked();
    expect(screen.getByRole('button', { name: /^Question 1, answered, marked/ })).toHaveAttribute('aria-current', 'step');
    view.unmount(); renderApp();
    expect(await screen.findByRole('radio', { name: 'Alpha' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Mark for Review' })).toHaveAttribute('aria-pressed', 'true');
    expect(fixture.fetcher.mock.calls.filter(([path, options]) => options?.method === 'POST' && !path.endsWith('/presence'))).toHaveLength(0);
  });

  it('crosses out options without changing the selected answer or sending a save', async () => {
    const fixture = backend(); renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Cross out option B' }));
    expect(screen.getByRole('button', { name: 'Cross out option B' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('radio', { name: 'Beta' })).not.toBeChecked();
    expect(fixture.fetcher.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(0);
  });

  it('flushes pending changes before submission and follows the server subject order', async () => {
    const fixture = backend(); renderApp();
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/1 unanswered questions/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Submit subject' }));
    expect(await screen.findByRole('heading', { name: 'Test Submitted Successfully!' })).toBeInTheDocument();
    const writes = fixture.fetcher.mock.calls.filter(([path, options]) => !path.endsWith('/presence') && (options?.method === 'PUT' || options?.method === 'POST'));
    expect(writes.map(([, options]) => options?.method)).toEqual(['PUT', 'POST']);
    expect(screen.getByRole('link', { name: 'Continue to Urdu' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Continue to Urdu' }));
    expect(await screen.findByRole('button', { name: 'Start Urdu' })).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('blocks finish on save failure and retains the draft through background session revalidation', async () => {
    const fixture = backend(); fixture.controls.failSave = 1; renderApp();
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit subject' }));
    await screen.findByText(/Some answers are not saved/);
    fixture.controls.failSession = true;
    act(() => { window.dispatchEvent(new Event('online')); });
    await screen.findByText(/Session check:/);
    expect(screen.getByRole('radio', { name: 'Alpha' })).toBeChecked();
    expect(fixture.state.subjects[0].status).toBe('ACTIVE');
    fixture.controls.failSave = 0;
    act(() => { window.dispatchEvent(new Event('online')); });
    // Reconnection waits for the failed save's checkpoint before retrying.
    await waitFor(() => expect(fixture.paper.questions[0].answer.selected_option_id).toBe('a'), { timeout: 4000 });
  });

  it('never displays success after a failed submission request', async () => {
    const fixture = backend(); fixture.controls.failSubmit = true; renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Finish' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit subject' }));
    await screen.findByText(/Unable to connect/);
    expect(screen.queryByText('Test Submitted Successfully!')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Finish' })).toBeEnabled();
  });

  it('blocks leaving with a failed save and warns before browser refresh', async () => {
    const fixture = backend(); fixture.controls.failSave = 1; renderApp();
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await userEvent.click(screen.getByRole('link', { name: 'Return to candidate dashboard' }));
    await screen.findByText(/Resolve the save problem before leaving/);
    expect(screen.getByRole('radio', { name: 'Alpha' })).toBeChecked();
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
  });

  it('discloses unsynchronized local changes on the confirmed expiry receipt', async () => {
    let monotonic = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => monotonic);
    const fixture = backend(); fixture.controls.failSave = 1; renderApp();
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await screen.findByRole('button', { name: 'Retry saves' });
    fixture.controls.expire = true; monotonic = 61_000;
    expect(await screen.findByRole('heading', { name: 'Subject time ended' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Only answers saved by the server are included');
    expect(fixture.paper.questions[0].answer.selected_option_id).toBeNull();
  });

  it('shows an explicit choice when another session changed an answer', async () => {
    const fixture = backend(); renderApp();
    await screen.findByRole('radio', { name: 'Alpha' });
    fixture.paper.questions[0].answer = { ...fixture.paper.questions[0].answer, selected_option_id: 'b', revision: 5 };
    await userEvent.click(screen.getByRole('radio', { name: 'Alpha' }));
    await screen.findByText(/This answer changed in another session/);
    expect(screen.getByRole('radio', { name: 'Alpha' })).toBeChecked();
    expect(screen.getByText('Beta', { selector: 'bdi' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Use server answer' }));
    expect(screen.getByRole('radio', { name: 'Beta' })).toBeChecked();
    expect(fixture.fetcher.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1);
  });

  it('locks controls at zero and waits for the server-confirmed expiry receipt', async () => {
    let monotonic = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => monotonic);
    const fixture = backend(); renderApp();
    await screen.findByRole('radio', { name: 'Alpha' });
    fixture.controls.failReads = true;
    monotonic = 61_000;
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Alpha' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Finish' })).toBeDisabled();
    expect(screen.queryByText('Test Submitted Successfully!')).not.toBeInTheDocument();
    fixture.controls.failReads = false; fixture.controls.expire = true;
    await userEvent.click(await screen.findByRole('button', { name: 'Check exam status' }));
    expect(await screen.findByRole('heading', { name: 'Subject time ended' })).toBeInTheDocument();
    expect(fixture.fetcher.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(0);
  });

  it('rejects forged receipt parameters for an active subject', async () => {
    backend(); renderApp('/submission?attempt=attempt-1&subject=subject-1');
    expect(await screen.findByRole('alert')).toHaveTextContent('The server has not confirmed submission');
    expect(screen.queryByText('Test Submitted Successfully!')).not.toBeInTheDocument();
  });

  it('confirms final completion only when the server has closed all subjects', async () => {
    const fixture = backend(); fixture.state.status = 'SUBMITTED'; fixture.state.submitted_at = '2026-10-08T10:00:30Z';
    fixture.state.subjects.forEach((subject) => { subject.status = 'SUBMITTED'; subject.submitted_at = fixture.state.submitted_at; });
    renderApp('/submission?attempt=attempt-1&subject=subject-1');
    expect(await screen.findByText(/Your exam submission is recorded/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Continue to/ })).not.toBeInTheDocument();
  });

  it('keeps the live session functional under React StrictMode', async () => {
    const fixture = backend(); renderApp(undefined, true);
    await userEvent.click(await screen.findByRole('radio', { name: 'Alpha' }));
    await waitFor(() => expect(fixture.paper.questions[0].answer.selected_option_id).toBe('a'));
  });

  it('uses the revalidated CSRF token without discarding pending drafts', async () => {
    const fixture = backend(); renderApp();
    await screen.findByRole('radio', { name: 'Alpha' });
    const original = profile.csrf_token;
    profile.csrf_token = 'rotated-csrf';
    try {
      act(() => { window.dispatchEvent(new Event('online')); });
      await waitFor(() => expect(fixture.fetcher.mock.calls.filter(([path]) => path === '/api/me').length).toBe(2));
      await userEvent.click(screen.getByRole('radio', { name: 'Alpha' }));
      await waitFor(() => expect(fixture.paper.questions[0].answer.selected_option_id).toBe('a'));
      expect(fixture.fetcher).toHaveBeenCalledWith(expect.stringContaining('/answers/q1'), expect.objectContaining({
        headers: expect.objectContaining({ 'X-CSRF-Token': 'rotated-csrf' }),
      }));
    } finally { profile.csrf_token = original; }
  });
});
