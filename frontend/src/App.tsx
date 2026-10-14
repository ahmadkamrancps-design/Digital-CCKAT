import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Layout } from './components/Layout';
import { useAuth } from './features/auth/AuthProvider';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import { ExamPage } from './pages/ExamPage';
import { SubmissionPage } from './pages/SubmissionPage';
import { CandidateInfoPage } from './pages/CandidateInfoPage';
import { ExamSessions } from './features/exam/ExamSessions';
import { AdminLayout } from './features/admin/AdminLayout';
import { CandidatesPage } from './features/admin/CandidatesPage';
import { SubjectsPage } from './features/admin/SubjectsPage';
import { QuestionsPage } from './features/admin/QuestionsPage';
import { CreateExamPage, ExamDetailPage, ExamsPage } from './features/admin/ExamsPage';
import { StaffActionsPage } from './features/admin/StaffActionsPage';
import { ProctorPage } from './features/proctor/ProctorPage';

export default function App() {
  const { loading, error, refresh, profile, isPreview } = useAuth();
  const { pathname } = useLocation();
  const publicLogin = pathname === '/' || pathname === '/login';
  const routes = <Routes>
    <Route path="/" element={<LoginPage />} />
    <Route path="/login" element={<Navigate to="/" replace />} />
    <Route path="/dashboard" element={<DashboardPage />} />
    <Route path="/exam" element={<ExamPage />} />
    <Route path="/submission" element={<SubmissionPage />} />
    <Route path="/instructions" element={<CandidateInfoPage section="instructions" />} />
    <Route path="/system-check" element={<CandidateInfoPage section="system-check" />} />
    <Route path="/profile" element={<CandidateInfoPage section="profile" />} />
    <Route path="/help" element={<CandidateInfoPage section="help" />} />
    <Route path="/proctor" element={<ProctorPage />} />
    <Route path="/admin" element={<AdminLayout />}>
      <Route index element={<Navigate to="candidates" replace />} />
      <Route path="candidates" element={<CandidatesPage />} />
      <Route path="subjects" element={<SubjectsPage />} />
      <Route path="questions" element={<QuestionsPage />} />
      <Route path="exams" element={<ExamsPage />} />
      <Route path="exams/new" element={<CreateExamPage />} />
      <Route path="exams/:examId" element={<ExamDetailPage />} />
      <Route path="actions" element={<StaffActionsPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
  const content = publicLogin ? routes
      : loading && !profile ? <div className="card session-state" role="status">Checking your session…</div>
      : error && !profile ? <div className="card session-state">
        <h1>Unable to confirm access</h1><p role="alert">{error}</p>
        <button onClick={() => { void refresh(); }}>Try again</button>
      </div>
      : routes;
  const fullPage = pathname.startsWith('/admin') || pathname === '/proctor' || (['/dashboard', '/instructions', '/system-check', '/profile', '/help', '/exam', '/submission'].includes(pathname)
    && (isPreview || (profile?.user.role === 'CANDIDATE' && !!profile.candidate)));
  const page = publicLogin || (fullPage && (!loading || !!profile) && (!error || !!profile))
    ? content
    : <Layout>{content}</Layout>;
  return <ExamSessions>
    {isPreview && <div className="preview-notice" role="note">Development preview · Sample data · No sign-in required</div>}
    {error && profile && <div className="session-warning" role="alert">Session check: {error} <button onClick={() => { void refresh(); }}>Try again</button></div>}
    {page}
  </ExamSessions>;
}
