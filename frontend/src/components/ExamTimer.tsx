interface ExamTimerProps {
  /** Display input must be calculated from authoritative server timestamps. */
  remainingSeconds: number | null;
  label?: string;
}

/** Presentation only: never starts, resets, extends, or submits an attempt. */
export function ExamTimer({ remainingSeconds, label = 'Time remaining' }: ExamTimerProps) {
  const known = remainingSeconds !== null && Number.isFinite(remainingSeconds);
  const seconds = known ? Math.max(0, Math.ceil(remainingSeconds)) : 0;
  const minutes = Math.floor(seconds / 60);
  const display = known
    ? `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
    : 'Time unavailable';
  return <div className="exam-timer">
    <span className="timer-label">{label}</span>
    <span role="timer" aria-live="off" aria-label={label}>{display}</span>
  </div>;
}
