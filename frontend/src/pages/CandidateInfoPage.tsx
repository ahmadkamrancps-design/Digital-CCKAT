import { Link, Navigate } from 'react-router-dom';
import CandidateSidebar from '../components/CandidateSidebar';
import { useAuth } from '../features/auth/AuthProvider';
import { previewCandidate } from '../features/preview/preview';
import { DeviceReadiness } from '../features/candidate/DeviceReadiness';

const sections = {
  instructions: {
    title: 'Exam instructions',
    description: 'Full exam instructions will be available with your assigned exam. This page is a layout preview.',
  },
  'system-check': {
    title: 'System check',
    description: 'Check your browser, recovery storage, and connection before the examination.',
  },
  profile: { title: 'Candidate profile', description: 'Your candidate registration details.' },
  help: {
    title: 'Help & Support',
    description: 'Contact CCK admissions for registration or access assistance. Support contact details will be added here.',
  },
};

/** Candidate guidance and readiness, preserving the existing CCK page shell. */
export function CandidateInfoPage({ section }: { section: keyof typeof sections }) {
  const { profile, isPreview } = useAuth();
  const displayProfile = isPreview ? previewCandidate : profile;
  if (!displayProfile) return <Navigate to="/" replace />;
  if (displayProfile.user.role !== 'CANDIDATE' || !displayProfile.candidate) {
    return <Navigate to="/dashboard" replace />;
  }
  const { title, description } = sections[section];
  return <div className="dashboard-layout">
    <CandidateSidebar />
    <main className="dashboard-content" id="main" tabIndex={-1}>
      <section className="exam-card card" aria-labelledby="page-heading">
        <h1 id="page-heading">{title}</h1>
        <p>{section === 'instructions' && !isPreview
          ? 'Open My Exam to view your assigned subjects, their durations, and start authorization.' : description}</p>
        {section === 'system-check' && (isPreview
          ? <p>Development preview: live device and service checks run after candidate sign-in.</p>
          : <DeviceReadiness />)}
        {section === 'instructions' && !isPreview && <>
          <ol>
            <li>Choose Start subject only when instructed. Each subject has an independent timer.</li>
            <li>Use Previous, Next, or the question overview to navigate within the current subject.</li>
            <li>You may change answers and mark questions for review until submission or expiry.</li>
            <li>Check the save status. Resolve any save problem before finishing.</li>
            <li>A connection interruption does not extend your time. Submitted subjects cannot be reopened.</li>
          </ol>
          <p><Link className="primary-button" to="/exam">My Exam →</Link></p>
        </>}
        {section === 'profile' && <dl>
          <dt>Name</dt><dd><bdi>{displayProfile.candidate.full_name}</bdi></dd>
          <dt>Roll number</dt><dd><bdi>{displayProfile.candidate.roll_number}</bdi></dd>
          {displayProfile.user.email && <><dt>Registered email</dt><dd><bdi>{displayProfile.user.email}</bdi></dd></>}
        </dl>}
        <Link to="/dashboard">Return to dashboard</Link>
      </section>
    </main>
  </div>;
}
