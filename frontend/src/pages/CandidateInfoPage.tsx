import { Link, Navigate } from 'react-router-dom';
import CandidateSidebar from '../components/CandidateSidebar';
import { useAuth } from '../features/auth/AuthProvider';
import { previewCandidate } from '../features/preview/preview';
import { DeviceReadiness } from '../features/candidate/DeviceReadiness';
import { ExamInstructions, HelpAndSupport, SystemCheckGuidance } from '../features/candidate/CandidateGuidance';
import { AssignedExams } from '../features/exam/AssignedExams';
import { mockExam } from '../data/mockExam';

const sections = {
  instructions: {
    title: 'Exam instructions',
    description: 'Read these instructions before starting. Ask your proctor if anything is unclear.',
  },
  'system-check': {
    title: 'System check',
    description: 'Check your browser, recovery storage, and connection before the examination.',
  },
  profile: { title: 'Candidate profile', description: 'Your candidate registration details.' },
  help: {
    title: 'Help & Support',
    description: 'Find help with exam access, saving answers, submission, and registration.',
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
    <main className="dashboard-content candidate-info-page" id="main" tabIndex={-1}>
      <section className="exam-card card candidate-info-card" aria-labelledby="page-heading">
        <p className="candidate-page-eyebrow">CCK Digital Entry Test · Candidate guide</p>
        <h1 id="page-heading">{title}</h1>
        <p className="candidate-page-intro">{description}</p>
        {section === 'instructions' && <ExamInstructions />}
        {section === 'system-check' && <><DeviceReadiness preview={isPreview} /><SystemCheckGuidance /></>}
        {section === 'profile' && <>
          {isPreview && <p className="candidate-notice">Sample profile for development preview. These details are not an admissions record.</p>}
          <dl className="candidate-profile-details">
            <div><dt>Full name</dt><dd><bdi>{displayProfile.candidate.full_name}</bdi></dd></div>
            <div><dt>Admissions roll number</dt><dd><bdi>{displayProfile.candidate.roll_number}</bdi></dd></div>
            <div><dt>Registration status</dt><dd>{displayProfile.candidate.status === 'APPROVED' ? 'Approved' : 'Disabled'}</dd></div>
            <div><dt>Account role</dt><dd>Candidate</dd></div>
            {displayProfile.user.email && <div><dt>Registered email</dt><dd><bdi>{displayProfile.user.email}</bdi></dd></div>}
          </dl>
          <section className="candidate-notice" aria-labelledby="record-corrections-heading">
            <h2 id="record-corrections-heading">Check your registration before starting</h2>
            <p>Your roll number is assigned through CCK admissions. Your approved name and father’s name must match the admissions record when you sign in. Your father’s name is not displayed on this profile.</p>
            <p>If any registration detail is wrong, contact admissions before the test. Changes must be made by authorized staff; you cannot edit your admissions record here.</p>
            <p>An approved registration does not start an exam or guarantee an assignment. Check My Exam for your assigned paper and start authorization.</p>
          </section>
          <div className="candidate-page-actions"><Link className="secondary-button" to="/help">Get registration help</Link><Link className="primary-button" to="/exam">Go to My Exam →</Link></div>
        </>}
        {section === 'help' && <HelpAndSupport />}
        <footer className="candidate-info-footer"><Link to="/dashboard">Return to dashboard</Link></footer>
      </section>
      {section === 'instructions' && (isPreview
        ? <section className="exam-card card" aria-labelledby="sample-subjects-heading">
          <h2 id="sample-subjects-heading">Sample subject order</h2>
          <p>Development preview only. Your live subject order and time limits come from your assigned exam.</p>
          <ol className="candidate-subject-outline">{mockExam.subjects.map((subject) => <li key={subject.id}><strong>{subject.name}</strong><span>{subject.durationMinutes} minutes</span></li>)}</ol>
        </section>
        : <AssignedExams />)}
    </main>
  </div>;
}
