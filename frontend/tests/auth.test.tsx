import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider } from '../src/features/auth/AuthProvider';
import type { SessionProfile } from '../src/types/auth';

// This suite isolates authentication. Live exam API requests have their own integration suite.
vi.mock('../src/services/exam', () => ({ examApi: { assigned: vi.fn(async () => []) } }));

const profile: SessionProfile = {
  user: { id: 'user-104', email: 'candidate@gmail.com', display_name: 'Test Candidate', role: 'CANDIDATE' },
  candidate: { id: 'candidate-104', full_name: 'Test Candidate', roll_number: 'CCK-104', status: 'APPROVED' },
  csrf_token: 'test-csrf', session_expires_at: '2030-01-01T12:00:00Z',
};

function response(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });
}

function renderApp(path = '/dashboard') {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
}

beforeEach(() => {
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test.apps.googleusercontent.com');
  vi.stubEnv('VITE_ENABLE_UI_PREVIEW', 'false');
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('protected dashboard', () => {
  it('loads a persisted server session on browser refresh', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(profile));
    vi.stubGlobal('fetch', fetcher);
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Candidate.' })).toBeInTheDocument();
    expect(screen.getByText('CCK-104')).toBeInTheDocument();
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.queryByText('Ahmad Kamran')).not.toBeInTheDocument();
    expect(await screen.findByText(/No active exam is available/)).toBeInTheDocument();
    expect(screen.queryByText('Design preview')).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith('/api/me', expect.objectContaining({ credentials: 'same-origin' }));
  });

  it('redirects an anonymous candidate to sign-in', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Please sign in.' }, 401)));
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(screen.queryByText('CCK-104')).not.toBeInTheDocument();
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });

  it('shows a retry when the backend is unavailable', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce(response(profile));
    vi.stubGlobal('fetch', fetcher);
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Unable to confirm access' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
  });

  it('signs out with CSRF protection and returns to login', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    const fetcher = vi.fn().mockResolvedValueOnce(response(profile)).mockResolvedValueOnce(response(null, 204));
    vi.stubGlobal('fetch', fetcher);
    renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(fetcher).toHaveBeenLastCalledWith('/api/auth/logout', expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf' }),
    }));
  });

  it('keeps the dashboard visible if sign-out cannot reach the server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(profile)).mockRejectedValueOnce(new TypeError('network')));
    renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
    expect(screen.getByText('CCK-104')).toBeInTheDocument();
  });

  it('does not claim sign-out succeeded when CSRF validation fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(profile))
      .mockResolvedValueOnce(response({ detail: 'Refresh and try again.' }, 403)));
    renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh and try again');
    expect(screen.getByText('CCK-104')).toBeInTheDocument();
  });

  it('does not restore a signed-out profile from a delayed session check', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    let finishLogout!: (value: Response) => void;
    let finishRefresh!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(profile))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishLogout = resolve; }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishRefresh = resolve; })));
    renderApp();
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    act(() => { window.dispatchEvent(new Event('online')); });
    await act(async () => { finishLogout(response(null, 204)); });
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    await act(async () => { finishRefresh(response(profile)); });
    expect(screen.getByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(screen.queryByText('CCK-104')).not.toBeInTheDocument();
  });
});

describe('staff password sign-in', () => {
  async function fillStaffDetails() {
    await userEvent.type(await screen.findByLabelText('Email address'), 'staff@cck.edu.pk');
    await userEvent.type(screen.getByLabelText('Password'), 'A long staff passphrase');
  }

  it('signs in without Google and keeps credentials out of browser storage', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    const staff = { ...profile, user: { ...profile.user, role: 'PROCTOR' }, candidate: null };
    const fetcher = vi.fn().mockResolvedValueOnce(response({ detail: 'Sign in' }, 401))
      .mockResolvedValueOnce(response(staff));
    vi.stubGlobal('fetch', fetcher);
    renderApp('/admin/login');
    await fillStaffDetails();
    expect(screen.queryByRole('button', { name: 'Continue with Google' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Roll number')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in to staff portal' }));
    expect(await screen.findByRole('heading', { name: 'Staff workspace' })).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith('/api/auth/staff', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ email: 'staff@cck.edu.pk', password: 'A long staff passphrase' }),
    }));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('offers the same password form beneath candidate sign-in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Sign in' }, 401)));
    renderApp('/');
    await userEvent.click(await screen.findByText('Staff sign-in'));
    expect(await screen.findByLabelText('Email address')).toBeVisible();
    expect(screen.getByLabelText('Roll number')).toBeVisible();
  });

  it('shows login errors and clears the rejected password', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response({ detail: 'Sign in' }, 401))
      .mockResolvedValueOnce(response({ detail: 'Unable to sign in. Check your email and password.' }, 401)));
    renderApp('/admin');
    await fillStaffDetails();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in to staff portal' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Check your email and password');
    expect(screen.getByLabelText('Email address')).toHaveValue('staff@cck.edu.pk');
    expect(screen.getByLabelText('Password')).toHaveValue('');
    expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument();
  });
});

