import { api } from "./api";
import type {
  MonitoredExam,
  MonitoringResponse,
  SessionEvent,
} from "../types/proctor";

export const proctorApi = {
  exams: async (signal?: AbortSignal): Promise<MonitoredExam[]> => {
    const result: MonitoredExam[] = [];
    for (let offset = 0; ; offset += 100) {
      const page = await api<MonitoredExam[]>(
        `/proctor/exams?limit=100&offset=${offset}`,
        { signal },
      );
      result.push(...page);
      if (page.length < 100) return result;
    }
  },
  sessions: (
    id: string,
    offset: number,
    search: string,
    activeOnly: boolean,
    signal?: AbortSignal,
  ) =>
    api<MonitoringResponse>(
      `/proctor/exams/${encodeURIComponent(id)}/sessions?${new URLSearchParams({ limit: "50", offset: String(offset), search, active_only: String(activeOnly) })}`,
      { signal },
    ),
  events: (attempt: string, offset: number, signal?: AbortSignal) =>
    api<SessionEvent[]>(
      `/proctor/attempts/${encodeURIComponent(attempt)}/events?limit=50&offset=${offset}`,
      { signal },
    ),
};
