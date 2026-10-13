/** Explicit candidate API contracts. No answer keys or grading configuration. */
export interface AssignedExam {
  exam_id: string;
  title: string;
  is_start_authorized: boolean;
  scheduled_start: string | null;
  scheduled_end: string | null;
  attempt_id: string | null;
  subjects: { exam_subject_id: string; name: string; duration_minutes: number; sequence: number }[];
}

export interface SubjectAttempt {
  id: string;
  exam_subject_id: string;
  subject_name: string;
  sequence: number;
  duration_minutes: number;
  status: 'NOT_STARTED' | 'ACTIVE' | 'SUBMITTED' | 'EXPIRED';
  started_at: string | null;
  expires_at: string | null;
  submitted_at: string | null;
}

export interface Attempt {
  id: string;
  exam_id: string;
  status: 'IN_PROGRESS' | 'SUBMITTED';
  started_at: string;
  submitted_at: string | null;
  server_time: string;
  subjects: SubjectAttempt[];
}

export interface AnswerFields {
  selected_option_id: string | null;
  short_answer_text: string | null;
  is_marked_for_review: boolean;
}
export interface Answer extends AnswerFields {
  exam_question_id: string;
  revision: number;
  last_saved_at: string | null;
}
export interface AnswerWrite extends AnswerFields { expected_revision: number }
export interface AnswerSaved { answer: Answer; server_time: string }

export interface CandidateQuestion {
  exam_question_id: string;
  question_id: string;
  type: 'MCQ' | 'SHORT_ANSWER';
  prompt: string;
  direction: 'auto' | 'ltr' | 'rtl';
  language: string | null;
  marks: string;
  sequence: number;
  options: { id: string; text: string }[];
  answer: Answer;
}
export interface SubjectPaper {
  subject: SubjectAttempt;
  server_time: string;
  questions: CandidateQuestion[];
}
