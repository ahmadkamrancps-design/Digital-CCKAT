import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen } from 'lucide-react';
import { examApi } from '../../services/exam';
import type { AssignedExam } from '../../types/attempt';

export function AssignedExams() {
  const [exams, setExams] = useState<AssignedExam[] | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    void examApi.assigned().then((result) => { if (active) setExams(result); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load exams.'); });
    return () => { active = false; };
  }, [retry]);
  return <section className="exam-card card" aria-labelledby="assigned-heading">
    <div className="exam-card-title"><h2 id="assigned-heading">Your Entry Test</h2></div>
    {error ? <><p role="alert">{error}</p><button className="secondary-button" onClick={() => setRetry((value) => value + 1)}>Retry exam list</button></>
      : !exams ? <p role="status">Loading assigned exams…</p>
      : exams.length === 0 ? <p>No active exam is available. Admissions will confirm your assignment and schedule.</p>
      : exams.map((exam) => <div key={exam.exam_id} className="assigned-exam">
        <h3>{exam.title}</h3>
        <p>{exam.is_start_authorized ? 'Start authorized by administration' : 'Waiting for start authorization'}</p>
        {exam.scheduled_start && <p>Scheduled start: <time dateTime={exam.scheduled_start}>{new Date(exam.scheduled_start).toLocaleString()}</time></p>}
        {exam.scheduled_end && <p>Exam closes: <time dateTime={exam.scheduled_end}>{new Date(exam.scheduled_end).toLocaleString()}</time></p>}
        <h3 className="subjects-heading">Subjects</h3>
        <div className="subject-grid">{exam.subjects.map((subject) => <div className="subject-card" key={subject.exam_subject_id}>
          <BookOpen aria-hidden="true" /><div><strong><bdi>{subject.name}</bdi></strong><span>{subject.duration_minutes} Minutes</span></div>
        </div>)}</div>
        <Link className="primary-button dashboard-action" to={exam.attempt_id ? `/exam?attempt=${encodeURIComponent(exam.attempt_id)}` : `/exam?exam=${encodeURIComponent(exam.exam_id)}`}>
          {exam.attempt_id ? 'Resume / view exam' : 'View instructions'} →
        </Link>
      </div>)}
  </section>;
}
