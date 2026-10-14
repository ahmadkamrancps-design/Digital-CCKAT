export interface AdminCandidateWrite {
  email: string;
  full_name: string;
  roll_number: string;
  google_subject: string | null;
  status: "APPROVED" | "DISABLED";
}
export interface AdminCandidate extends AdminCandidateWrite {
  id: string;
  user_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
export interface AdminSubjectWrite {
  name: string;
  code: string;
  is_active: boolean;
}
export interface AdminSubject extends AdminSubjectWrite {
  id: string;
  created_at: string;
  updated_at: string;
}
export interface AdminExamWrite {
  title: string;
  description: string;
  status: "DRAFT" | "ARCHIVED";
  is_published: boolean;
  scheduled_start: string | null;
  scheduled_end: string | null;
  result_release_at: string | null;
}
export interface AdminExam extends AdminExamWrite {
  id: string;
  is_start_authorized: boolean;
  results_released: boolean;
  has_attempts: boolean;
  created_at: string;
  updated_at: string;
}
export interface AdminExamSubjectWrite {
  subject_id: string;
  duration_minutes: number;
  sequence: number;
}
export interface AdminExamSubject extends AdminExamSubjectWrite {
  id: string;
  exam_id: string;
  total_marks: string;
  question_count: number;
}
export type AdminGrading =
  | {
      mode: "EXACT";
      unicode_normalization: "NFC" | "NONE";
      trim_whitespace: boolean;
      collapse_whitespace: boolean;
      case_sensitive: boolean;
    }
  | { mode: "NUMERIC"; absolute_tolerance: string }
  | { mode: "MANUAL" };
interface QuestionBase {
  subject_id: string;
  prompt: string;
  marks: string;
  direction: "auto" | "ltr" | "rtl";
  language: string | null;
  is_active: boolean;
}
export type AdminQuestionWrite = QuestionBase &
  (
    | { type: "MCQ"; options: { text: string; is_correct: boolean }[] }
    | {
        type: "SHORT_ANSWER";
        grading: AdminGrading;
        accepted_answers: string[];
      }
  );
export interface AdminQuestion extends QuestionBase {
  id: string;
  type: "MCQ" | "SHORT_ANSWER";
  options: {
    id: string;
    text: string;
    is_correct: boolean;
    display_order: number;
  }[];
  grading: AdminGrading | null;
  accepted_answers: string[];
  created_at: string;
  updated_at: string;
}
export interface AdminPaperEntry {
  question_id: string;
  marks_override: string | null;
}
export interface AdminPaper {
  exam_subject_id: string;
  questions: (AdminPaperEntry & {
    id: string;
    sequence: number;
    effective_marks: string;
  })[];
  total_marks: string;
}
export interface AdminAssignment {
  id: string;
  candidate_id: string;
  exam_id: string;
  is_active: boolean;
  assigned_by: string;
}
export interface StaffAction {
  id: string;
  user_id: string;
  event_type: string;
  entity_id: string;
  server_timestamp: string;
}
