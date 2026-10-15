import { test, expect, type BrowserContext } from "./fixtures";
import type { PresenceWrite, SessionEvent } from "../src/types/proctor";

function sharedState() {
  return {
    start: Date.now(),
    lastSeen: null as string | null,
    question: null as number | null,
    events: [] as SessionEvent[],
    nonces: new Set<string>(),
    presenceFail: true,
    monitorFail: false,
    revoked: false,
    assigned: false,
    savedOption: null as string | null,
    revision: 0,
  };
}
async function backend(
  context: BrowserContext,
  role: "CANDIDATE" | "PROCTOR" | "ADMIN" | "EXAMINER",
  state: ReturnType<typeof sharedState>,
) {
  const requests: string[] = [];
  const now = () => new Date().toISOString();
  const deadline = new Date(state.start + 120_000).toISOString();
  const subject = {
    id: "subject-1",
    exam_subject_id: "paper-1",
    subject_name: "English",
    sequence: 1,
    duration_minutes: 2,
    status: "ACTIVE",
    started_at: new Date(state.start).toISOString(),
    expires_at: deadline,
    submitted_at: null,
  };
  const exam = {
    id: "exam-1",
    title: "CCK Monitoring Test",
    description: "",
    status: "DRAFT",
    is_published: false,
    is_start_authorized: false,
    results_released: false,
    result_release_at: null,
    has_attempts: false,
    scheduled_start: null,
    scheduled_end: null,
    created_at: now(),
    updated_at: now(),
  };
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    requests.push(`${method} ${path}`);
    const send = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/api/me")
      return send({
        user: {
          id: role.toLowerCase(),
          email: "fixture@example.test",
          display_name: "Monitoring Staff",
          role,
        },
        candidate:
          role === "CANDIDATE"
            ? {
                id: "candidate-1",
                full_name: "Test Candidate",
                roll_number: "CCK-104",
                status: "APPROVED",
              }
            : null,
        csrf_token: "proctor-fixture-csrf",
        session_expires_at: "2030-01-01T00:00:00Z",
      });
    if (
      method !== "GET" &&
      request.headers()["x-csrf-token"] !== "proctor-fixture-csrf"
    )
      return send({ detail: "CSRF required." }, 403);
    if (path === "/api/proctor/exams")
      return send(
        state.revoked
          ? []
          : [
              {
                id: exam.id,
                title: exam.title,
                is_start_authorized: true,
                scheduled_start: null,
                scheduled_end: null,
              },
            ],
      );
    if (path === "/api/proctor/exams/exam-1/sessions") {
      if (state.revoked)
        return send({ detail: "Monitoring access revoked." }, 404);
      if (state.monitorFail)
        return send({ detail: "Temporary monitoring failure." }, 503);
      return send({
        server_time: now(),
        candidates: [
          {
            candidate_id: "candidate-1",
            roll_number: "CCK-104",
            full_name: "Test Candidate",
            access_active: true,
            attempt_id: "attempt-1",
            state: "TESTING",
            subject_attempt_id: subject.id,
            subject_name: "English",
            subject_status: "ACTIVE",
            question_count: 1,
            reported_question_sequence: state.question,
            expires_at: deadline,
            remaining_seconds: 120,
            connection: state.lastSeen ? "ONLINE" : "UNKNOWN",
            last_seen_at: state.lastSeen,
            review_event_count: state.events.filter((event) =>
              [
                "FULLSCREEN_EXIT",
                "CONNECTION_LOST",
                "VISIBILITY_HIDDEN",
              ].includes(event.event_type),
            ).length,
          },
        ],
      });
    }
    if (path === "/api/proctor/attempts/attempt-1/events")
      return state.revoked
        ? send({ detail: "Monitoring access revoked." }, 404)
        : send([...state.events].reverse());
    if (path === "/api/candidate/attempts/attempt-1")
      return send({
        id: "attempt-1",
        exam_id: exam.id,
        status: "IN_PROGRESS",
        started_at: subject.started_at,
        submitted_at: null,
        server_time: now(),
        subjects: [subject],
      });
    if (path.endsWith("/questions") && role === "CANDIDATE")
      return send({
        subject,
        server_time: now(),
        questions: [
          {
            exam_question_id: "q1",
            question_id: "bank-q1",
            type: "MCQ",
            prompt: "Choose the answer to preserve.",
            marks: "1.00",
            sequence: 1,
            direction: "ltr",
            language: "en",
            options: [
              { id: "a", text: "Alpha" },
              { id: "b", text: "Beta" },
            ],
            answer: {
              exam_question_id: "q1",
              selected_option_id: state.savedOption,
              short_answer_text: null,
              is_marked_for_review: false,
              revision: state.revision,
              last_saved_at: null,
            },
          },
        ],
      });
    if (path.endsWith("/presence") && role === "CANDIDATE") {
      if (state.presenceFail)
        return send({ detail: "Monitoring unavailable." }, 503);
      const body = request.postDataJSON() as PresenceWrite;
      state.lastSeen = now();
      state.question = body.question_sequence;
      for (const event of body.events)
        if (!state.nonces.has(event.event_id)) {
          state.nonces.add(event.event_id);
          state.events.push({
            id: event.event_id,
            event_type: event.event_type,
            source: "CLIENT",
            subject_attempt_id: body.subject_attempt_id,
            server_timestamp: now(),
          });
        }
      return send({ server_time: now() });
    }
    if (
      path.includes("/answers/") &&
      method === "PUT" &&
      role === "CANDIDATE"
    ) {
      state.savedOption = request.postDataJSON().selected_option_id;
      state.revision++;
      return send({
        server_time: now(),
        answer: {
          exam_question_id: "q1",
          revision: state.revision,
          selected_option_id: state.savedOption,
          short_answer_text: null,
          is_marked_for_review: false,
          last_saved_at: now(),
        },
      });
    }
    if (role === "ADMIN") {
      if (path === '/api/admin/examiners' || path.endsWith('/examiners')) return send([]);
      if (path === "/api/admin/proctors")
        return send([{ id: "proctor-1", display_name: "Approved Proctor" }]);
      if (
        path === "/api/admin/exams/exam-1/proctors/proctor-1" &&
        method === "PUT"
      )
        state.assigned = request.postDataJSON().is_active;
      if (path.includes("/proctors"))
        return send(
          state.assigned
            ? [
                {
                  user_id: "proctor-1",
                  display_name: "Approved Proctor",
                  is_active: true,
                  user_is_active: true,
                },
              ]
            : [],
        );
      if (path === "/api/admin/exams/exam-1") return send(exam);
      if (path === "/api/admin/subjects" || path.endsWith("/subjects"))
        return send([]);
    }
    return send({ detail: "Unexpected fixture request." }, 404);
  });
  return requests;
}

