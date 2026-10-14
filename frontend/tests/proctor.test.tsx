import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import { remainingTime } from "../src/features/proctor/ProctorPage";
import { usePoll } from "../src/features/proctor/usePoll";
import type { Role, SessionProfile } from "../src/types/auth";
import type {
  MonitoredCandidate,
  MonitoringResponse,
} from "../src/types/proctor";

const row: MonitoredCandidate = {
  candidate_id: "candidate-1",
  roll_number: "CCK-104",
  full_name: "محمد احمد",
  access_active: true,
  attempt_id: "attempt-1",
  state: "TESTING",
  subject_attempt_id: "subject-1",
  subject_name: "English",
  subject_status: "ACTIVE",
  question_count: 30,
  reported_question_sequence: 23,
  expires_at: "2026-10-15T09:01:00Z",
  remaining_seconds: 60,
  connection: "ONLINE",
  last_seen_at: "2026-10-15T09:00:00Z",
  review_event_count: 1,
};
function backend(role: Role = "PROCTOR") {
  const profile: SessionProfile = {
    user: {
      id: "staff-user",
      email: "approved@gmail.com",
      display_name: "Monitoring Staff",
      role,
    },
    candidate:
      role === "CANDIDATE"
        ? {
            id: "candidate-1",
            full_name: "Candidate Name",
            roll_number: "CCK-104",
            status: "APPROVED",
          }
        : null,
    csrf_token: "test-csrf",
    session_expires_at: "2030-01-01T00:00:00Z",
  };
  const controls = { status: 200 };
  const response = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const fetcher = vi.fn(async (path: string) => {
    if (path === "/api/me") return response(profile);
    if (path === "/api/candidate/exams") return response([]);
    if (path.startsWith("/api/proctor/exams?"))
      return response([
        {
          id: "exam-1",
          title: "Assigned Exam",
          is_start_authorized: true,
          scheduled_start: null,
          scheduled_end: null,
        },
      ]);
    if (path.startsWith("/api/proctor/exams/exam-1/sessions"))
      return controls.status === 200
        ? response({ server_time: "2026-10-15T09:00:00Z", candidates: [row] })
        : response(
            {
              detail:
                controls.status === 503
                  ? "Temporary failure."
                  : "Access revoked.",
            },
            controls.status,
          );
    if (path.startsWith("/api/proctor/attempts/attempt-1/events"))
      return response([
        {
          id: "event-1",
          event_type: "VISIBILITY_HIDDEN",
          source: "CLIENT",
          subject_attempt_id: "subject-1",
          server_timestamp: "2026-10-15T09:00:00Z",
        },
      ]);
    throw new Error(`Unexpected request ${path}`);
  });
  vi.stubGlobal("fetch", fetcher);
  return { fetcher, controls };
}
function open() {
  return render(
    <MemoryRouter initialEntries={["/proctor"]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
beforeEach(() => vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "false"));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("proctor workspace", () => {
  it.each(["CANDIDATE", "EXAMINER"] as const)(
    "does not fetch monitoring or keys for %s",
    async (role) => {
      const state = backend(role);
      open();
      await screen.findByRole("heading", {
        name:
          role === "CANDIDATE" ? "Welcome, Candidate Name." : "Staff workspace",
      });
      expect(
        state.fetcher.mock.calls.some(
          ([path]) => path.includes("/proctor/") || path.includes("/admin/"),
        ),
      ).toBe(false);
    },
  );
  it("does not grant monitoring access in candidate preview", async () => {
    vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "true");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    open();
    expect(
      await screen.findByRole("heading", { name: "Proctor sign-in required" }),
    ).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each(["ADMIN", "PROCTOR"] as const)(
    "shows safe status, reported position, and event context for %s",
    async (role) => {
      const state = backend(role);
      open();
      await screen.findByRole('option', { name: 'Assigned Exam' });
      await userEvent.selectOptions(
        await screen.findByLabelText("Exam to monitor"),
        "exam-1",
      );
      expect(await screen.findByText("محمد احمد")).toBeInTheDocument();
      expect(screen.getByText("Reported question 23 / 30")).toBeInTheDocument();
      expect(screen.getByText("Online · recent contact")).toBeInTheDocument();
      await userEvent.click(
        screen.getByRole("button", { name: "Inspect events for CCK-104" }),
      );
      expect(await screen.findByText("VISIBILITY HIDDEN")).toBeInTheDocument();
      expect(screen.getByText("Browser report")).toBeInTheDocument();
      expect(
        screen.getByText(/do not establish misconduct/),
      ).toBeInTheDocument();
      expect(
        state.fetcher.mock.calls.some(
          ([path]) => path.includes("/questions") || path.includes("/answers"),
        ),
      ).toBe(false);
    },
  );
  it("labels retained snapshots as stale, then clears them after access revocation", async () => {
    const state = backend();
    open();
    await screen.findByRole('option', { name: 'Assigned Exam' });
    await userEvent.selectOptions(
      await screen.findByLabelText("Exam to monitor"),
      "exam-1",
    );
    await screen.findByText("محمد احمد");
    state.controls.status = 503;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "status may be stale",
    );
    expect(screen.getByText("محمد احمد")).toBeInTheDocument();
    state.controls.status = 404;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("محمد احمد")).not.toBeInTheDocument(),
    );
  });
  it("uses server timestamps and elapsed monotonic time instead of the device date", () => {
    const snapshot = {
      data: {
        server_time: "2026-10-15T09:00:00Z",
        candidates: [row],
      } satisfies MonitoringResponse,
      requestedAt: 1000,
    };
    vi.spyOn(Date, "now").mockReturnValue(4_000_000_000_000);
    expect(remainingTime(row, snapshot, 16_000)).toBe("00:45");
    expect(remainingTime(row, snapshot, 90_000)).toBe("00:00");
  });
  it("does not overlap polling requests and aborts when its scope unmounts", async () => {
    vi.useFakeTimers();
    let finish!: (value: number) => void;
    const load = vi.fn(
      async (_signal: AbortSignal) =>
        new Promise<number>((resolve) => {
          finish = resolve;
        }),
    );
    const view = renderHook(() => usePoll("scope", load));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      finish(1);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(load).toHaveBeenCalledTimes(2);
    view.unmount();
    expect(load.mock.calls[1][0].aborted).toBe(true);
    finish(2);
  });
});
