import { useEffect, useRef, useState } from 'react';
import { ArrowRight, BookOpen, Check, FileText, Info, Timer } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import CCKLogo from '../../components/CCKLogo';
import { SubmissionSuccessIcon } from '../../components/SubmissionSuccessIcon';
import { examApi } from '../../services/exam';
import type { Attempt, SubjectAttempt } from '../../types/attempt';
import { useExamSessions, useOpenExamSession } from './ExamSessions';

/** A reload fetches the receipt from the server; route parameters are never evidence of success. */
export function LiveSubmission() {
  const sessions = useExamSessions();
  const openSession = useOpenExamSession();
  const [params] = useSearchParams();
  const attemptId = params.get('attempt');
  const subjectId = params.get('subject');
  const [receipt, setReceipt] = useState<{ attempt: Attempt; subject: SubjectAttempt; count: number | null } | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [recoveryError, setRecoveryError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let current = true;
    setReceipt(null); setError(''); setRecoveryError('');
    if (!attemptId || !subjectId) return;
    void (async () => {
      const attempt = await examApi.attempt(attemptId);
      const subject = attempt.subjects.find((item) => item.id === subjectId);
      if (!subject || !['SUBMITTED', 'EXPIRED'].includes(subject.status) || !subject.submitted_at) {
        throw new Error('The server has not confirmed submission for this subject.');
      }
      // A subject expired before it began has no candidate-visible paper.
      const paper = subject.started_at ? await examApi.paper(attempt.id, subject.id) : null;
      if (paper && current) {
        try {
          const session = await openSession(attempt.id, paper, performance.now());
          await session.queue.close(paper.questions.map((question) => question.answer));
          if (current) setRecoveryError(session.queue.getSnapshot().localError || '');
        } catch (cause) {
          if (current) setRecoveryError(cause instanceof Error ? cause.message : 'Unable to inspect the local recovery copy.');
        }
      }
      if (current) setReceipt({ attempt, subject, count: paper?.questions.length ?? null });
    })().catch((cause: unknown) => { if (current) setError(cause instanceof Error ? cause.message : 'Unable to confirm submission.'); });
    return () => { current = false; };
  }, [attemptId, subjectId, retry, openSession]);
  useEffect(() => { if (receipt) heading.current?.focus({ preventScroll: true }); }, [receipt]);
  if (!receipt) return <main className="submission-page" id="main"><section className="submission-card">
    <h1>Submission status</h1>
    {error ? <><p role="alert">{error}</p><button onClick={() => setRetry((value) => value + 1)}>Retry confirmation</button></>
      : !attemptId || !subjectId ? <p>There is no confirmed submission to display.</p> : <p role="status">Confirming submission with the server…</p>}
    <p><Link to="/dashboard">Return to dashboard</Link></p>
  </section></main>;
  const { attempt, subject, count } = receipt;
  const next = [...attempt.subjects].sort((a, b) => a.sequence - b.sequence).find((item) => ['NOT_STARTED', 'ACTIVE'].includes(item.status));
  const timestamp = new Date(subject.submitted_at!);
  return <main className="submission-page" id="main" tabIndex={-1}><section className="submission-card" aria-labelledby="submission-heading">
    <div className="submission-brand"><CCKLogo size={74} /><div><strong className="cck-serif">Cadet College Kohat</strong><span>Digital Entry Test</span></div></div>
    <SubmissionSuccessIcon key={subject.id} animate={subject.status === 'SUBMITTED'} />
    <h1 ref={heading} tabIndex={-1} id="submission-heading">{subject.status === 'EXPIRED' ? 'Subject time ended' : 'Test Submitted Successfully!'}</h1>
    <p className="submission-intro">{subject.status === 'EXPIRED' ? 'The server has closed this subject. Saved answers are locked.' : 'Your subject has been submitted and answers are locked.'}</p>
    {sessions.get(subject.id)?.queue.dirty() && <p className="exam-alert" role="alert">Some local changes were not acknowledged before this subject closed. Only answers saved by the server are included in the submission.</p>}
    {recoveryError && <div className="exam-alert" role="alert">{recoveryError} <button onClick={() => setRetry((value) => value + 1)}>Retry recovery check</button></div>}
    {attempt.status === 'SUBMITTED' && <p>All subjects are closed. Your exam submission is recorded. Results will be available only when released by administration.</p>}
    <dl className="submission-details">
      <div><BookOpen aria-hidden="true" /><div><dt>Subject</dt><dd><bdi>{subject.subject_name}</bdi></dd></div></div>
      <div><Timer aria-hidden="true" /><div><dt>Submission Time</dt><dd><time dateTime={subject.submitted_at!}>{timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}<span>{timestamp.toLocaleDateString()}</span></time></dd></div></div>
      <div><FileText aria-hidden="true" /><div><dt>Total Questions</dt><dd>{count ?? 'Not started'}</dd></div></div>
      <div><span className="submission-status-icon" aria-hidden="true"><Check size={20} strokeWidth={3} /></span><div><dt>Status</dt><dd>{subject.status === 'EXPIRED' ? 'Time expired' : 'Submitted'}</dd></div></div>
    </dl>
    <div className="submission-info"><Info size={23} aria-hidden="true" /><p>{next ? 'Continue when you are ready. The next subject starts only after you choose Start subject.' : 'You can now return to your candidate dashboard.'}</p></div>
    <Link className="primary-button submission-continue" to={next ? `/exam?attempt=${encodeURIComponent(attempt.id)}` : '/dashboard'}>
      {next ? `Continue to ${next.subject_name}` : 'Return to dashboard'}<ArrowRight size={19} aria-hidden="true" />
    </Link>
  </section></main>;
}