describe('admissions candidate sign-in', () => {
  async function fillDetails() {
    await userEvent.type(await screen.findByLabelText('Roll number'), 'CCK-104');
    await userEvent.type(screen.getByLabelText('Full name'), 'Test Candidate');
    await userEvent.type(screen.getByLabelText('Father’s name'), 'Test Father');
  }

  it('signs in without Google or email and restores the dashboard after refresh', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    const approved = { ...profile, user: { ...profile.user, email: null } };
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response(approved)))
      .mockResolvedValueOnce(response({ detail: 'Sign in' }, 401));
    vi.stubGlobal('fetch', fetcher);
    const view = renderApp('/');
    await fillDetails();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith('/api/auth/candidate', expect.objectContaining({
      method: 'POST', credentials: 'same-origin',
      body: JSON.stringify({ roll_number: 'CCK-104', full_name: 'Test Candidate', father_name: 'Test Father' }),
    }));
    expect(screen.queryByText('Registered email:')).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    view.unmount();
    renderApp('/dashboard');
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
    expect(fetcher).toHaveBeenLastCalledWith('/api/me', expect.anything());
  });

  it.each([
    [401, 'Unable to sign in. Check your admissions details or contact admissions.'],
    [429, 'Too many sign-in attempts. Please wait before trying again.'],
    [503, 'Service temporarily unavailable.'],
  ])('preserves details and shows the server error for HTTP %s', async (status, detail) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response({ detail: 'Sign in' }, 401))
      .mockResolvedValueOnce(response({ detail }, status)));
    renderApp('/');
    await fillDetails();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(detail);
    expect(screen.getByLabelText('Roll number')).toHaveValue('CCK-104');
    expect(screen.getByLabelText('Father’s name')).toHaveValue('Test Father');
    expect(screen.queryByRole('heading', { name: 'Welcome, Test Candidate.' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });

  it('requires all three fields and prevents duplicate submits while verifying', async () => {
    let finish!: (value: Response) => void;
    const fetcher = vi.fn().mockResolvedValueOnce(response({ detail: 'Sign in' }, 401))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal('fetch', fetcher);
    renderApp('/');
    const button = await screen.findByRole('button', { name: 'Sign in' });
    await userEvent.click(button);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await fillDetails();
    await userEvent.dblClick(button);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Verifying…' })).toBeDisabled();
    await act(async () => { finish(response(profile)); });
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
  });
});

describe('candidate page scaffolds', () => {
  it.each(['/exam', '/submission'])('requires a session for %s', async (path) => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Please sign in.' }, 401)));
    renderApp(path);
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Submission status' })).not.toBeInTheDocument();
  });

  it.each(['/exam', '/submission'])('returns staff visiting %s to their dashboard', async (path) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      ...profile,
      user: { ...profile.user, role: 'PROCTOR' },
      candidate: null,
    })));
    renderApp(path);
    expect(await screen.findByRole('heading', { name: 'Staff workspace' })).toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Candidate navigation' })).not.toBeInTheDocument();
  });

  it('does not show a submission confirmation without a server receipt', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(profile)));
    renderApp('/submission');
    expect(await screen.findByText('There is no confirmed submission to display.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Return to dashboard' }));
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
  });

  it('does not start a mock exam for an approved candidate', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(profile));
    vi.stubGlobal('fetch', fetcher);
    renderApp('/exam');
    expect(await screen.findByText(/No active exam is available/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /start/i })).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith('/api/me', expect.anything());
  });
});

describe('application routing', () => {
  it('renders the login design while the session request is still pending', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    let finishSession!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => {
      finishSession = resolve;
    })));
    renderApp('/');
    expect(screen.getByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveClass('login-page');
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session');
    expect(screen.queryByText('Candidate portal')).not.toBeInTheDocument();
    await act(async () => { finishSession(response({ detail: 'Please sign in.' }, 401)); });
    expect(await screen.findByRole('form', { name: 'Candidate sign-in' })).toBeInTheDocument();
  });

  it('keeps the login design visible on connection failure and allows retry', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce(response({ detail: 'Please sign in.' }, 401)));
    renderApp('/');
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
    expect(screen.getByRole('main')).toHaveClass('login-page');
    expect(screen.queryByText('CCK-104')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('form', { name: 'Candidate sign-in' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each(['/', '/login', '/missing-page'])('opens the canonical login from %s', async (path) => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Please sign in.' }, 401)));
    const router = createMemoryRouter([
      { path: '*', element: <AuthProvider><App /></AuthProvider> },
    ], { initialEntries: [path] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');
    expect(screen.getAllByRole('main')).toHaveLength(1);
  });

  it('opens the dashboard for an existing approved session visiting home', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(profile)));
    const router = createMemoryRouter([
      { path: '*', element: <AuthProvider><App /></AuthProvider> },
    ], { initialEntries: ['/'] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByText('CCK-104')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });
});
