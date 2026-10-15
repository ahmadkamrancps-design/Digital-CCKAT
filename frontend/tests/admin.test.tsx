import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import { candidateCsv } from "../src/features/admin/candidateCsv";
import type {
  AdminCandidate,
  AdminCandidateWrite,
  AdminQuestion,
  AdminSubject,
} from "../src/types/admin";
import type { SessionProfile } from "../src/types/auth";

const profile: SessionProfile = {
  user: {
    id: "admin",
    email: "admin@example.test",
    display_name: "Test Administrator",
    role: "ADMIN",
  },
  candidate: null,
  csrf_token: "admin-csrf",
  session_expires_at: "2030-01-01T10:00:00Z",
};
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function renderApp(path = "/admin/candidates") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
const subject: AdminSubject = {
  id: "subject",
  name: "Urdu",
  code: "UR",
  is_active: true,
  created_at: "2026-10-15T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
};
function fixture() {
  const candidates: AdminCandidate[] = [];
  const questions: AdminQuestion[] = [];
  const writes: { path: string; options: RequestInit }[] = [];
  const controls = { failSave: false, csrf: "admin-csrf" };
  const fetcher = vi.fn(async (raw: string, options: RequestInit = {}) => {
    const path = raw.split("?")[0];
    if (path === "/api/me")
      return response({ ...profile, csrf_token: controls.csrf });
    if (!options.method || options.method === "GET") {
      if (path === "/api/admin/candidates") return response(candidates);
      if (path === "/api/admin/exams") return response([]);
      if (path === "/api/admin/subjects") return response([subject]);
      if (path === "/api/admin/questions") return response(questions);
    }
    writes.push({ path, options });
    if (controls.failSave)
      return response({ detail: "Storage temporarily unavailable." }, 503);
    if (path === "/api/admin/candidates") {
      const value = JSON.parse(String(options.body)) as AdminCandidateWrite;
      const candidate: AdminCandidate = {
        ...value,
        id: "candidate",
        user_id: "user",
        is_active: value.status === "APPROVED",
        created_at: subject.created_at,
        updated_at: subject.updated_at,
      };
      candidates.push(candidate);
      return response(candidate, 201);
    }
    if (path === "/api/admin/questions") {
      const body = JSON.parse(String(options.body));
      const value: AdminQuestion = {
        ...body,
        id: "question",
        created_at: subject.created_at,
        updated_at: subject.updated_at,
        options: body.options || [],
        grading: body.grading || null,
        accepted_answers: body.accepted_answers || [],
      };
      questions.push(value);
      return response(value, 201);
    }
    return response({ detail: "Unexpected fixture request." }, 404);
  });
  vi.stubGlobal("fetch", fetcher);
  return { candidates, questions, writes, controls, fetcher };
}
beforeEach(() => {
  vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "false");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("administrator access and workflows", () => {
  it.each(["CANDIDATE", "PROCTOR", "EXAMINER"] as const)(
    "blocks %s before issuing admin requests",
    async (role) => {
      const fetcher = vi.fn(async (path: string) =>
        response(
          path === "/api/me"
            ? {
                ...profile,
                user: { ...profile.user, role },
                candidate:
                  role === "CANDIDATE"
                    ? {
                        id: "candidate",
                        full_name: "Candidate",
                        roll_number: "CCK-104",
                        status: "APPROVED",
                      }
                    : null,
              }
            : [],
        ),
      );
      vi.stubGlobal("fetch", fetcher);
      renderApp();
      await screen.findByRole("heading", {
        name:
          role === "CANDIDATE"
            ? "Welcome, Candidate."
            : "Welcome, Test Administrator.",
      });
      expect(
        fetcher.mock.calls.some(([path]) => path.includes("/admin/")),
      ).toBe(false);
      expect(
        screen.queryByRole("heading", { name: "Candidate management" }),
      ).not.toBeInTheDocument();
    },
  );
  it("requires authentication for admin pages even in candidate preview", async () => {
    vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "true");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    renderApp();
    expect(
      await screen.findByRole("heading", {
        name: "Administrator sign-in required",
      }),
    ).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("creates an approved candidate with CSRF and retains the form on a failed save", async () => {
    const state = fixture();
    state.controls.failSave = true;
    renderApp();
    await userEvent.click(
      await screen.findByRole("button", { name: "Create candidate" }),
    );
    await userEvent.type(screen.getByLabelText("Full name"), "محمد احمد");
    await userEvent.type(screen.getByLabelText("Father’s name"), "محمد کامران");
    await userEvent.type(screen.getByLabelText("Roll number"), "CCK-201");
    await userEvent.type(
      screen.getByLabelText("Authorized email"),
      "approved@gmail.com",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save candidate" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Storage temporarily unavailable.",
    );
    expect(screen.getByLabelText("Full name")).toHaveValue("محمد احمد");
    state.controls.failSave = false;
    await userEvent.click(
      screen.getByRole("button", { name: "Save candidate" }),
    );
    await screen.findByRole("button", { name: "Edit CCK-201" });
    expect(state.writes[1].options.headers).toMatchObject({
      "X-CSRF-Token": "admin-csrf",
    });
    expect(state.candidates[0]).toMatchObject({
      full_name: "محمد احمد",
      google_subject: null,
      status: "APPROVED",
    });
    expect(
      Object.keys(JSON.parse(String(state.writes[1].options.body))).sort(),
    ).toEqual([
      "email",
      "father_name",
      "full_name",
      "google_subject",
      "roll_number",
      "status",
    ]);
  });
  it("uses the refreshed CSRF token for the next mutation", async () => {
    const state = fixture();
    renderApp("/admin/subjects");
    await screen.findByRole("heading", { name: "Subject catalog" });
    state.controls.csrf = "fresh-csrf";
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() =>
      expect(
        state.fetcher.mock.calls.filter(([path]) => path === "/api/me"),
      ).toHaveLength(2),
    );
    await userEvent.type(screen.getByLabelText("Subject name"), "Science");
    await userEvent.type(screen.getByLabelText("Subject code"), "SCI");
    await userEvent.click(screen.getByRole("button", { name: "Save subject" }));
    await waitFor(() => expect(state.writes).toHaveLength(1));
    expect(state.writes[0].options.headers).toMatchObject({
      "X-CSRF-Token": "fresh-csrf",
    });
  });
  it("creates an Urdu numeric short answer without sending MCQ fields", async () => {
    const state = fixture();
    renderApp("/admin/questions");
    await userEvent.click(
      await screen.findByRole("button", { name: "Create question" }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Question subject"),
      "subject",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Type"),
      "SHORT_ANSWER",
    );
    await userEvent.type(
      screen.getByLabelText("Question prompt"),
      "جواب لکھیں",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Text direction"),
      "rtl",
    );
    await userEvent.type(
      screen.getByLabelText("Language code (optional)"),
      "ur",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Grading mode"),
      "NUMERIC",
    );
    await userEvent.clear(screen.getByLabelText("Absolute tolerance"));
    await userEvent.type(screen.getByLabelText("Absolute tolerance"), "0.01");
    await userEvent.type(
      screen.getByLabelText("Accepted answers (one per line)"),
      "24",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save question" }),
    );
    await waitFor(() => expect(state.questions).toHaveLength(1));
    const body = JSON.parse(String(state.writes[0].options.body));
    expect(body).toMatchObject({
      type: "SHORT_ANSWER",
      direction: "rtl",
      language: "ur",
      grading: { mode: "NUMERIC", absolute_tolerance: "0.01" },
      accepted_answers: ["24"],
    });
    expect(body).not.toHaveProperty("options");
  });
});
describe("candidate CSV import parser", () => {
  it("imports admission records without Google identities or email addresses", () => {
    expect(candidateCsv("roll_number,full_name,father_name\nCCK-104,محمد احمد,محمد کامران")).toEqual([{
      roll_number: "CCK-104", full_name: "محمد احمد", father_name: "محمد کامران",
      email: null, google_subject: null, status: "APPROVED",
    }]);
    expect(() => candidateCsv("roll_number,full_name,father_name\ncck-1,A,F\nCCK-1,B,G")).toThrow(/duplicate/);
  });
  it("supports Unicode, BOM, CRLF, quoted commas, escaped quotes, and embedded newlines", () => {
    const rows = candidateCsv(
      '\uFEFFemail,full_name,roll_number,status\r\nAPPROVED@gmail.com,"محمد, ""احمد""\nKamran",CCK-1,DISABLED\r\n',
    );
    expect(rows).toEqual([
      {
        email: "approved@gmail.com",
        full_name: 'محمد, "احمد"\nKamran',
        father_name: null,
        roll_number: "CCK-1",
        google_subject: null,
        status: "DISABLED",
      },
    ]);
  });
  it("defaults approval explicitly and supports verified subject mapping", () => {
    expect(
      candidateCsv(
        "email,full_name,roll_number,google_subject\na@gmail.com,Ahmad,1,stable-sub",
      )[0],
    ).toMatchObject({ status: "APPROVED", google_subject: "stable-sub" });
  });
  it.each([
    "email,name,roll_number\na@gmail.com,A,1",
    "email,email,full_name,roll_number\na@gmail.com,a@gmail.com,A,1",
    'email,full_name,roll_number\na@gmail.com,"A,1',
    "email,full_name,roll_number\na@gmail.com,A,1,extra",
    "email,full_name,roll_number,status\na@gmail.com,A,1,ADMIN",
    "email,full_name,roll_number\na@gmail.com,A,1\nA@gmail.com,B,2",
  ])(
    "rejects malformed input without creating partial records: %s",
    (input) => {
      expect(() => candidateCsv(input)).toThrow();
    },
  );
});
