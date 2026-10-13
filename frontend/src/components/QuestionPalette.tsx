import { Bookmark } from 'lucide-react';
import type { QuestionNavigationItem } from '../types/exam';

interface QuestionPaletteProps {
  questions: readonly QuestionNavigationItem[];
  currentQuestionId: string | null;
  onNavigate: (questionId: string) => void;
  disabled?: boolean;
}

export function QuestionPalette({ questions, currentQuestionId, onNavigate, disabled = false }: QuestionPaletteProps) {
  return <nav className="question-palette" aria-label="Question overview">
    <h2>Questions</h2>
    <ul className="question-legend" aria-label="Question status legend">
      <li><span className="legend-dot answered-dot" aria-hidden="true" />Answered</li>
      <li><span className="legend-dot unanswered-dot" aria-hidden="true" />Not Answered</li>
      <li><span className="legend-dot review-dot" aria-hidden="true" />Marked for Review</li>
    </ul>
    <ol className="question-list">
      {questions.map((question) => <li key={question.id}>
        <button
          type="button"
          className={`question-button${question.isAnswered ? ' is-answered' : ''}${question.isMarkedForReview ? ' is-marked' : ''}`}
          aria-current={question.id === currentQuestionId ? 'step' : undefined}
          aria-label={`Question ${question.number}, ${question.isAnswered ? 'answered' : 'unanswered'}${question.isMarkedForReview ? ', marked for review' : ''}`}
          disabled={disabled}
          onClick={() => onNavigate(question.id)}
        >
          {question.number}
          {question.isMarkedForReview && <Bookmark size={12} aria-hidden="true" />}
        </button>
      </li>)}
    </ol>
  </nav>;
}
