import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { AnswerQueue } from './AnswerQueue';
import { ServerDeadline } from './ServerDeadline';
import { createSession } from './createSession';
import type { SubjectPaper } from '../../types/attempt';

export interface ExamSession { queue: AnswerQueue; deadline: ServerDeadline }
interface SessionStore {
  sessions: Map<string, ExamSession>;
  csrf: { current: string };
  opening: Map<string, Promise<ExamSession>>;
  active: boolean;
  open: (attemptId: string, paper: SubjectPaper, requestedAt: number) => Promise<ExamSession>;
}
const Context = createContext<SessionStore | null>(null);

/** Account-scoped memory and disk recovery. Never authorize a session from browser storage. */
export function ExamSessions({ children }: { children: ReactNode }) {
  const { profile } = useAuth();
  const scope = profile?.user.id || '';
  return <ScopedSessions key={scope} userId={scope} csrf={profile?.csrf_token || ''}>{children}</ScopedSessions>;
}
function ScopedSessions({ children, csrf, userId }: { children: ReactNode; csrf: string; userId: string }) {
  const store = useRef<SessionStore | null>(null);
  if (!store.current) {
    const value: SessionStore = { sessions: new Map(), csrf: { current: csrf }, opening: new Map(), active: true,
      open: async (attemptId, paper, requestedAt) => {
        const key = paper.subject.id;
        const existing = value.sessions.get(key);
        if (existing) return existing;
        const opening = value.opening.get(key);
        if (opening) return opening;
        const promise = createSession({ userId, attemptId, subjectId: key }, paper, requestedAt, value.csrf)
          .then(async (session) => {
            if (!value.active) { await session.queue.dispose(); throw new Error('The session ended. Sign in again to continue.'); }
            value.sessions.set(key, session);
            return session;
          }).finally(() => value.opening.delete(key));
        value.opening.set(key, promise);
        return promise;
      },
    };
    store.current = value;
  }
  store.current.csrf.current = csrf;
  useEffect(() => {
    const value = store.current!;
    value.active = true;
    const cache = value.sessions;
    const warn = (event: BeforeUnloadEvent) => {
      if ([...cache.values()].some((session) => session.queue.dirty())) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    const online = () => { cache.forEach((session) => { void session.queue.reconnect(); }); };
    const offline = () => { cache.forEach((session) => session.queue.connectionLost()); };
    const visible = () => { if (document.visibilityState === 'visible') online(); };
    window.addEventListener('online', online); window.addEventListener('offline', offline);
    document.addEventListener('visibilitychange', visible);
    return () => {
      value.active = false;
      window.removeEventListener('beforeunload', warn);
      window.removeEventListener('online', online); window.removeEventListener('offline', offline);
      document.removeEventListener('visibilitychange', visible);
      cache.forEach((session) => { void session.queue.dispose(); }); cache.clear();
    };
  }, []);
  return <Context.Provider value={store.current}>{children}</Context.Provider>;
}
function useSessionStore() {
  const store = useContext(Context);
  if (!store) throw new Error('ExamSessions is required');
  return store;
}
export function useExamSessions() { return useSessionStore().sessions; }
export function useExamCSRF() { return useSessionStore().csrf; }
export function useOpenExamSession() { return useSessionStore().open; }
