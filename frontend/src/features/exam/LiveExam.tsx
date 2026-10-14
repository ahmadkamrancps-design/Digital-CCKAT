import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowLeft, ArrowRight, Bookmark } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ExamHeader } from '../../components/ExamHeader';
import { QuestionPalette } from '../../components/QuestionPalette';
import { QuestionRenderer } from '../../components/QuestionRenderer';
import { SaveStatus } from '../../components/SaveStatus';
import { examApi } from '../../services/exam';
import type { Attempt, SubjectAttempt, SubjectPaper } from '../../types/attempt';
import type { ExamQuestion, SaveState } from '../../types/exam';
import { useAuth } from '../auth/AuthProvider';
import { AssignedExams } from './AssignedExams';
import { useOpenExamSession, type ExamSession } from './ExamSessions';
import { useExamPresence } from './useExamPresence';

const message = (cause: unknown) => cause instanceof Error ? cause.message : 'Unable to load the exam.';
const closed = (subject: SubjectAttempt) => ['SUBMITTED', 'EXPIRED'].includes(subject.status);
const receiptPath = (attempt: string, subject: string) => `/submission?attempt=${encodeURIComponent(attempt)}&subject=${encodeURIComponent(subject)}`;

export function LiveExam() {
  const [params] = useSearchParams();
  const attemptId = params.get('attempt');
  const examId = params.get('exam');
  return <ExamEntry key={attemptId || examId || 'list'} attemptId={attemptId} examId={examId} />;
}

function ExamEntry({ attemptId, examId }: { attemptId: string | null; examId: string | null }) {
  const { profile } = useAuth();
  const navigate = useNavigate();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [title, setTitle] = useState('Digital Entry Test');
  const [authorized, setAuthorized] = useState(false);
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    setError('');
    setReady(false);
    void (async () => {
      if (attemptId) {
        const result = await examApi.attempt(attemptId);
        if (current) setAttempt(result);
      } else if (examId) {
        const exams = await examApi.assigned();
        const assigned = exams.find((item) => item.exam_id === examId);
        if (!assigned) throw new Error('This exam is not assigned to your account.');
        if (current) { setTitle(assigned.title); setAuthorized(assigned.is_start_authorized); }
        if (assigned.attempt_id && current) navigate(`/exam?attempt=${encodeURIComponent(assigned.attempt_id)}`, { replace: true });
      }
      if (current) setReady(true);
    })().catch((cause: unknown) => { if (current) setError(message(cause)); });
    return () => { current = false; };
  }, [attemptId, examId, retry, navigate]);

  async function action(subject?: SubjectAttempt) {
    if (!profile || pending) return;
    setPending(true); setError('');
    try {
      const result = subject && attempt
        ? await examApi.start(attempt.id, subject.id, profile.csrf_token)
        : await examApi.begin(examId!, profile.csrf_token);
      if (!attemptId) navigate(`/exam?attempt=${encodeURIComponent(result.id)}`, { replace: true });
      else setAttempt(result);
    } catch (cause) { setError(message(cause)); }
    finally { setPending(false); }
  }

  if (!attemptId && !examId) return <main className="exam-entry" id="main"><AssignedExams /><Link to="/dashboard">Return to dashboard</Link></main>;
  if (!ready) return <main className="exam-entry" id="main"><section className="card session-state">
    {error ? <><p role="alert">{error}</p><button onClick={() => setRetry((value) => value + 1)}>Retry exam access</button></> : <p role="status">Loading exam…</p>}
    <Link to="/dashboard">Return to dashboard</Link>
  </section></main>;
  const subjects = [...(attempt?.subjects || [])].sort((a, b) => a.sequence - b.sequence);
  const active = subjects.find((subject) => subject.status === 'ACTIVE');
  if (active && attempt) return <ActivePaper key={active.id} attempt={attempt} subject={active} onState={setAttempt} />;
  const next = subjects.find((subject) => subject.status === 'NOT_STARTED');
  const last = subjects.filter(closed).at(-1);
  return <main className="exam-entry" id="main"><section className="exam-card card">
    <h1>{attempt ? (next ? `Ready for ${next.subject_name}` : 'Exam completed') : title}</h1>
    <p>Work through subjects in the assigned order. Each subject has its own timer.</p>
    <p>Your timer starts when you choose Start subject. Submitted or expired subjects cannot be changed.</p>
    <p>Answers save automatically while you work. Check the save status before finishing. A temporary connection failure does not extend your time.</p>
    {!attempt && <p>{authorized ? 'Administration has authorized this exam. The server will check the scheduled window before allowing access.' : 'Waiting for start authorization. Refresh this page when the proctor authorizes the exam.'}</p>}
    {subjects.length > 0 && <ol>{subjects.map((subject) => <li key={subject.id}>
      <bdi>{subject.subject_name}</bdi> · {subject.duration_minutes} minutes · {subject.status.replace('_', ' ')}
      {closed(subject) && <> · <Link to={receiptPath(attempt!.id, subject.id)}>View submission</Link></>}
    </li>)}</ol>}
    {error && <p role="alert">{error}</p>}
    {next ? <button className="primary-button" disabled={pending} onClick={() => { void action(next); }}>{pending ? 'Starting…' : `Start ${next.subject_name}`}</button>
      : !attempt ? <button className="primary-button" disabled={pending || !authorized} onClick={() => { void action(); }}>{pending ? 'Opening…' : 'Open assigned exam'}</button>
      : last ? <Link className="primary-button" to={receiptPath(attempt.id, last.id)}>View final confirmation</Link> : null}
    <p><Link to="/dashboard">Return to dashboard</Link></p>
  </section></main>;
}

