import { openRecovery, type RecoveryScope } from '../../storage/recovery';
import { examApi } from '../../services/exam';
import type { AnswerFields, SubjectPaper } from '../../types/attempt';
import { AnswerQueue } from './AnswerQueue';
import { ServerDeadline } from './ServerDeadline';
import type { ExamSession } from './ExamSessions';

export async function createSession(scope: RecoveryScope, paper: SubjectPaper, requestedAt: number, csrf: { current: string }): Promise<ExamSession> {
  const journal = await openRecovery(scope);
  try {
    for (const cell of journal.initial) {
      const question = paper.questions.find((item) => item.exam_question_id === cell.confirmed.exam_question_id);
      if (!question) throw new Error('Recovery questions do not match this subject. Contact your proctor.');
      const valid = (value: AnswerFields) => question.type === 'MCQ'
        ? value.short_answer_text === null && (value.selected_option_id === null || question.options.some((item) => item.id === value.selected_option_id))
        : value.selected_option_id === null;
      if (!valid(cell.draft) || !valid(cell.confirmed) || (cell.request && (!valid(cell.request) || cell.request.expected_revision !== cell.confirmed.revision))) {
        throw new Error('The recovered answer does not match this question. Contact your proctor.');
      }
    }
    const deadline = new ServerDeadline();
    if (paper.subject.status === 'ACTIVE') deadline.sync(paper.subject.expires_at, paper.server_time, requestedAt);
    const queue = new AnswerQueue(paper.questions.map((question) => question.answer),
      (id, answer) => examApi.save(scope.attemptId, scope.subjectId, id, answer, csrf.current), () => deadline.writable(), journal);
    await queue.restore(journal.initial);
    if (paper.subject.status !== 'ACTIVE') queue.locked = true;
    return { deadline, queue };
  } catch (cause) { await journal.release(); throw cause; }
}
