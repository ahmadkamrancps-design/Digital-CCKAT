import { api } from './api';
import type { AnswerSaved, AnswerWrite, AssignedExam, Attempt, SubjectPaper } from '../types/attempt';

const segment = encodeURIComponent;
const root = (attempt: string) => `/candidate/attempts/${segment(attempt)}`;
const subjectRoot = (attempt: string, subject: string) => `${root(attempt)}/subjects/${segment(subject)}`;
const mutation = (csrf: string, method = 'POST', body?: unknown): RequestInit => ({
  method, headers: { 'X-CSRF-Token': csrf }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

export const examApi = {
  assigned: () => api<AssignedExam[]>('/candidate/exams'),
  attempt: (id: string) => api<Attempt>(root(id)),
  begin: (exam: string, csrf: string) => api<Attempt>(`/candidate/exams/${segment(exam)}/attempt`, mutation(csrf)),
  start: (attempt: string, subject: string, csrf: string) => api<Attempt>(`${subjectRoot(attempt, subject)}/start`, mutation(csrf)),
  paper: (attempt: string, subject: string) => api<SubjectPaper>(`${subjectRoot(attempt, subject)}/questions`),
  save: (attempt: string, subject: string, question: string, answer: AnswerWrite, csrf: string) =>
    api<AnswerSaved>(`${subjectRoot(attempt, subject)}/answers/${segment(question)}`, mutation(csrf, 'PUT', answer)),
  submit: (attempt: string, subject: string, csrf: string) => api<Attempt>(`${subjectRoot(attempt, subject)}/submit`, mutation(csrf)),
};
