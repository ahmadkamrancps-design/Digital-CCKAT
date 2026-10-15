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

export interface GoogleCredentialResponse {
  credential: string;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
            auto_select: boolean;
            ux_mode: 'popup';
          }) => void;
          renderButton: (element: HTMLElement, config: {
            theme: 'outline' | 'filled_blue'; size: 'large'; text: 'signin_with' | 'continue_with'; width: number;
          }) => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}
