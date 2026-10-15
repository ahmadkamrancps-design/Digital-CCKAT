import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import type { Role, SessionProfile } from "../src/types/auth";
import type {
  AttemptResult,
  Grade,
  ManualResponse,
} from "../src/types/grading";

const result: AttemptResult = {
  attempt_id: "attempt",
  exam_id: "exam",
  exam_title: "Official CCK test",
  grading_status: "COMPLETE",
  publication_status: "WITHHELD",
  maximum_marks: "100.00",
  marks_awarded: "91.25",
  percentage: "91.25",
  subjects: [
    {
      subject_name: "Urdu",
      sequence: 1,
      maximum_marks: "100.00",
      marks_awarded: "91.25",
      pending_answers: 0,
    },
  ],
};
const responseRow: ManualResponse = {
  answer_id: "answer",
  attempt_id: "attempt",
  subject_name: "Urdu",
  question_number: 1,
  prompt: "مختصر جواب لکھیں۔",
  direction: "rtl",
  answer_text: "پاکستان",
  maximum_marks: "2.00",
  current_grade: null,
};

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function fixture(role: Role = "EXAMINER") {
  const profile: SessionProfile = {
    user: { id: "user", email: null, display_name: "CCK User", role },
    candidate:
      role === "CANDIDATE"
        ? {
            id: "candidate",
            roll_number: "CCK-104",
            full_name: "Candidate Name",
            status: "APPROVED",
          }
        : null,
    csrf_token: "grading-csrf",
    session_expires_at: "2030-01-01T00:00:00Z",
  };
  const controls = { saveStatus: 200, released: false, denyRead: false };
  const grades: Grade[] = [];
  const fetcher = vi.fn(async (raw: string, options: RequestInit = {}) => {
    const path = raw.split("?")[0];
    if (path === "/api/me") return json(profile);
    if (path === "/api/candidate/results")
      return json([
        {
          ...result,
          publication_status: controls.released ? "RELEASED" : "WITHHELD",
        },
      ]);
    if (path === "/api/candidate/exams") return json([]);
    if (path === "/api/grading/exams")
      return json([
        {
          id: "exam",
          title: "Official CCK test",
          results_released: controls.released,
        },
      ]);
    if (controls.denyRead) return json({ detail: "Exam access revoked." }, 404);
    if (path.endsWith("/attempts")) return json([]);
    if (path.endsWith("/queue"))
      return json(
        grades.length && !raw.includes("include_graded=true")
          ? []
          : [{ ...responseRow, current_grade: grades.at(-1) || null }],
      );
    if (path.endsWith("/history")) return json(grades);
    if (path.endsWith("/grade")) {
      if (controls.saveStatus !== 200)
        return json(
          {
            detail:
              controls.saveStatus === 409
                ? "This grade changed. Reload the response before saving."
                : "Exam access revoked.",
          },
          controls.saveStatus,
        );
      const body = JSON.parse(String(options.body)) as {
        marks_awarded: string;
        expected_revision: number;
        notes: string;
      };
      const grade: Grade = {
        id: `grade-${grades.length + 1}`,
        answer_id: "answer",
        revision: body.expected_revision + 1,
        marks_awarded: body.marks_awarded,
        maximum_marks: "2.00",
        method: "MANUAL",
        graded_by: "user",
        graded_at: "2026-10-15T10:00:00Z",
        notes: body.notes,
      };
      grades.push(grade);
      return json(grade);
    }
    return json({ detail: "Unexpected request." }, 404);
  });
  vi.stubGlobal("fetch", fetcher);
  return { controls, grades, fetcher };
}
function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
async function openExam() {
  await screen.findByRole("option", { name: "Official CCK test" });
  await userEvent.selectOptions(screen.getByLabelText("Exam to grade"), "exam");
  await screen.findByText("پاکستان");
}
beforeEach(() => {
  vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "false");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("grading workspace", () => {
  it("refreshes the grading lock after administration withholds results", async () => {
    const state = fixture();
    state.controls.released = true;
    renderApp("/grading");
    await openExam();
    expect(
      screen.getByRole("button", { name: "Save grade for question 1" }),
    ).toBeDisabled();
    state.controls.released = false;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh grading" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save grade for question 1" }),
      ).toBeEnabled(),
    );
  });
  it("saves marks with CSRF and revision and supports viewing grade history", async () => {
    const state = fixture();
    renderApp("/grading");
    await openExam();
    expect(screen.getByText(responseRow.prompt)).toHaveAttribute("dir", "rtl");
    await userEvent.type(screen.getByLabelText("Marks for question 1"), "1.5");
    await userEvent.type(
      screen.getByLabelText("Examiner notes for question 1"),
      "Rubric applied",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save grade for question 1" }),
    );
    await screen.findByText("No responses need review in this view.");
    expect(state.fetcher).toHaveBeenCalledWith(
      "/api/grading/answers/answer/grade",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "grading-csrf" }),
        body: JSON.stringify({
          expected_revision: 0,
          marks_awarded: "1.5",
          notes: "Rubric applied",
        }),
      }),
    );
    await userEvent.click(screen.getByLabelText("Include graded responses"));
    await userEvent.click(
      await screen.findByRole("button", {
        name: "View history for question 1",
      }),
    );
    expect(
      await screen.findByRole("list", { name: "Grade history for question 1" }),
    ).toHaveTextContent("Rubric applied");
    expect(state.grades).toHaveLength(1);
  });
  it("retains typed marks after a stale-write rejection", async () => {
    const state = fixture();
    state.controls.saveStatus = 409;
    renderApp("/grading");
    await openExam();
    await userEvent.type(screen.getByLabelText("Marks for question 1"), "1.5");
    await userEvent.click(
      screen.getByRole("button", { name: "Save grade for question 1" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This grade changed",
    );
    expect(screen.getByLabelText("Marks for question 1")).toHaveValue(1.5);
    expect(state.grades).toHaveLength(0);
  });
  it("clears the response when saving discovers revoked access", async () => {
    const state = fixture();
    state.controls.saveStatus = 404;
    renderApp("/grading");
    await openExam();
    await userEvent.type(screen.getByLabelText("Marks for question 1"), "1");
    await userEvent.click(
      screen.getByRole("button", { name: "Save grade for question 1" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Access to this exam is no longer available",
    );
    expect(screen.queryByText("پاکستان")).not.toBeInTheDocument();
  });
  it.each(["CANDIDATE", "PROCTOR"] as const)(
    "blocks %s from grading before fetching responses",
    async (role) => {
      const state = fixture(role);
      renderApp("/grading");
      await screen.findByRole("heading", {
        name:
          role === "CANDIDATE" ? "Welcome, Candidate Name." : "Staff workspace",
      });
      expect(
        state.fetcher.mock.calls.some(([path]) =>
          path.startsWith("/api/grading"),
        ),
      ).toBe(false);
    },
  );
});

describe("candidate results", () => {
  it("never renders withheld marks and displays only released server totals", async () => {
    const state = fixture("CANDIDATE");
    renderApp("/results");
    await screen.findByText(/Your result is not available yet/);
    expect(screen.queryByText("91.25%")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    state.controls.released = true;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh results" }),
    );
    expect(await screen.findByText("91.25%")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Subject marks" }),
    ).toHaveTextContent("Urdu");
    state.controls.released = false;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh results" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("91.25%")).not.toBeInTheDocument(),
    );
  });
  it("offers a sample result in development preview without API calls", async () => {
    const state = fixture();
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "true");
    renderApp("/results");
    expect(
      await screen.findByText(/Sample result for design testing/),
    ).toBeInTheDocument();
    expect(screen.getByText("82.00%")).toBeInTheDocument();
    expect(state.fetcher).not.toHaveBeenCalled();
  });
});