test("monitoring failure does not block answers; recovered browser events reach the proctor and revocation clears the roster", async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(60_000);
  const state = sharedState();
  const requests = await backend(context, "PROCTOR", state);
  const candidateContext = await browser.newContext();
  await candidateContext.route(
    /^https:\/\/fonts\.(googleapis|gstatic)\.com\//,
    (route) => route.abort(),
  );
  try {
    await backend(candidateContext, "CANDIDATE", state);
    const candidate = await candidateContext.newPage();
    await candidate.goto("http://127.0.0.1:5174/exam?attempt=attempt-1");
    await candidate.getByRole("radio", { name: "Alpha" }).check();
    await expect(candidate.getByText("Saved", { exact: true })).toBeVisible();
    expect(state.savedOption).toBe("a");
    state.presenceFail = false;
    await candidate.evaluate(() => {
      document.dispatchEvent(new Event("fullscreenchange"));
      window.dispatchEvent(new Event("online"));
    });
    await expect.poll(() => state.lastSeen).not.toBeNull();
    await page.goto("/proctor");
    await page.getByLabel("Exam to monitor").selectOption("exam-1");
    await expect(page.getByText("Reported question 1 / 1")).toBeVisible();
    await expect(page.getByText("Online · recent contact")).toBeVisible();
    await page
      .getByRole("button", { name: "Inspect events for CCK-104" })
      .click();
    await expect(
      page.getByText("FULLSCREEN EXIT", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/do not establish misconduct/)).toBeVisible();
    expect(
      requests.some(
        (path) => path.includes("/questions") || path.includes("/answers"),
      ),
    ).toBe(false);
    await page.screenshot({
      path: "test-results/proctor-dashboard.png",
      fullPage: true,
    });
    state.monitorFail = true;
    await page
      .getByRole("button", { name: "Refresh status", exact: true })
      .click();
    await expect(page.getByText(/status may be stale/)).toBeVisible();
    await expect(
      page.getByText("Test Candidate", { exact: true }),
    ).toBeVisible();
    state.revoked = true;
    await page
      .getByRole("button", { name: "Refresh status", exact: true })
      .click();
    await expect(page.getByText("Test Candidate", { exact: true })).toHaveCount(
      0,
    );
  } finally {
    await candidateContext.close();
  }
});

test("administrator assigns and revokes proctor access through the exam workspace", async ({
  page,
  context,
}) => {
  const state = sharedState();
  await backend(context, "ADMIN", state);
  page.on("dialog", (dialog) => {
    void dialog.accept();
  });
  await page.goto("/admin/exams/exam-1");
  await page.getByLabel("Proctor to assign").selectOption("proctor-1");
  await page
    .getByRole("button", { name: "Assign proctor", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Revoke proctor" }),
  ).toBeVisible();
  expect(state.assigned).toBe(true);
  await page.getByRole("button", { name: "Revoke proctor" }).click();
  await expect(
    page.getByRole("button", { name: "Revoke proctor" }),
  ).toHaveCount(0);
  expect(state.assigned).toBe(false);
});
