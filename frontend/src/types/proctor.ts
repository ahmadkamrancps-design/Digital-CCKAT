export type ClientEventType =
  | "CONNECTION_LOST"
  | "CONNECTION_RESTORED"
  | "VISIBILITY_HIDDEN"
  | "VISIBILITY_VISIBLE"
  | "FULLSCREEN_EXIT"
  | "FULLSCREEN_ENTER";
export interface ClientEvent {
  event_id: string;
  event_type: ClientEventType;
}
export interface PresenceWrite {
  subject_attempt_id: string;
  question_sequence: number;
  events: ClientEvent[];
}
export interface ProctorStaff {
  id: string;
  display_name: string;
}
export interface ProctorAssignment {
  user_id: string;
  display_name: string;
  is_active: boolean;
  user_is_active: boolean;
}
export interface MonitoredExam {
  id: string;
  title: string;
  is_start_authorized: boolean;
  scheduled_start: string | null;
  scheduled_end: string | null;
}
export interface MonitoredCandidate {
  candidate_id: string;
  roll_number: string;
  full_name: string;
  access_active: boolean;
  attempt_id: string | null;
  state: "NOT_STARTED" | "TESTING" | "BETWEEN_SUBJECTS" | "SUBMITTED";
  subject_attempt_id: string | null;
  subject_name: string | null;
  subject_status: "NOT_STARTED" | "ACTIVE" | "SUBMITTED" | "EXPIRED" | null;
  question_count: number;
  reported_question_sequence: number | null;
  expires_at: string | null;
  remaining_seconds: number | null;
  connection: "ONLINE" | "NO_RECENT_CONTACT" | "UNKNOWN";
  last_seen_at: string | null;
  review_event_count: number;
}
export interface MonitoringResponse {
  server_time: string;
  candidates: MonitoredCandidate[];
}
export interface SessionEvent {
  id: string;
  event_type:
    | ClientEventType
    | "EXAM_OPENED"
    | "SUBJECT_STARTED"
    | "ANSWER_SAVED"
    | "QUESTION_FLAGGED"
    | "QUESTION_UNFLAGGED"
    | "SUBJECT_SUBMITTED"
    | "SUBJECT_AUTO_SUBMITTED"
    | "EXAM_SUBMITTED";
  source: "SERVER" | "CLIENT";
  subject_attempt_id: string | null;
  server_timestamp: string;
}
