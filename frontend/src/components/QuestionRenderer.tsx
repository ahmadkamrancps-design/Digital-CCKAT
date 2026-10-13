import type { ExamQuestion } from '../types/exam';

interface Props {
  question: ExamQuestion;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  eliminated?: readonly string[];
  onEliminate?: (id: string) => void;
}

export function QuestionRenderer({ question, value, onChange, disabled = false, eliminated = [], onEliminate }: Props) {
  const promptId = `prompt-${question.id}`;
  const hintId = `hint-${question.id}`;
  return <div className="question-body" lang={question.language} dir={question.direction || 'auto'}>
    <h2 className="question-prompt" id={promptId}>{question.prompt}</h2>
    {question.expression && <p className="math-expression" dir="ltr">{question.expression}</p>}
    {question.type === 'MCQ'
      ? <fieldset className="mcq-options" aria-labelledby={promptId} disabled={disabled}>
        {question.options.map((option, index) => <div key={option.id} className="mcq-option-row"><label
          className={`mcq-option${value === option.id ? ' is-selected' : ''}${eliminated.includes(option.id) ? ' is-eliminated' : ''}`}
        >
          <input
            type="radio"
            name={`answer-${question.id}`}
            value={option.id}
            checked={value === option.id}
            onChange={() => onChange(option.id)}
          />
          <span className="option-letter" aria-hidden="true">{String.fromCharCode(65 + index)}</span>
          <span>{option.text}</span>
        </label>{onEliminate && <button className="eliminate-option" type="button" disabled={disabled}
          aria-label={`Cross out option ${String.fromCharCode(65 + index)}`} aria-pressed={eliminated.includes(option.id)}
          onClick={() => onEliminate(option.id)}>{eliminated.includes(option.id) ? 'Undo' : '×'}</button>}</div>)}
      </fieldset>
      : <div className="short-answer-control">
        <label className="sr-only" htmlFor={`answer-${question.id}`}>Your answer</label>
        <input
          id={`answer-${question.id}`}
          type="text"
          inputMode={question.inputMode || 'text'}
          value={value}
          maxLength={question.maxLength || 200}
          aria-describedby={`${promptId} ${hintId}`}
          disabled={disabled}
          autoComplete="off"
          spellCheck={false}
          dir={question.direction || 'auto'}
          onChange={(event) => onChange(event.target.value)}
        />
        <p id={hintId}>{question.inputMode === 'decimal' ? 'Enter your answer as a number.' : 'Type a short answer.'}</p>
      </div>}
  </div>;
}
