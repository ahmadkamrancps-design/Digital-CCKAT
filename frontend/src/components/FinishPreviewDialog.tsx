import { useEffect, useRef } from 'react';

interface Props {
  subjectName: string;
  unansweredCount: number;
  onCancel: () => void;
  onConfirm: () => void;
}

export function FinishPreviewDialog({ subjectName, unansweredCount, onCancel, onConfirm }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); };
  }, []);
  return <dialog ref={dialog} className="finish-dialog" aria-labelledby="finish-title" aria-describedby="finish-description" onCancel={onCancel}>
    <h2 id="finish-title">Finish {subjectName} preview?</h2>
    <p id="finish-description">{unansweredCount} unanswered {unansweredCount === 1 ? 'question' : 'questions'}.
      {' '}This ends the sample subject on this page. Responses are not submitted to CCK.</p>
    <div className="finish-dialog-actions">
      <button className="secondary-button" type="button" onClick={onCancel}>Keep reviewing</button>
      <button className="primary-button" type="button" onClick={onConfirm}>Finish preview</button>
    </div>
  </dialog>;
}
