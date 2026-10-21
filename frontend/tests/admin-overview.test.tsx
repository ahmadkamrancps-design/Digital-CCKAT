import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../src/App";
import { AuthProvider, useAuth } from "../src/features/auth/AuthProvider";
import type { AdminOverview } from "../src/types/admin";

const summary: AdminOverview = {
  candidate_count: 1250,
  approved_candidates: 1200,
  exam_count: 1,
  published_exams: 0,
  question_count: 90,
  active_questions: 88,
  subject_count: 3,
  active_subjects: 3,
  recent_exams: [
    {
      id: "exam-1",
      title: "Registered entry test",
      status: "DRAFT",
      is_published: false,
      is_start_authorized: false,
      results_released: false,
      scheduled_start: null,
    },
  ],
  recent_actions: [
    {
      id: "action-1",
      actor_name: "Approved Administrator",
      event_type: "EXAM_CREATED",
      server_timestamp: "2026-10-20T09:00:00Z",
    },
  ],
};
const profile = {
  user: {
    id: "admin-1",
    email: "admin@example.test",
    display_name: "Approved Administrator",
    role: "ADMIN",
  },
  candidate: null,
  csrf_token: "test-csrf",
  session_expires_at: "2030-01-01T00:00:00Z",
};
function SessionIndicator() {
  return (
    <output aria-label="Session role">
      {useAuth().profile?.user.role || "Anonymous"}
    </output>
  );
}
function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
        <SessionIndicator />
      </AuthProvider>
    </MemoryRouter>,
  );
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => {
  vi.stubEnv("DEV", true);
  vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "false");
  vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it.each([
  { dev: true, enabled: true, visible: true },
  { dev: false, enabled: true, visible: false },
  { dev: true, enabled: false, visible: false },
])(
  "shows local management entry only when development=$dev and enabled=$enabled",
  async ({ dev, enabled, visible }) => {
    vi.stubEnv("DEV", dev);
    vi.stubEnv("VITE_MANAGEMENT_SANDBOX", String(enabled));
    const fetcher = vi.fn(async (_path: string) =>
      json({ detail: "Sign in." }, 401),
    );
    vi.stubGlobal("fetch", fetcher);
    renderPage("/");
    await screen.findByLabelText("Roll number");
    const entry = screen.queryByRole("link", {
      name: "Open test administration →",
    });
    if (visible) {
      expect(entry).toHaveAttribute("href", "/api/local-management");
      expect(
        screen.getByText(/Local management sandbox · Test data only/),
      ).toBeInTheDocument();
    } else {
      expect(entry).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Local management sandbox · Test data only/),
      ).not.toBeInTheDocument();
    }
    expect(screen.getByLabelText("Session role")).toHaveTextContent(
      "Anonymous",
    );
    expect(fetcher.mock.calls.every(([path]) => path === "/api/me")).toBe(true);
  },
);

it("loads administrator totals from one aggregate API without downloading candidate records", async () => {
  const fetcher = vi.fn(async (path: string) =>
    json(path === "/api/me" ? profile : summary),
  );
  vi.stubGlobal("fetch", fetcher);
  renderPage("/admin");
  const totals = await screen.findByRole("region", {
    name: "Administration totals",
  });
  expect(
    within(totals).getByRole("link", { name: /Registered candidates/ }),
  ).toHaveTextContent("1,250");
  expect(
    screen.getByRole("link", { name: "Manage Registered entry test" }),
  ).toHaveAttribute("href", "/admin/exams/exam-1");
  expect(screen.getByRole("link", { name: "Create an exam" })).toHaveAttribute(
    "href",
    "/admin/exams/new",
  );
  expect(screen.getByText("Exam created")).toBeInTheDocument();
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
    "/api/me",
    "/api/admin/overview",
  ]);
});

it("shows an actionable empty overview and retries a failed load without fabricated totals", async () => {
  let fail = true;
  const fetcher = vi.fn(async (path: string) =>
    path === "/api/me"
      ? json(profile)
      : fail
        ? json({ detail: "Summary temporarily unavailable." }, 503)
        : json({ ...summary, recent_exams: [], recent_actions: [] }),
  );
  vi.stubGlobal("fetch", fetcher);
  renderPage("/admin");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Summary temporarily unavailable.",
  );
  expect(
    screen.queryByRole("region", { name: "Administration totals" }),
  ).not.toBeInTheDocument();
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Retry loading" }));
  expect(
    await screen.findByText("Your first exam starts here"),
  ).toBeInTheDocument();
  expect(screen.getByText("No staff activity yet")).toBeInTheDocument();
});

it("opens a read-only administration preview, filters sample records and never creates an admin session", async () => {
  vi.stubEnv("VITE_ENABLE_UI_PREVIEW", "true");
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  renderPage("/");
  await userEvent.click(
    screen.getByRole("link", { name: "Explore administration design →" }),
  );
  expect(
    screen.getByRole("heading", { name: "Administration overview" }),
  ).toBeInTheDocument();
  const navigation = screen.getByRole("navigation", {
    name: "Administration",
  });
  await userEvent.click(
    within(navigation).getByRole("link", { name: "Candidates" }),
  );
  await userEvent.type(
    screen.getByLabelText("Search candidates"),
    "CCK-DEMO-003",
  );
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.getByText("نمونہ امیدوار")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Status"), "disabled");
  expect(screen.getByText("No matching candidates")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Create candidate · View only" }),
  ).toBeDisabled();
  for (const [label, heading] of [
    ["Exams & builder", "Exam management"],
    ["Subjects", "Subject catalog"],
    ["Question bank", "Question bank"],
    ["Staff actions", "Staff action history"],
  ]) {
    await userEvent.click(
      within(navigation).getByRole("link", { name: label }),
    );
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  }
  expect(screen.getByLabelText("Session role")).toHaveTextContent("Anonymous");
  expect(fetcher).not.toHaveBeenCalled();
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
}, 15000);

it.each([
  { dev: false, preview: true },
  { dev: true, preview: false },
])(
  "denies the design route when development=$dev and preview=$preview",
  async ({ dev, preview }) => {
    vi.stubEnv("DEV", dev);
    vi.stubEnv("VITE_ENABLE_UI_PREVIEW", String(preview));
    const fetcher = vi.fn(async (_path: string) =>
      json({ detail: "Sign in." }, 401),
    );
    vi.stubGlobal("fetch", fetcher);
    renderPage("/preview/admin");
    expect(await screen.findByLabelText("Roll number")).toBeInTheDocument();
    expect(
      screen.queryByText("Sample Class 8 Entry Test"),
    ).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every(([path]) => path === "/api/me")).toBe(true);
  },
);
