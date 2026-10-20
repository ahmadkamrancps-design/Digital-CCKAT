import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider } from '../src/features/auth/AuthProvider';
import type { SessionProfile } from '../src/types/auth';
import type { AssignedExam } from '../src/types/attempt';

const profile: SessionProfile = {
  user: { id: 'guide-user', email: null, display_name: 'Registered Candidate', role: 'CANDIDATE' },
  candidate: { id: 'guide-candidate', full_name: 'Registered Candidate', roll_number: 'CCK-GUIDE-104', status: 'APPROVED' },
  csrf_token: 'guide-test-csrf', session_expires_at: '2030-01-01T12:00:00Z',
};
const assigned: AssignedExam[] = [{
  exam_id: 'guide-exam', title: 'Assigned Admission Paper', is_start_authorized: false,
  scheduled_start: null, scheduled_end: null, attempt_id: null,
  subjects: [{ exam_subject_id: 'guide-subject', name: 'Configured Language Paper', duration_minutes: 45, sequence: 1 }],
}];
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

beforeEach(() => vi.stubEnv('VITE_ENABLE_UI_PREVIEW', 'false'));
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

function renderPage(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
}

it('shows the actual assigned subjects and durations on instructions without starting an attempt', async () => {
  const fetcher = vi.fn(async (path: string, options: RequestInit = {}) => {
    if (options.method && options.method !== 'GET') throw new Error('Guidance must not start or change an attempt');
    if (path === '/api/me') return response(profile);
    if (path === '/api/candidate/exams') return response(assigned);
    throw new Error('Unexpected guidance request');
  });
  vi.stubGlobal('fetch', fetcher);
  renderPage('/instructions');
  expect(await screen.findByText('Configured Language Paper')).toBeInTheDocument();
  expect(screen.getByText('45 Minutes')).toBeInTheDocument();
  expect(screen.getByText('Waiting for start authorization')).toBeInTheDocument();
  expect(screen.queryByText('60 minutes')).not.toBeInTheDocument();
  expect(fetcher.mock.calls.map(([path]) => path).sort()).toEqual(['/api/candidate/exams', '/api/me']);
});

it('shows only the signed-in candidate record and keeps registration corrections with admissions', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(profile)));
  renderPage('/profile');
  expect(await screen.findByText('CCK-GUIDE-104')).toBeInTheDocument();
  expect(screen.getByText('Registered Candidate')).toBeInTheDocument();
  expect(screen.getByText('Approved')).toBeInTheDocument();
  expect(screen.queryByText('Ahmad Kamran')).not.toBeInTheDocument();
  expect(screen.queryByText('candidate@example.com')).not.toBeInTheDocument();
  expect(screen.getByText(/Your father’s name is not displayed/)).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
