import { test, expect, type BrowserContext } from "./fixtures";
import type { Grade } from "../src/types/grading";

async function backend(
  context: BrowserContext,
  role: "EXAMINER" | "CANDIDATE" | "ADMIN",
) {
  const state = {
    grades: [] as Grade[],
    released: false,
    ready: false,
    assigned: false,
  };
  const exam = {
    id: "exam-1",
    title: "CCK Admission Test",
    description: "",
    status: "DRAFT",
    is_published: true,
    is_start_authorized: false,
    results_released: false,
    result_release_at: null,
    has_attempts: true,
    scheduled_start: null,
    scheduled_end: null,
    created_at: "2026-10-15T10:00:00Z",
    updated_at: "2026-10-15T10:00:00Z",
  };
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const send = (value: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (path === "/api/me")
      return send({
        user: {
          id: "staff-1",
          email: null,
          display_name: "CCK Test User",
          role,
        },
        candidate:
          role === "CANDIDATE"
            ? {
                id: "candidate",
                full_name: "Test Candidate",
                roll_number: "CCK-104",
                status: "APPROVED",
              }
            : null,
        csrf_token: "browser-csrf",
        session_expires_at: "2030-01-01T00:00:00Z",
      });
    if (
      method !== "GET" &&
      request.headers()["x-csrf-token"] !== "browser-csrf"
    )
      return send({ detail: "CSRF required." }, 403);
    if (path === "/api/grading/exams")
      return send([{ ...exam, results_released: state.released }]);
    if (path.endsWith("/attempts")) return send([]);
    if (path.endsWith("/queue"))
      return send(
        state.grades.length && !request.url().includes("include_graded=true")
          ? []
          : [
              {
                answer_id: "answer-1",
                attempt_id: "attempt-1",
                subject_name: "Urdu",
                question_number: 1,
                prompt: "مختصر جواب لکھیں۔",
                direction: "rtl",
                answer_text: "پاکستان",
                maximum_marks: "2.00",
                current_grade: state.grades.at(-1) || null,
              },
            ],
      );
    if (path.endsWith("/history")) return send(state.grades);
    if (path === "/api/grading/answers/answer-1/grade") {
      const body = request.postDataJSON();
      const grade: Grade = {
        id: `grade-${state.grades.length + 1}`,
        answer_id: "answer-1",
        revision: body.expected_revision + 1,
        marks_awarded: body.marks_awarded,
        maximum_marks: "2.00",
        method: "MANUAL",
        graded_by: "staff-1",
        graded_at: "2026-10-15T10:00:00Z",
        notes: body.notes,
      };
      state.grades.push(grade);
      return send(grade);
    }
    if (path === "/api/candidate/results")
      return send([
        {
          attempt_id: "attempt-1",
          exam_id: exam.id,
          exam_title: exam.title,
          grading_status: "COMPLETE",
          publication_status: state.released ? "RELEASED" : "WITHHELD",
          subjects: state.released
            ? [
                {
                  subject_name: "Urdu",
                  sequence: 1,
                  maximum_marks: "100.00",
                  marks_awarded: "82.50",
                  pending_answers: 0,
                },
              ]
            : [],
          maximum_marks: state.released ? "100.00" : null,
          marks_awarded: state.released ? "82.50" : null,
          percentage: state.released ? "82.50" : null,
        },
      ]);
    if (path === "/api/admin/examiners")
      return send([{ id: "examiner-1", display_name: "Approved Examiner" }]);
    if (path.endsWith("/examiners/examiner-1") && method === "PUT") {
      state.assigned = request.postDataJSON().is_active;
      return send([
        {
          user_id: "examiner-1",
          display_name: "Approved Examiner",
          is_active: state.assigned,
        },
      ]);
    }
    if (path.endsWith("/examiners"))
      return send(
        state.assigned
          ? [
              {
                user_id: "examiner-1",
                display_name: "Approved Examiner",
                is_active: true,
              },
            ]
          : [],
      );
    if (path === "/api/admin/exams/exam-1/result-release") {
      if (request.postDataJSON().released && !state.ready)
        return send(
          { detail: "Complete grading before releasing results." },
          409,
        );
      state.released = request.postDataJSON().released;
      return send({ ...exam, results_released: state.released });
    }
    if (path === "/api/admin/exams/exam-1")
      return send({ ...exam, results_released: state.released });
    if (
      path === "/api/admin/subjects" ||
      path === "/api/admin/proctors" ||
      path.endsWith("/subjects") ||
      path.endsWith("/proctors")
    )
      return send([]);
    throw Error(`Unexpected grading fixture request: ${method} ${path}`);
  });
  return state;
}

