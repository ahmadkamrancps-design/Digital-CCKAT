import { useEffect, useRef } from 'react';
import { ArrowRight, BookOpen, Check, FileText, Info, Timer } from 'lucide-react';
import { Link } from 'react-router-dom';
import CCKLogo from '../../components/CCKLogo';
import { SubmissionSuccessIcon } from '../../components/SubmissionSuccessIcon';
import type { ExamSubjectPreview } from '../../types/exam';

interface Props {
  subject: ExamSubjectPreview;
  nextSubject?: ExamSubjectPreview;
  onContinue?: () => void;
  onRestart?: () => void;
  answeredCount?: number;
  reviewCount?: number;
}

/** Design preview only. Never used as evidence of a server-confirmed submission. */
export function SubmissionPreview({ subject, nextSubject, onContinue, onRestart, answeredCount, reviewCount }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [subject.id]);
  const continueLabel = nextSubject ? `Continue to ${nextSubject.name}` : 'Return to dashboard';

  return <main className="submission-page" id="main" tabIndex={-1}>
    <section className="submission-card" aria-labelledby="submission-heading">
      <div className="submission-brand">
        <CCKLogo size={74} />
        <div><strong className="cck-serif">Cadet College Kohat</strong><span>Online Entry Test 2026</span></div>
      </div>
      <SubmissionSuccessIcon key={subject.id} />
      <h1 ref={heading} tabIndex={-1} id="submission-heading">Test Submitted Successfully!</h1>
      <p className="submission-intro">{nextSubject ? 'Please continue to the next subject.' : 'You have reached the end of the subject preview.'}</p>
      <p className="submission-preview-label">Design preview — no test has been submitted to CCK.</p>

      <dl className="submission-details">
        <div><BookOpen aria-hidden="true" /><div><dt>Subject</dt><dd>{subject.name}</dd></div></div>
        <div><Timer aria-hidden="true" /><div><dt>Sample Submission Time</dt><dd>10:02 AM<span>15 March 2026</span></dd></div></div>
        <div><FileText aria-hidden="true" /><div><dt>Total Questions</dt><dd>{subject.questions.length}</dd></div></div>
        <div><span className="submission-status-icon" aria-hidden="true"><Check size={20} strokeWidth={3} /></span><div><dt>Status</dt><dd>Submitted<span>Preview only</span></dd></div></div>
      </dl>

      <div className="submission-info"><Info size={23} aria-hidden="true" /><p>
        {nextSubject ? 'Continue when you are ready for the next subject.' : 'You can return to your candidate dashboard.'}
        <br />This preview does not save or submit answers.
      </p></div>

      {nextSubject && onContinue
        ? <button type="button" className="primary-button submission-continue" onClick={onContinue}>{continueLabel}<ArrowRight size={19} aria-hidden="true" /></button>
        : <Link className="primary-button submission-continue" to={nextSubject ? `/exam?subject=${nextSubject.id}` : '/dashboard'}>{continueLabel}<ArrowRight size={19} aria-hidden="true" /></Link>}

      {answeredCount !== undefined && <p className="submission-answer-summary">{answeredCount} of {subject.questions.length} questions answered · {reviewCount ?? 0} marked for review.</p>}
      {onRestart && <button type="button" className="submission-restart" onClick={onRestart}>Restart subject preview</button>}
    </section>
  </main>;
}
