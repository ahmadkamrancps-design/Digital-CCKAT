import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import CCKLogo from '../components/CCKLogo';
import { StaffSignIn } from '../features/auth/StaffSignIn';
import { useAuth } from '../features/auth/AuthProvider';
import { CandidateSignIn } from '../features/auth/CandidateSignIn';

export default function LoginPage({ staffOnly = false }: { staffOnly?: boolean }) {
  const { profile, loading, error, refresh, isPreview } = useAuth();
  const [staffOpen, setStaffOpen] = useState(false);
  if (profile && !loading && !error) return <Navigate to={profile.user.role === 'ADMIN' ? '/admin' : '/dashboard'} replace />;
  return (
    <main className="login-page" id="main" tabIndex={-1}>
      <div className="login-overlay" aria-hidden="true" />

      <section className="login-brand" aria-labelledby="college-heading">
        <CCKLogo size={105} />
        <h1 className="cck-serif" id="college-heading">Cadet College Kohat</h1>
        <div className="motto">
          <span aria-hidden="true" />
          FROM DARKNESS UNTO LIGHT
          <span aria-hidden="true" />
        </div>
      </section>

      <section className="login-card" aria-labelledby="sign-in-heading">
        <h2 id="sign-in-heading">{staffOnly ? 'Administration' : 'Welcome'}</h2>
        {import.meta.env.DEV && import.meta.env.VITE_MANAGEMENT_SANDBOX === 'true' && <p><a className="primary-button preview-entry" href="/api/local-management">Open test administration →</a></p>}
        <p>
          {staffOnly ? 'Sign in with your staff email and password' : 'Enter your admissions details to continue to'}
          <br />
          CCK Online Entry Test 2026
        </p>

        {isPreview ? <><Link className="primary-button preview-entry" to="/dashboard">Explore without login →</Link><Link className="admin-preview-entry" to="/preview/admin">Explore administration design →</Link></>
          : loading ? <p className="login-session-status" role="status">Checking your session…</p>
          : <>
            {error && <div className="login-session-error" role="alert">
              <p>{error}</p>
              <button className="secondary-button" type="button" onClick={() => { void refresh(); }}>Try again</button>
            </div>}
            {staffOnly ? <StaffSignIn /> : <><CandidateSignIn />
            <details className="staff-sign-in" onToggle={(event) => setStaffOpen(event.currentTarget.open)}>
              <summary>Staff sign-in</summary>
              {staffOpen && <StaffSignIn />}
            </details>
            </>}
          </>}

        {staffOnly && <p><Link to="/">Candidate sign-in</Link></p>}

        <div className="login-info">
          <span aria-hidden="true">ⓘ</span>
          <p>
            {staffOnly ? 'Access is restricted to approved staff accounts.' : 'Only registered candidates can access the test.'}
            <br />
            {staffOnly ? 'Your account role determines which management tools you can access.' : 'We verify your roll number, full name, and father’s name with your admission record.'}
          </p>
        </div>
      </section>

      <footer>
        © 2026 Cadet College Kohat
        <span aria-hidden="true">|</span>
        Privacy Policy
        <span aria-hidden="true">|</span>
        Help &amp; Support
      </footer>
    </main>
  );
}
