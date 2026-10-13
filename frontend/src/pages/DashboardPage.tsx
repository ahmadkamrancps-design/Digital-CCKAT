import { useState, type ReactNode } from 'react';
import { BookOpen, Calculator, CalendarDays, Clock3, PenLine } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import CandidateSidebar from '../components/CandidateSidebar';
import { useAuth } from '../features/auth/AuthProvider';
import { previewCandidate } from '../features/preview/preview';
import { AssignedExams } from '../features/exam/AssignedExams';

export default function DashboardPage() {
  const { profile, signOut, isPreview } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const displayProfile = isPreview ? previewCandidate : profile;
  if (!displayProfile) return <Navigate to="/" replace />;
  const { candidate, user } = displayProfile;
  const logout = async () => {
    setPending(true);
    setError(null);
    try { await signOut(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to sign out.'); }
    finally { setPending(false); }
  };
  const signOutButton = isPreview ? <Link className="secondary-button" to="/">Back to login</Link> : <button
    type="button"
    className="secondary-button"
    onClick={() => { void logout(); }}
    disabled={pending}
  >{pending ? 'Signing out…' : 'Sign out'}</button>;

  if (user.role !== 'CANDIDATE' || !candidate) {
    return <div className="staff-dashboard">
      <header>
        <h1>Welcome, <bdi>{user.display_name}</bdi>.</h1>
        {signOutButton}
      </header>
      {error && <p role="alert">{error}</p>}
      <section className="exam-card card" aria-labelledby="account-heading">
        <h2 id="account-heading">Your account</h2>
        <dl>
          <dt>Registered email</dt><dd><bdi>{user.email}</bdi></dd>
          <dt>Access</dt><dd>{user.role}</dd>
        </dl>
      </section>
      <section className="exam-card card" aria-labelledby="staff-heading">
        <h2 id="staff-heading">Staff workspace</h2>
        <p>Your staff role is verified. Staff management tools will be added in a later development milestone.</p>
      </section>
    </div>;
  }

  return (
    <div className="dashboard-layout">
      <CandidateSidebar />

      <main className="dashboard-content" id="main" tabIndex={-1}>
        <header className="dashboard-user">
          <div className="avatar" aria-hidden="true">{Array.from(candidate.full_name.trim())[0] || 'C'}</div>
          <div>
            <strong><bdi>{candidate.full_name}</bdi></strong>
          </div>
          {signOutButton}
        </header>
        {error && <p role="alert">{error}</p>}

        <section className="dashboard-welcome">
          <h1>Welcome, <bdi>{candidate.full_name}</bdi>.</h1>
          <div className="candidate-meta">
            Roll No: <strong><bdi>{candidate.roll_number}</bdi></strong>
            <span className="candidate-badge">Candidate</span>
          </div>
          <p className="candidate-email">Registered email: <bdi>{user.email}</bdi></p>
          {!isPreview && <p className="candidate-email">Wait for Saved before signing out. Signing out clears your local recovery copies.</p>}
        </section>

        <section className="campus-banner" aria-label="Cadet College Kohat campus">
          <img
            src="/assets/cck/dashboard-campus.png"
            alt="Cadet College Kohat academic block"
          />
          <div className="campus-caption">
            <strong className="cck-serif">Cadet College Kohat</strong>
            <span>From Darkness Unto Light</span>
          </div>
        </section>

        {isPreview ? <section className="exam-card card" aria-labelledby="exam-preview-heading">
          <div className="exam-card-title">
            <h2 id="exam-preview-heading">Your Entry Test</h2>
            <span>Design preview</span>
          </div>
          <p className="exam-preview-note" id="exam-preview-note">
            No exam is assigned in this portal yet. The schedule and subjects below are sample content.
            Admissions will provide your confirmed schedule and instructions.
          </p>

          <div className="exam-summary">
            <div>
              <h3>Cadet College Kohat Entry Test 2026</h3>
              <p>Class 8 Admission • Based on Class 7 syllabus</p>
            </div>
            <div className="exam-date">
              <CalendarDays aria-hidden="true" />
              <div>
                <small>Test Date (sample)</small>
                <strong>15 March 2026</strong>
              </div>
              <Clock3 aria-hidden="true" />
              <div>
                <small>Reporting Time (sample)</small>
                <strong>09:00 AM</strong>
              </div>
            </div>
          </div>

          <h3 className="subjects-heading">Subjects</h3>
          <div className="subject-grid">
            <Subject icon={<BookOpen aria-hidden="true" />} name="English" />
            <Subject icon={<Calculator aria-hidden="true" />} name="Mathematics" />
            <Subject icon={<PenLine aria-hidden="true" />} name="Urdu" />
          </div>
          {isPreview ? <Link className="primary-button dashboard-action" to="/instructions">View Instructions →</Link> : <button
            className="primary-button dashboard-action"
            type="button"
            disabled
            aria-describedby="exam-preview-note"
          >View Instructions →</button>}
        </section> : <AssignedExams />}
      </main>
    </div>
  );
}

/** Sample dashboard subjects only; assigned subjects will come from the backend. */
function Subject({ icon, name }: { icon: ReactNode; name: string }) {
  return (
    <div className="subject-card">
      {icon}
      <div>
        <strong>{name}</strong>
        <span>60 Minutes</span>
      </div>
    </div>
  );
}
