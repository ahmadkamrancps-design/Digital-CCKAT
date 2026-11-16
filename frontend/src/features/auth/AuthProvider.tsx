import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../../services/api';
import type { CandidateCredentials, SessionProfile, StaffCredentials } from '../../types/auth';
import { uiPreviewEnabled } from '../preview/preview';
import { clearUserRecovery } from '../../storage/recovery';

interface AuthState {
  isPreview: boolean;
  profile: SessionProfile | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  signInCandidate: (credentials: CandidateCredentials) => Promise<void>;
  signInStaff: (credentials: StaffCredentials) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const isPreview = uiPreviewEnabled();
  const [profile, setProfile] = useState<SessionProfile | null>(null);
  const [loading, setLoading] = useState(!isPreview);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const currentProfile = useRef(profile);
  currentProfile.current = profile;

  const refresh = useCallback(async () => {
    if (isPreview) {
      setProfile(null);
      setLoading(false);
      setError(null);
      return;
    }
    const version = ++requestVersion.current;
    setLoading(!currentProfile.current);
    setError(null);
    try {
      const result = await api<SessionProfile>('/me');
      if (version === requestVersion.current) setProfile(result);
    } catch (cause) {
      if (version !== requestVersion.current) return;
      if (cause instanceof ApiError && [401, 403].includes(cause.status)) setProfile(null);
      if (!(cause instanceof ApiError && cause.status === 401)) {
        setError(cause instanceof Error ? cause.message : 'Unable to check your session.');
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [isPreview]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    // Revalidate server access when returning to the dashboard or regaining a connection.
    const revalidate = () => { if (document.visibilityState === 'visible') void refresh(); };
    window.addEventListener('online', revalidate);
    document.addEventListener('visibilitychange', revalidate);
    return () => {
      window.removeEventListener('online', revalidate);
      document.removeEventListener('visibilitychange', revalidate);
    };
  }, [refresh]);

  const signInCandidate = useCallback(async (credentials: CandidateCredentials) => {
    if (isPreview) throw new Error('Disable UI preview before signing in.');
    const result = await api<SessionProfile>('/auth/candidate', {
      method: 'POST', body: JSON.stringify(credentials),
    });
    ++requestVersion.current;
    setLoading(false);
    setError(null);
    setProfile(result);
  }, [isPreview]);

  const signOut = useCallback(async () => {
    if (isPreview || !profile) return;
    try {
      await api<void>('/auth/logout', {
        method: 'POST', headers: { 'X-CSRF-Token': profile.csrf_token },
      });
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.status === 401)) throw cause;
      // An expired session no longer has server access. A CSRF failure must be shown.
    }
    const version = ++requestVersion.current;
    setLoading(false);
    setProfile(null);
    setError(null);
    try { await clearUserRecovery(profile.user.id); }
    catch {
      if (version === requestVersion.current) setError('You are signed out, but local recovery copies could not be cleared. Contact your proctor before sharing this device.');
    }
  }, [isPreview, profile]);

  const signInStaff = useCallback(async (credentials: StaffCredentials) => {
    if (isPreview) throw new Error('Disable UI preview before signing in.');
    const result = await api<SessionProfile>('/auth/staff', {
      method: 'POST', body: JSON.stringify(credentials),
    });
    ++requestVersion.current;
    setLoading(false);
    setError(null);
    setProfile(result);
  }, [isPreview]);

  return <AuthContext.Provider value={{ isPreview, profile, loading, error, refresh, signInCandidate, signInStaff, signOut }}>
    {children}
  </AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is required');
  return value;
}
