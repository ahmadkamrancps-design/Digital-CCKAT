/** Candidate-facing question shapes. Answer keys and grading rules belong on the server. */
export interface QuestionBase {
  id: string;
  prompt: string;
  marks: number;
  direction?: 'auto' | 'ltr' | 'rtl';
  language?: string;
  /** Plain text notation only; never interpreted as administrator-supplied HTML. */
  expression?: string;
}

export interface MCQQuestion extends QuestionBase {
  type: 'MCQ';
  options: readonly { id: string; text: string }[];
}

export interface ShortAnswerQuestion extends QuestionBase {
  type: 'SHORT_ANSWER';
  maxLength?: number;
  inputMode?: 'text' | 'decimal';
}

export type ExamQuestion = MCQQuestion | ShortAnswerQuestion;

export interface ExamSubjectPreview {
  id: string;
  name: string;
  durationMinutes: number;
  questions: readonly ExamQuestion[];
}

/** Local UI fixture only; this is not an assigned exam or an authorized attempt. */
export interface ExamPreview {
  id: string;
  title: string;
  subjects: readonly ExamSubjectPreview[];
}

export interface QuestionNavigationItem {
  id: string;
  number: number;
  isAnswered: boolean;
  isMarkedForReview: boolean;
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'offline' | 'error';
