import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';
import { mockExam } from '../data/mockExam';
import { SubmissionPreview } from '../features/exam-preview/SubmissionPreview';
import { LiveSubmission } from '../features/exam/LiveSubmission';

/** Never show a success confirmation without a server-confirmed submission receipt. */
export function SubmissionPage() {
  const { profile, isPreview } = useAuth();
  const [params] = useSearchParams();
  if (isPreview) {
    const index = Math.max(0, mockExam.subjects.findIndex((subject) => subject.id === params.get('subject')));
    return <SubmissionPreview subject={mockExam.subjects[index]} nextSubject={mockExam.subjects[index + 1]} />;
  }
  if (!isPreview && !profile) return <Navigate to="/" replace />;
  if (!isPreview && (profile?.user.role !== 'CANDIDATE' || !profile.candidate)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <LiveSubmission />;
}
