import { useRef, useState } from 'react';
import { useAuth } from './AuthProvider';

export function StaffSignIn() {
  const { signInStaff } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  return <form className="candidate-login-form" aria-label="Staff sign-in" onSubmit={(event) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    void signInStaff({ email: email.trim().toLowerCase(), password }).catch((cause: unknown) => {
      setPassword('');
      setError(cause instanceof Error ? cause.message : 'Unable to sign in. Please try again.');
    }).finally(() => { inFlight.current = false; setPending(false); });
  }}>
    <fieldset disabled={pending}>
      <legend>
        <span>Staff sign-in</span>
        <small>Use your approved staff email and password.</small>
      </legend>
      <label htmlFor="staff-email">Email address</label>
      <input id="staff-email" name="email" type="email" required maxLength={254}
        autoComplete="username" autoCapitalize="none" spellCheck={false}
        value={email} onChange={(event) => setEmail(event.target.value)} />
      <label htmlFor="staff-password">Password</label>
      <input id="staff-password" name="password" type="password" required maxLength={128}
        autoComplete="current-password" value={password}
        onChange={(event) => setPassword(event.target.value)} />
      <p className="login-details-help">If you need a password reset, contact the system administrator.</p>
      <button className="primary-button" type="submit">{pending ? 'Signing in…' : 'Sign in to staff portal'}</button>
    </fieldset>
    {pending && <p role="status">Checking your staff account…</p>}
    {error && <p role="alert">{error}</p>}
  </form>;
}
