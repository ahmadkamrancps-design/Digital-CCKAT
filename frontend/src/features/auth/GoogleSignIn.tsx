import { useEffect, useRef, useState } from 'react';
import { useAuth } from './AuthProvider';

let scriptPromise: Promise<void> | null = null;

function loadGoogle(): Promise<void> {
  if (window.google) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      scriptPromise = null;
      reject(new Error('Google sign-in could not load. Check your connection and retry.'));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export function GoogleSignIn() {
  const container = useRef<HTMLDivElement>(null);
  const { signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [ready, setReady] = useState(false);
  const [retry, setRetry] = useState(0);
  const inFlight = useRef(false);
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

  useEffect(() => {
    if (!clientId) return;
    let active = true;
    setError(null);
    setReady(false);
    void loadGoogle().then(() => {
      if (!active || !container.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: clientId, auto_select: false, ux_mode: 'popup',
        callback: (response) => {
          if (!active || inFlight.current) return;
          inFlight.current = true;
          setPending(true);
          setError(null);
          void signIn(response.credential).catch((cause: unknown) => {
            if (active) setError(cause instanceof Error ? cause.message : 'Sign-in failed. Try again.');
          }).finally(() => {
            inFlight.current = false;
            if (active) setPending(false);
          });
        },
      });
      window.google.accounts.id.renderButton(container.current, {
        theme: 'filled_blue', size: 'large', text: 'continue_with', width: 280,
      });
      setReady(true);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : 'Google sign-in is unavailable.');
    });
    return () => { active = false; };
  }, [clientId, retry, signIn]);

  if (!clientId) return <div className="sign-in-control">
    <button className="google-button" type="button" disabled aria-describedby="google-setup-note">
      <strong aria-hidden="true">G</strong> Continue with Google
    </button>
    <p className="google-setup-note" id="google-setup-note" role="status">
      Sign-in is being configured. Please contact admissions for assistance.
    </p>
  </div>;
  return <div className="sign-in-control" aria-busy={pending}>
    <div ref={container} style={{ display: ready && !pending ? 'flex' : 'none' }} />
    {(!ready || pending) && <button className="google-button" type="button" disabled>
      <strong aria-hidden="true">G</strong> Continue with Google
    </button>}
    {!ready && !error && <p role="status">Loading Google sign-in…</p>}
    {pending && <p role="status">Verifying your candidate registration…</p>}
    {error && <div role="alert"><p>{error}</p>
      <button className="secondary-button" type="button" onClick={() => setRetry((value) => value + 1)}>Retry sign-in</button>
    </div>}
  </div>;
}