function ActivePaper({ attempt, subject, onState }: { attempt: Attempt; subject: SubjectAttempt; onState: (value: Attempt) => void }) {
  const { profile } = useAuth();
  const csrf = profile!.csrf_token;
  const openSession = useOpenExamSession();
  const navigate = useNavigate();
  const [paper, setPaper] = useState<SubjectPaper | null>(null);
  const [session, setSession] = useState<ExamSession | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    const requestStarted = performance.now();
    setError('');
    void examApi.paper(attempt.id, subject.id).then(async (result) => {
      if (!current) return;
      if (closed(result.subject)) { navigate(receiptPath(attempt.id, subject.id), { replace: true }); return; }
      const value = await openSession(attempt.id, result, requestStarted);
      if (!current) return;
      value.deadline.sync(result.subject.expires_at, result.server_time, requestStarted);
      value.queue.mergeConfirmed(result.questions.map((question) => question.answer));
      if (value.deadline.writable()) value.queue.locked = false;
      setSession(value); setPaper(result);
      void value.queue.reconnect();
    }).catch((cause: unknown) => { if (current) setError(message(cause)); });
    return () => { current = false; };
  }, [attempt.id, subject.id, retry, openSession, csrf, navigate]);
  // Profile revalidation must not reload a paper or replace local drafts. Dependencies use the stable identity/token below.
  if (!paper || !session) return <main className="exam-entry" id="main"><section className="card session-state">
    {error ? <><p role="alert">{error}</p><button onClick={() => setRetry((value) => value + 1)}>Retry questions</button></> : <p role="status">Loading questions…</p>}
  </section></main>;
  return <ExamWorkspace paper={paper} session={session} attempt={attempt} onState={onState} />;
}

