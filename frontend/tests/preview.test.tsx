import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider, useAuth } from '../src/features/auth/AuthProvider';

function SessionIndicator() {
  const { profile } = useAuth();
  return <output aria-label="Session state">{profile ? 'Authenticated' : 'Anonymous'}</output>;
}

function renderPreview(path: string) {
  return render(<MemoryRouter initialEntries={[path]}>
    <AuthProvider><App /><SessionIndicator /></AuthProvider>
  </MemoryRouter>);
}

beforeEach(() => {
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_ENABLE_UI_PREVIEW', 'true');
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Backend unavailable')));
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('development UI preview', () => {
  it.each([
    ['/dashboard', 'Welcome, Ahmad Kamran.'],
    ['/exam', 'Question 1 of 30'],
    ['/submission', 'Test Submitted Successfully!'],
    ['/instructions', 'Exam instructions'],
    ['/system-check', 'System check'],
    ['/profile', 'Candidate profile'],
    ['/help', 'Help & Support'],
  ])('opens %s without a backend or session', async (path, heading) => {
    renderPreview(path);
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('Development preview');
    expect(screen.getByLabelText('Session state')).toHaveTextContent('Anonymous');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    act(() => { window.dispatchEvent(new Event('online')); });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('opens the dashboard from login and provides working sidebar navigation', async () => {
    renderPreview('/');
    await userEvent.click(screen.getByRole('link', { name: 'Explore without login →' }));
    expect(screen.getByText('CCK-2026-001')).toBeInTheDocument();
    for (const [link, heading] of [
      ['My Exam', 'Question 1 of 30'],
      ['Instructions', 'Exam instructions'],
      ['System Check', 'System check'],
      ['Profile', 'Candidate profile'],
      ['Help & Support', 'Help & Support'],
    ]) {
      await userEvent.click(screen.getByRole('link', { name: link }));
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
      await userEvent.click(screen.getByRole('link', { name: 'Return to dashboard' }));
    }
    await userEvent.click(screen.getByRole('link', { name: 'View Instructions →' }));
    expect(screen.getByRole('heading', { name: 'Exam instructions' })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('requires authentication in production even if the preview flag is set', async () => {
    vi.stubEnv('DEV', false);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Sign in' }), { status: 401 })));
    renderPreview('/dashboard');
    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Explore without login →' })).not.toBeInTheDocument();
    expect(screen.queryByText('CCK-2026-001')).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/api/me', expect.anything());
  });
});
