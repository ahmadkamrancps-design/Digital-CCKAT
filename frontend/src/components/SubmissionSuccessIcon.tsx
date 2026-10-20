interface Props {
  animate?: boolean;
}

/** Decorative feedback only; the receipt heading communicates submission status. */
export function SubmissionSuccessIcon({ animate = true }: Props) {
  return <div className={`submission-success-icon${animate ? ' is-animated' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 76 76" focusable="false">
      <circle className="submission-success-ring" cx="38" cy="38" r="36" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle className="submission-success-disc" cx="38" cy="38" r="38" fill="currentColor" />
      <path className="submission-success-check" d="M22 39 33 50 55 27" pathLength="1" fill="none" stroke="white" strokeWidth="5.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </div>;
}
