export interface Grade {
  id: string;
  answer_id: string;
  revision: number;
  marks_awarded: string;
  maximum_marks: string;
  method: string;
  graded_by: string | null;
  graded_at: string;
  notes: string;
}
export interface GradingExam {
  id: string;
  title: string;
  results_released: boolean;
}
export interface ExaminerStaff {
  id: string;
  display_name: string;
}
export interface ExaminerAssignment {
  user_id: string;
  display_name: string;
  is_active: boolean;
}
export interface ManualResponse {
  answer_id: string;
  attempt_id: string;
  subject_name: string;
  question_number: number;
  prompt: string;
  direction: "auto" | "ltr" | "rtl";
  answer_text: string;
  maximum_marks: string;
  current_grade: Grade | null;
}
export interface SubjectResult {
  subject_name: string;
  sequence: number;
  maximum_marks: string;
  marks_awarded: string | null;
  pending_answers: number;
}
export interface AttemptResult {
  attempt_id: string;
  exam_id: string;
  exam_title: string;
  grading_status: "PENDING" | "COMPLETE";
  publication_status: "WITHHELD" | "SCHEDULED" | "RELEASED";
  subjects: SubjectResult[];
  maximum_marks: string | null;
  marks_awarded: string | null;
  percentage: string | null;
}
export interface GradingAttempt {
  attempt_id: string;
  roll_number: string;
  full_name: string;
  status: string;
  grading_status: "PENDING" | "COMPLETE";
  pending_answers: number;
  marks_awarded: string | null;
  maximum_marks: string;
}
