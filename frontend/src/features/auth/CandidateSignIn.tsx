import { useRef, useState } from 'react';
import type { CandidateCredentials } from '../../types/auth';
import { useAuth } from './AuthProvider';

export function CandidateSignIn() {
  const { signInCandidate } = useAuth();
  const [value, setValue] = useState<CandidateCredentials>({
    roll_number: '', full_name: '', father_name: '',
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  return <form className="candidate-login-form" aria-label="Candidate sign-in" onSubmit={(event) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    void signInCandidate(value).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : 'Unable to sign in. Please try again.');
    }).finally(() => { inFlight.current = false; setPending(false); });
  }}>
    <fieldset disabled={pending}>
      <legend>
        <span>Candidate sign-in</span>
        <small>Enter the details exactly as they appear in your admission record.</small>
      </legend>
      <label htmlFor="candidate-roll">Roll number</label>
      <input id="candidate-roll" name="roll_number" required maxLength={64}
        autoComplete="username" autoCapitalize="none" spellCheck={false}
        aria-describedby="roll-help" value={value.roll_number}
        onChange={(event) => setValue({ ...value, roll_number: event.target.value })} />
      <p id="roll-help">Use the roll number issued through the CCK admission portal.</p>
      <label htmlFor="candidate-name">Full name</label>
      <input id="candidate-name" name="full_name" required maxLength={200} autoComplete="name"
        dir="auto" value={value.full_name}
        onChange={(event) => setValue({ ...value, full_name: event.target.value })} />
      <label htmlFor="candidate-father">Father’s name</label>
      <input id="candidate-father" name="father_name" required maxLength={200} autoComplete="off"
        dir="auto" value={value.father_name}
        onChange={(event) => setValue({ ...value, father_name: event.target.value })} />
      <p className="login-details-help">Enter both names as recorded in your admission application.</p>
      <button className="primary-button" type="submit">{pending ? 'Verifying…' : 'Sign in'}</button>
    </fieldset>
    {pending && <p role="status">Checking your candidate registration…</p>}
    {error && <p role="alert">{error}</p>}
  </form>;
}