test("examiner records partial marks and a correction with preserved history", async ({
  page,
  context,
}) => {
  const state = await backend(context, "EXAMINER");
  await page.goto("/grading");
  await expect(
    page.getByRole("option", { name: "CCK Admission Test" }),
  ).toHaveCount(1);
  await page.getByLabel("Exam to grade").selectOption("exam-1");
  await expect(page.getByText("پاکستان", { exact: true })).toBeVisible();
  await page.getByLabel("Marks for question 1", { exact: true }).fill("1.5");
  await page.getByLabel("Examiner notes for question 1").fill("Initial review");
  await page.getByRole("button", { name: "Save grade for question 1" }).click();
  await expect(
    page.getByText("No responses need review in this view."),
  ).toBeVisible();
  await page.getByLabel("Include graded responses").check();
  await page.getByLabel("Marks for question 1", { exact: true }).fill("2");
  await page
    .getByLabel("Examiner notes for question 1")
    .fill("Rubric correction");
  await page.getByRole("button", { name: "Save grade for question 1" }).click();
  await expect.poll(() => state.grades.length).toBe(2);
  await page
    .getByRole("button", { name: "View history for question 1" })
    .click();
  await expect(
    page.getByRole("list", { name: "Grade history for question 1" }),
  ).toContainText("Rubric correction");
  expect(state.grades.map((row) => row.revision)).toEqual([1, 2]);
  await page.screenshot({
    path: "test-results/examiner-workspace.png",
    fullPage: true,
  });
});

test("candidate sees marks only after release and loses visibility after withholding", async ({
  page,
  context,
}) => {
  const state = await backend(context, "CANDIDATE");
  await page.goto("/results");
  await expect(
    page.getByText(/Your result is not available yet/),
  ).toBeVisible();
  await expect(page.getByRole("table")).not.toBeVisible();
  state.released = true;
  await page.getByRole("button", { name: "Refresh results" }).click();
  await expect(page.getByText("82.50%", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/candidate-results.png",
    fullPage: true,
  });
  state.released = false;
  await page.getByRole("button", { name: "Refresh results" }).click();
  await expect(page.getByRole("table")).not.toBeVisible();
});

test("administrator assigns an examiner and authorizes only ready results", async ({
  page,
  context,
}) => {
  const state = await backend(context, "ADMIN");
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/admin/exams/exam-1");
  await expect(
    page.getByRole("option", { name: "Approved Examiner" }),
  ).toHaveCount(1);
  await page.getByLabel("Examiner to assign").selectOption("examiner-1");
  await page
    .getByRole("button", { name: "Assign examiner", exact: true })
    .click();
  await expect.poll(() => state.assigned).toBe(true);
  await page.getByRole("button", { name: "Authorize result release" }).click();
  await expect(page.getByRole("alert")).toContainText("Complete grading");
  state.ready = true;
  await page.getByRole("button", { name: "Authorize result release" }).click();
  await expect.poll(() => state.released).toBe(true);
  await expect(page.getByText("Released", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Save release plan / keep withheld" })
    .click();
  await expect.poll(() => state.released).toBe(false);
  await page
    .getByRole("button", { name: "Revoke examiner", exact: true })
    .click();
  await expect.poll(() => state.assigned).toBe(false);
});
