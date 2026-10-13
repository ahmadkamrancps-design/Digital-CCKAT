import type { SessionProfile } from '../../types/auth';

/** Vite removes the development branch from production builds. */
export function uiPreviewEnabled(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_ENABLE_UI_PREVIEW === 'true';
}

/** Display data only. This object deliberately contains no session or CSRF credentials. */
export const previewCandidate: Pick<SessionProfile, 'user' | 'candidate'> = {
  user: {
    id: 'preview-user',
    email: 'candidate@example.com',
    display_name: 'Ahmad Kamran',
    role: 'CANDIDATE',
  },
  candidate: {
    id: 'preview-candidate',
    full_name: 'Ahmad Kamran',
    roll_number: 'CCK-2026-001',
    status: 'APPROVED',
  },
};
