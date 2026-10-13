import { BookOpen, Timer } from 'lucide-react';
import { Link } from 'react-router-dom';
import CCKLogo from './CCKLogo';
import { ExamTimer } from './ExamTimer';
import type { ExamSubjectPreview } from '../types/exam';

interface Props {
  subjects: readonly ExamSubjectPreview[];
  subjectId: string;
  onSubjectChange: (id: string) => void;
  remainingSeconds: number;
  onFinish: () => void;
  finished: boolean;
  liveSubject?: string;
  title?: string;
  onLeave?: () => void;
}

export function ExamHeader({ subjects, subjectId, onSubjectChange, remainingSeconds, onFinish, finished, liveSubject, title, onLeave }: Props) {
  return <header className="exam-header">
    <Link className="exam-brand" to="/dashboard" aria-label="Return to candidate dashboard" onClick={onLeave ? (event) => { event.preventDefault(); onLeave(); } : undefined}>
      <CCKLogo size={58} />
      <span><strong className="cck-serif">Cadet College Kohat</strong>
        <span>{title || 'Online Entry Test 2026'}</span>
      </span>
    </Link>
    <div className="exam-header-controls">
      {liveSubject ? <span className="exam-subject-select"><BookOpen size={22} aria-hidden="true" /><strong>{liveSubject}</strong></span> : <label className="exam-subject-select">
        <BookOpen size={22} aria-hidden="true" />
        <span className="sr-only">Preview subject</span>
        <select value={subjectId} onChange={(event) => onSubjectChange(event.target.value)}>
          {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
        </select>
      </label>}
      <div className="exam-clock">
        <Timer size={27} aria-hidden="true" />
        <ExamTimer remainingSeconds={remainingSeconds} label={liveSubject ? 'Time remaining' : 'Preview timer · paused'} />
      </div>
      <button className="exam-finish-button" type="button" onClick={onFinish} disabled={finished}>Finish</button>
    </div>
  </header>;
}
