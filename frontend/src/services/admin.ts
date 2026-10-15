import { useMemo } from "react";
import { useAuth } from "../features/auth/AuthProvider";
import { api } from "./api";
import type { ProctorAssignment } from "../types/proctor";
import type { ExaminerAssignment } from "../types/grading";
import type {
  AdminAssignment,
  AdminCandidate,
  AdminCandidateWrite,
  AdminExam,
  AdminExamSubject,
  AdminExamSubjectWrite,
  AdminExamWrite,
  AdminPaper,
  AdminPaperEntry,
  AdminQuestion,
  AdminQuestionWrite,
  AdminSubject,
  AdminSubjectWrite,
  StaffAction,
} from "../types/admin";

export function adminApi(csrf: string) {
  const write = <T>(path: string, method: string, body?: unknown) =>
    api<T>(`/admin${path}`, {
      method,
      headers: { "X-CSRF-Token": csrf },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  return {
    assignExaminer: (exam: string, user: string, is_active: boolean) => write<ExaminerAssignment[]>(`/exams/${exam}/examiners/${user}`, 'PUT', { is_active }),
    release: (id: string, result_release_at: string | null) => write<AdminExam>(`/exams/${id}/result-release`, 'POST', { released: true, result_release_at }),
    proctorAssignments: (exam: string) => api<ProctorAssignment[]>(`/admin/exams/${exam}/proctors`),
    assignProctor: (exam: string, user: string, is_active: boolean) => write<ProctorAssignment[]>(`/exams/${exam}/proctors/${user}`, 'PUT', { is_active }),
    list: <T>(path: string, query: Record<string, string> = {}) =>
      api<T[]>(`/admin${path}?${new URLSearchParams(query)}`),
    candidate: (value: AdminCandidateWrite, id?: string) =>
      write<AdminCandidate>(
        `/candidates${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        value,
      ),
    importCandidates: (candidates: AdminCandidateWrite[]) =>
      write<AdminCandidate[]>("/candidates/import", "POST", { candidates }),
    assignments: (id: string) =>
      api<AdminAssignment[]>(`/admin/candidates/${id}/assignments`),
    assign: (exam: string, candidate: string, is_active: boolean) =>
      write<AdminAssignment>(`/exams/${exam}/candidates/${candidate}`, "PUT", {
        is_active,
      }),
    subject: (value: AdminSubjectWrite, id?: string) =>
      write<AdminSubject>(
        `/subjects${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        value,
      ),
    exam: (id: string) => api<AdminExam>(`/admin/exams/${id}`),
    saveExam: (value: AdminExamWrite, id?: string) =>
      write<AdminExam>(
        `/exams${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        value,
      ),
    publish: (id: string, published: boolean) =>
      write<AdminExam>(`/exams/${id}/publication`, "POST", { published }),
    authorize: (id: string, authorized: boolean) =>
      write<{ is_start_authorized: boolean }>(
        `/exams/${id}/start-authorization`,
        "POST",
        { authorized },
      ),
    withhold: (id: string, result_release_at: string | null) =>
      write<AdminExam>(`/exams/${id}/result-release`, "POST", {
        released: false,
        result_release_at,
      }),
    reorderSubjects: (id: string, subject_ids: string[]) =>
      write<AdminExamSubject[]>(`/exams/${id}/subject-order`, "PUT", {
        subject_ids,
      }),
    saveExamSubject: (
      exam: string,
      value: AdminExamSubjectWrite,
      id?: string,
    ) =>
      write<AdminExamSubject>(
        `/exams/${exam}/subjects${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        value,
      ),
    removeExamSubject: (exam: string, id: string) =>
      write<void>(`/exams/${exam}/subjects/${id}`, "DELETE"),
    question: (value: AdminQuestionWrite, id?: string) =>
      write<AdminQuestion>(
        `/questions${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        value,
      ),
    archiveQuestion: (id: string) =>
      write<AdminQuestion>(`/questions/${id}/archive`, "POST"),
    paper: (id: string) =>
      api<AdminPaper>(`/admin/exam-subjects/${id}/questions`),
    savePaper: (id: string, questions: AdminPaperEntry[]) =>
      write<AdminPaper>(`/exam-subjects/${id}/questions`, "PUT", { questions }),
  };
}
export function useAdminApi() {
  const { profile } = useAuth();
  const csrf = profile?.csrf_token || "";
  return useMemo(() => adminApi(csrf), [csrf]);
}
/** Page through backend limits; selectors never silently stop at the first 50 records. */
export async function allAdminRows<T>(
  client: ReturnType<typeof adminApi>,
  path: string,
  query: Record<string, string> = {},
): Promise<T[]> {
  const records: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await client.list<T>(path, {
      ...query,
      limit: "100",
      offset: String(offset),
    });
    records.push(...page);
    if (page.length < 100) return records;
  }
}
export type { StaffAction };