function ExamWorkspace({ paper, session, attempt, onState }: { paper: SubjectPaper; session: ExamSession; attempt: Attempt; onState: (value: Attempt) => void }) {
  const { profile } = useAuth();
  const navigate = useNavigate();
  const { queue, deadline } = session;
  const snapshot = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  const [seconds, setSeconds] = useState(deadline.seconds());
  const [index, setIndex] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [eliminated, setEliminated] = useState<Record<string, string[]>>({});
  const heading = useRef<HTMLHeadingElement>(null);
  const checking = useRef(false);
  const mounted = useRef(true);
  const question = paper.questions[index];
  const cell = snapshot.cells[question.exam_question_id];
  const locked = seconds === 0 || queue.locked || !!snapshot.localError || paper.subject.status !== 'ACTIVE';
  useExamPresence(attempt.id, paper.subject.id, index + 1, seconds > 0 && !queue.locked && paper.subject.status === 'ACTIVE');
  const value = question.type === 'MCQ' ? cell.draft.selected_option_id || '' : cell.draft.short_answer_text || '';
  const navigation = paper.questions.map((item, number) => {
    const answer = snapshot.cells[item.exam_question_id].draft;
    return { id: item.exam_question_id, number: number + 1,
      isAnswered: !!(answer.selected_option_id || answer.short_answer_text?.trim()), isMarkedForReview: answer.is_marked_for_review };
  });
  const errors = Object.entries(snapshot.cells).filter(([, item]) => item.error);
  const status: SaveState = snapshot.localError || (locked && queue.dirty()) ? 'error' : !snapshot.online && queue.dirty() ? 'offline' : errors.length ? 'error'
    : snapshot.saving || queue.dirty() ? 'saving' : 'saved';

  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [index]);
  useEffect(() => {
    mounted.current = true;
    const tick = window.setInterval(() => setSeconds(deadline.seconds()), 250);
    return () => { mounted.current = false; window.clearInterval(tick); };
  }, [deadline]);

  const checkState = useCallback(async () => {
    if (checking.current) return;
    checking.current = true;
    const requestStarted = performance.now();
    try {
      const result = await examApi.attempt(attempt.id);
      if (!mounted.current) return;
      const current = result.subjects.find((item) => item.id === paper.subject.id);
      if (!current) throw new Error('Unable to confirm the active subject.');
      queue.connectionConfirmed();
      if (closed(current)) {
        queue.locked = true;
        navigate(receiptPath(result.id, current.id), { replace: true });
      } else {
        deadline.sync(current.expires_at, result.server_time, requestStarted);
        setSeconds(deadline.seconds());
        onState(result);
      }
      setError('');
    } catch (cause) { if (mounted.current) { queue.connectionLost(); setError(message(cause)); } }
    finally { checking.current = false; }
  }, [attempt.id, paper.subject.id, deadline, queue, navigate, onState]);
  const deadlineReached = seconds === 0;
  useEffect(() => {
    void checkState();
    const timer = window.setInterval(() => { void checkState(); }, deadlineReached ? 5_000 : 15_000);
    const visible = () => { if (document.visibilityState === 'visible') void checkState(); };
    document.addEventListener('visibilitychange', visible);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [checkState, deadlineReached]);

  async function finish() {
    if (pending || locked || !profile) return;
    setPending(true); setError('');
    try {
      if (!await queue.flush()) throw new Error('Some answers are not saved. Resolve the save problem before finishing.');
      if (!deadline.writable()) { await checkState(); return; }
      const result = await examApi.submit(attempt.id, paper.subject.id, profile.csrf_token);
      if (!mounted.current) return;
      const current = result.subjects.find((item) => item.id === paper.subject.id);
      if (!current || !closed(current) || !current.submitted_at) throw new Error('The server has not confirmed submission. Check status before continuing.');
      queue.locked = true;
      navigate(receiptPath(result.id, current.id), { replace: true });
    } catch (cause) { if (mounted.current) setError(message(cause)); }
    finally { if (mounted.current) { setPending(false); setConfirming(false); } }
  }
  async function leave() {
    if (pending) return;
    if (queue.dirty() && !await queue.flush()) { setError('Some answers are not saved. Resolve the save problem before leaving.'); return; }
    navigate('/dashboard');
  }
  const rendered: ExamQuestion = question.type === 'MCQ'
    ? { id: question.exam_question_id, prompt: question.prompt, marks: Number(question.marks), direction: question.direction,
      language: question.language || undefined, type: 'MCQ', options: question.options }
    : { id: question.exam_question_id, prompt: question.prompt, marks: Number(question.marks), direction: question.direction,
      language: question.language || undefined, type: 'SHORT_ANSWER', maxLength: 500 };

  return <main className="exam-shell" id="main" tabIndex={-1}>
    <ExamHeader subjects={[]} subjectId={paper.subject.id} onSubjectChange={() => {}} liveSubject={paper.subject.subject_name}
      title="Digital Entry Test" remainingSeconds={seconds} onFinish={() => setConfirming(true)} finished={locked || pending} onLeave={() => { void leave(); }} />
    <div className="exam-save-bar"><SaveStatus status={status} /><span>{snapshot.online ? 'Connected' : 'Connection interrupted · retrying'}</span>
      {queue.dirty() && <span>{snapshot.localSaving ? 'Preserving changes on this device…' : snapshot.localError ? 'Recovery copy needs attention' : 'Saved on this device · awaiting server confirmation'}</span>}
      {snapshot.restored && <span>Recovered answers from this device</span>}
      {errors.length > 0 && !locked && <button onClick={() => { void queue.retry(); }}>Retry saves</button>}
    </div>
    {snapshot.localError && <div className="exam-alert" role="alert">{snapshot.localError} <button onClick={() => { void queue.retryLocalSave(); }}>Retry local saving</button></div>}
    {(seconds === 0 || queue.locked) && <p className="exam-alert" role="alert">Time has ended or access is locked. Answers cannot be changed. Checking server submission status…</p>}
    {error && <div className="exam-alert" role="alert">{error} <button onClick={() => { void checkState(); }}>Check exam status</button></div>}
    <div className="exam-workspace">
      <aside className="exam-question-sidebar"><QuestionPalette questions={navigation} currentQuestionId={question.exam_question_id}
        onNavigate={(id) => setIndex(paper.questions.findIndex((item) => item.exam_question_id === id))} />
        <button className="exam-dashboard-link" onClick={() => { void leave(); }}>Return to dashboard</button></aside>
      <section className="exam-question-area" aria-labelledby="question-heading">
        <div className="question-toolbar"><h1 ref={heading} tabIndex={-1} id="question-heading">Question {index + 1} of {paper.questions.length}</h1>
          <button className={`review-button${cell.draft.is_marked_for_review ? ' is-marked' : ''}`} aria-pressed={cell.draft.is_marked_for_review}
            disabled={locked || pending} onClick={() => queue.edit(question.exam_question_id, { is_marked_for_review: !cell.draft.is_marked_for_review })}>
            <Bookmark size={17} aria-hidden="true" /> Mark for Review</button></div>
        <div className="exam-question-card"><QuestionRenderer question={rendered} value={value} disabled={locked || pending}
          eliminated={eliminated[question.exam_question_id] || []} onEliminate={(id) => setEliminated((current) => {
            const options = current[question.exam_question_id] || [];
            return { ...current, [question.exam_question_id]: options.includes(id) ? options.filter((item) => item !== id) : [...options, id] };
          })}
          onChange={(answer) => queue.edit(question.exam_question_id, question.type === 'MCQ'
            ? { selected_option_id: answer || null, short_answer_text: null } : { short_answer_text: answer || null, selected_option_id: null })} />
          <button className="clear-answer-button" disabled={locked || pending || !value} onClick={() => queue.edit(question.exam_question_id, { selected_option_id: null, short_answer_text: null })}>Clear Answer</button>
          {cell.error && <div className="answer-problem" role="alert"><p>{cell.error}</p>
            {cell.conflict && <><p>Current server answer: <bdi>{cell.conflict.selected_option_id
              ? question.options.find((item) => item.id === cell.conflict!.selected_option_id)?.text || 'Selected option'
              : cell.conflict.short_answer_text || 'Unanswered'}</bdi> · {cell.conflict.is_marked_for_review ? 'Marked for review' : 'Not marked'}</p>
              <button disabled={locked} onClick={() => queue.resolve(question.exam_question_id, false)}>Use server answer</button>
              <button disabled={locked} onClick={() => queue.resolve(question.exam_question_id, true)}>Save my answer instead</button></>}
          </div>}
          {errors.some(([id]) => id !== question.exam_question_id) && <p role="alert">Another question has a save problem. <button onClick={() => setIndex(paper.questions.findIndex((item) => item.exam_question_id === errors[0][0]))}>Review save problem</button></p>}
          <div className="question-navigation"><button className="secondary-button" disabled={index === 0} onClick={() => setIndex(index - 1)}><ArrowLeft size={18} aria-hidden="true" /> Previous</button>
            <button className="primary-button" disabled={index === paper.questions.length - 1} onClick={() => setIndex(index + 1)}>Next <ArrowRight size={18} aria-hidden="true" /></button></div>
        </div>
      </section>
    </div>
    {confirming && !locked && <FinishSubject subjectName={paper.subject.subject_name} unanswered={navigation.filter((item) => !item.isAnswered).length}
      pending={pending} onCancel={() => setConfirming(false)} onConfirm={() => { void finish(); }} />}
  </main>;
}

function FinishSubject({ subjectName, unanswered, pending, onCancel, onConfirm }: {
  subjectName: string; unanswered: number; pending: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="finish-dialog" aria-labelledby="finish-title" onCancel={(event) => { if (pending) event.preventDefault(); else onCancel(); }}>
    <h2 id="finish-title">Finish {subjectName}?</h2><p>{unanswered} unanswered questions. Saved answers will be submitted and this subject will be locked.</p>
    <div className="finish-dialog-actions"><button className="secondary-button" disabled={pending} onClick={onCancel}>Keep reviewing</button>
      <button className="primary-button" disabled={pending} onClick={onConfirm}>{pending ? 'Saving and submitting…' : 'Submit subject'}</button></div>
  </dialog>;
}
