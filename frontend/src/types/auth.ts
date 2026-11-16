export type Role = 'CANDIDATE' | 'ADMIN' | 'PROCTOR' | 'EXAMINER';

export interface SessionProfile {
  user: { id: string; email: string | null; display_name: string; role: Role };
  candidate: {
    id: string;
    roll_number: string;
    full_name: string;
    status: 'APPROVED' | 'DISABLED';
  } | null;
  csrf_token: string;
  session_expires_at: string;
}

export interface CandidateCredentials {
  roll_number: string;
  full_name: string;
  father_name: string;
}

export interface StaffCredentials {
  email: string;
  password: string;
}
