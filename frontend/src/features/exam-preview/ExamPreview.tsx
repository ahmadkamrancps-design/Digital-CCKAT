import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Bookmark } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { ExamHeader } from '../../components/ExamHeader';
import { FinishPreviewDialog } from '../../components/FinishPreviewDialog';
import { QuestionPalette } from '../../components/QuestionPalette';
import { QuestionRenderer } from '../../components/QuestionRenderer';
import { mockExam } from '../../data/mockExam';
import { SubmissionPreview } from './SubmissionPreview';

interface PreviewResponse {
  value: string;
  marked: boolean;
}

/** Local interaction state only: no storage, requests, deadlines, grading, or server submission. */
export function ExamPreview() {
  const [params, setParams] = useSearchParams();
  const subject = mockExam.subjects.find((item) => item.id === params.get('subject')) || mockExam.subjects[0];
  const [positions, setPositions] = useState<Record<string, number>>({});
  const [responses, setResponses] = useState<Record<string, PreviewResponse>>({});
  const [finishedSubjects, setFinishedSubjects] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const index = positions[subject.id] || 0;
  const question = subject.questions[index];
  const response = responses[question.id] || { value: '', marked: false };
  const finished = finishedSubjects.includes(subject.id);
  const navigation = subject.questions.map((item, itemIndex) => ({
    id: item.id, number: itemIndex + 1,
    isAnswered: !!responses[item.id]?.value.trim(),
    isMarkedForReview: !!responses[item.id]?.marked,
  }));
  const answeredCount = navigation.filter((item) => item.isAnswered).length;
  const reviewCount = navigation.filter((item) => item.isMarkedForReview).length;

  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [subject.id, index, finished]);

  function navigate(nextIndex: number) {
    setPositions((current) => ({ ...current, [subject.id]: nextIndex }));
  }

  function changeAnswer(value: string) {
    setResponses((current) => ({
      ...current,
      [question.id]: { value, marked: current[question.id]?.marked || false },
    }));
  }

  function resetSubject() {
    const ids = new Set(subject.questions.map((item) => item.id));
    setResponses((current) => Object.fromEntries(Object.entries(current).filter(([id]) => !ids.has(id))));
    setFinishedSubjects((current) => current.filter((id) => id !== subject.id));
    navigate(0);
  }

  if (finished) {
    const nextSubject = mockExam.subjects[mockExam.subjects.findIndex((item) => item.id === subject.id) + 1];
    return <SubmissionPreview
      subject={subject}
      nextSubject={nextSubject}
      answeredCount={answeredCount}
      reviewCount={reviewCount}
      onRestart={resetSubject}
      onContinue={nextSubject ? () => setParams({ subject: nextSubject.id }) : undefined}
    />;
  }

  return <main className="exam-shell" id="main" tabIndex={-1}>
    <ExamHeader
      subjects={mockExam.subjects}
      subjectId={subject.id}
      onSubjectChange={(id) => { setConfirming(false); setParams({ subject: id }); }}
      remainingSeconds={subject.durationMinutes * 60}
      onFinish={() => setConfirming(true)}
      finished={finished}
    />
    <div className="exam-workspace">
      <aside className="exam-question-sidebar">
        <QuestionPalette
          questions={navigation}
          currentQuestionId={question.id}
          onNavigate={(id) => navigate(subject.questions.findIndex((item) => item.id === id))}
          disabled={finished}
        />
        <Link className="exam-dashboard-link" to="/dashboard">Return to dashboard</Link>
      </aside>
      <section className="exam-question-area" aria-labelledby="question-heading">
          <div className="question-toolbar">
            <h1 ref={heading} tabIndex={-1} id="question-heading">Question {index + 1} of {subject.questions.length}</h1>
            <button
              className={`review-button${response.marked ? ' is-marked' : ''}`}
              type="button"
              aria-pressed={response.marked}
              onClick={() => setResponses((current) => ({
                ...current,
                [question.id]: { value: current[question.id]?.value || '', marked: !current[question.id]?.marked },
              }))}
            ><Bookmark size={17} aria-hidden="true" /> Mark for Review</button>
          </div>
          <div className="exam-question-card">
            <QuestionRenderer question={question} value={response.value} onChange={changeAnswer} />
            <button className="clear-answer-button" type="button" onClick={() => changeAnswer('')} disabled={!response.value}>Clear Answer</button>
            <div className="question-navigation">
              <button className="secondary-button" type="button" onClick={() => navigate(index - 1)} disabled={index === 0}>
                <ArrowLeft size={18} aria-hidden="true" /> Previous
              </button>
              <button className="primary-button" type="button" onClick={() => navigate(index + 1)} disabled={index === subject.questions.length - 1}>
                Next <ArrowRight size={18} aria-hidden="true" />
              </button>
            </div>
          </div>
        <p className="exam-preview-storage-note" role="status">Preview responses stay on this page only. Refresh resets them.</p>
      </section>
    </div>
    {confirming && <FinishPreviewDialog
      subjectName={subject.name}
      unansweredCount={subject.questions.length - answeredCount}
      onCancel={() => setConfirming(false)}
      onConfirm={() => {
        setFinishedSubjects((current) => [...current, subject.id]);
        setConfirming(false);
      }}
    />}
  </main>;
}
