import { api } from "./api";
import type {
  AttemptResult,
  Grade,
  GradingAttempt,
  GradingExam,
  ManualResponse,
} from "../types/grading";

export function gradingApi(csrf: string) {
  return {
    exams: async () => {
      const rows: GradingExam[] = [];
      for (let offset = 0; ; offset += 100) {
        const page = await api<GradingExam[]>(
          `/grading/exams?limit=100&offset=${offset}`,
        );
        rows.push(...page);
        if (page.length < 100) return rows;
      }
    },
    attempts: (exam: string, offset: number) =>
      api<GradingAttempt[]>(
        `/grading/exams/${exam}/attempts?limit=50&offset=${offset}`,
      ),
    queue: (exam: string, offset: number, includeGraded: boolean) =>
      api<ManualResponse[]>(
        `/grading/exams/${exam}/queue?limit=50&offset=${offset}&include_graded=${includeGraded}`,
      ),
    grade: (
      answer: string,
      body: { expected_revision: number; marks_awarded: string; notes: string },
    ) =>
      api<Grade>(`/grading/answers/${answer}/grade`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
      }),
    history: (answer: string) =>
      api<Grade[]>(`/grading/answers/${answer}/history`),
    automatic: (attempt: string) =>
      api<{ grades_created: number }>(`/admin/attempts/${attempt}/grade`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
      }),
    results: (offset: number) =>
      api<AttemptResult[]>(`/candidate/results?limit=50&offset=${offset}`),
  };
}
