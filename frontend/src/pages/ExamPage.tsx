import { Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';
import { ExamPreview } from '../features/exam-preview/ExamPreview';
import { LiveExam } from '../features/exam/LiveExam';

/** Interactive sample UI in development; real exams still require a backend attempt. */
export function ExamPage() {
  const { profile, isPreview } = useAuth();
  if (isPreview) return <ExamPreview />;
  if (!isPreview && !profile) return <Navigate to="/" replace />;
  if (!isPreview && (profile?.user.role !== 'CANDIDATE' || !profile.candidate)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <LiveExam key={profile!.user.id} />;
}
