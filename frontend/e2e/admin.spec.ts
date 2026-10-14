import { test, expect, type BrowserContext } from "./fixtures";
import type {
  AdminCandidate,
  AdminExam,
  AdminExamSubject,
  AdminPaper,
  AdminQuestion,
  AdminSubject,
} from "../src/types/admin";

async function backend(
  context: BrowserContext,
  role: "ADMIN" | "PROCTOR" = "ADMIN",
) {
  const candidates: AdminCandidate[] = [];
  const subjects: AdminSubject[] = [];
  const questions: AdminQuestion[] = [];
  const exams: AdminExam[] = [];
  const papers: AdminExamSubject[] = [];
  const selections = new Map<string, AdminPaper>();
  let serial = 0;
  let errors = false;
  const requests: string[] = [];
  const timestamp = () => new Date(Date.now() + ++serial).toISOString();
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    requests.push(`${method} ${path}`);
    const send = (value: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (path === "/api/me")
      return send({
        user: {
          id: "admin-user",
          email: "admin@example.test",
          display_name: "Browser Administrator",
          role,
        },
        candidate: null,
        csrf_token: "browser-csrf",
        session_expires_at: "2030-01-01T09:00:00Z",
      });
    if (role !== "ADMIN")
      return send({ detail: "Administrator access required." }, 403);
    if (
      method !== "GET" &&
      request.headers()["x-csrf-token"] !== "browser-csrf"
    )
      return send({ detail: "CSRF required." }, 403);
    const body = method === "GET" ? {} : request.postDataJSON();
    if (method !== "GET" && errors)
      return send(
        { detail: "Temporary save failure. Keep your edits and retry." },
        503,
      );
    if (path === "/api/admin/candidates" && method === "GET")
      return send(candidates);
    if (path === "/api/admin/candidates" && method === "POST") {
      const row: AdminCandidate = {
        ...body,
        id: `candidate-${++serial}`,
        user_id: `user-${serial}`,
        is_active: body.status === "APPROVED",
        created_at: timestamp(),
        updated_at: timestamp(),
      };
      candidates.push(row);
      return send(row, 201);
    }
    if (path === "/api/admin/candidates/import") {
      const rows = body.candidates as AdminCandidate[];
      if (
        rows.some((row) =>
          candidates.some(
            (current) =>
              current.email === row.email ||
              current.roll_number === row.roll_number,
          ),
        )
      )
        return send(
          { detail: "Duplicate candidate. No candidates were saved." },
          409,
        );
      const created = rows.map((row) => ({
        ...row,
        id: `candidate-${++serial}`,
        user_id: `user-${serial}`,
        is_active: row.status === "APPROVED",
        created_at: timestamp(),
        updated_at: timestamp(),
      }));
      candidates.push(...created);
      return send(created, 201);
    }
    if (path.startsWith("/api/admin/candidates/") && method === "PUT") {
      const row = candidates.find((row) => path.endsWith(`/${row.id}`))!;
      Object.assign(row, body, {
        is_active: body.status === "APPROVED",
        updated_at: timestamp(),
      });
      return send(row);
    }
    if (path === "/api/admin/subjects" && method === "GET")
      return send(subjects);
    if (path === "/api/admin/subjects" && method === "POST") {
      const row: AdminSubject = {
        ...body,
        id: `subject-${++serial}`,
        created_at: timestamp(),
        updated_at: timestamp(),
      };
      subjects.push(row);
      return send(row, 201);
    }
    if (path === "/api/admin/questions" && method === "GET")
      return send(
        questions.filter(
          (row) =>
            !url.searchParams.get("subject_id") ||
            row.subject_id === url.searchParams.get("subject_id"),
        ),
      );
    if (path === "/api/admin/questions" && method === "POST") {
      const row: AdminQuestion = {
        ...body,
        id: `question-${++serial}`,
        created_at: timestamp(),
        updated_at: timestamp(),
        options: (body.options || []).map(
          (option: { text: string; is_correct: boolean }, index: number) => ({
            ...option,
            id: `option-${serial}-${index}`,
            display_order: index + 1,
          }),
        ),
        grading: body.grading || null,
        accepted_answers: body.accepted_answers || [],
      };
      questions.push(row);
      return send(row, 201);
    }
    if (path === "/api/admin/exams" && method === "GET") return send(exams);
    if (path === "/api/admin/exams" && method === "POST") {
      const row: AdminExam = {
        ...body,
        id: `exam-${++serial}`,
        is_start_authorized: false,
        has_attempts: false,
        results_released: false,
        created_at: timestamp(),
        updated_at: timestamp(),
      };
      exams.push(row);
      return send(row, 201);
    }
    const exam = exams.find((row) =>
      path.startsWith(`/api/admin/exams/${row.id}`),
    );
    if (exam) {
      if (path.endsWith(`/${exam.id}`) && method === "GET") return send(exam);
      if (path.endsWith("/subjects") && method === "GET")
        return send(papers.filter((paper) => paper.exam_id === exam.id));
      if (path.endsWith("/subjects") && method === "POST") {
        const row: AdminExamSubject = {
          ...body,
          id: `paper-${++serial}`,
          exam_id: exam.id,
          total_marks: "0",
          question_count: 0,
        };
        papers.push(row);
        selections.set(row.id, {
          exam_subject_id: row.id,
          questions: [],
          total_marks: "0",
        });
        return send(row, 201);
      }
      if (path.endsWith("/publication")) {
        if (
          body.published &&
          papers.some(
            (paper) => paper.exam_id === exam.id && !paper.question_count,
          )
        )
          return send({ detail: "Every subject needs a paper." }, 409);
        exam.is_published = body.published;
        if (!body.published) exam.is_start_authorized = false;
        return send(exam);
      }
      if (path.endsWith("/start-authorization")) {
        exam.is_start_authorized = body.authorized;
        return send({ is_start_authorized: body.authorized });
      }
      if (path.endsWith("/result-release")) {
        exam.result_release_at = body.result_release_at;
        return send(exam);
      }
    }
    const paper = papers.find(
      (row) => path === `/api/admin/exam-subjects/${row.id}/questions`,
    );
    if (paper) {
      if (method === "GET") return send(selections.get(paper.id));
      if (exams.find((exam) => exam.id === paper.exam_id)?.is_start_authorized)
        return send({ detail: "Exam is locked." }, 409);
      const selected: AdminPaper = {
        exam_subject_id: paper.id,
        questions: body.questions.map(
          (
            entry: { question_id: string; marks_override: string | null },
            index: number,
          ) => ({
            ...entry,
            id: `selection-${++serial}`,
            sequence: index + 1,
            effective_marks:
              entry.marks_override ||
              questions.find((row) => row.id === entry.question_id)!.marks,
          }),
        ),
        total_marks: "3.00",
      };
      selections.set(paper.id, selected);
      paper.question_count = selected.questions.length;
      paper.total_marks = selected.total_marks;
      return send(selected);
    }
    return send(
      { detail: `Unexpected fixture request ${method} ${path}` },
      404,
    );
  });
  return {
    candidates,
    subjects,
    questions,
    exams,
    papers,
    selections,
    requests,
    fail: (value: boolean) => {
      errors = value;
    },
  };
}
test.beforeEach(async ({ page }) => {
  page.on("dialog", (dialog) => {
    void dialog.accept();
  });
});

test("admin creates and disables a candidate, reviews CSV, and preserves a rejected import", async ({
  page,
  context,
}) => {
  const fixture = await backend(context);
  await page.goto("/admin/candidates");
  await page.getByRole("button", { name: "Create candidate" }).click();
  await page.getByLabel("Full name").fill("محمد احمد");
  await page.getByLabel("Roll number").fill("CCK-201");
  await page.getByLabel("Authorized email").fill("approved@gmail.com");
  await page.getByRole("button", { name: "Save candidate" }).click();
  await page.getByRole("button", { name: "Edit CCK-201" }).click();
  await page.getByLabel("Candidate status").selectOption("DISABLED");
  await page.getByRole("button", { name: "Save candidate" }).click();
  await expect.poll(() => fixture.candidates[0].status).toBe("DISABLED");
  await page.getByRole("button", { name: "Import CSV" }).click();
  const csv =
    "email,full_name,roll_number\nsecond@gmail.com,Second Candidate,CCK-202\napproved@gmail.com,Duplicate,CCK-203";
  await page.getByLabel("CSV content").fill(csv);
  await page.getByRole("button", { name: "Review import" }).click();
  await page.getByRole("button", { name: "Import 2 candidates" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "No candidates were saved",
  );
  await expect(page.getByLabel("CSV content")).toHaveValue(csv);
  expect(fixture.candidates).toHaveLength(1);
});

test("admin builds a configured paper, changes order, and enables starts with editing locked", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000); // Several complete CRUD workflows run before paper validation.
  const fixture = await backend(context);
  await page.goto("/admin/subjects");
  await page.getByLabel("Subject name").fill("Mathematics");
  await page.getByLabel("Subject code").fill("MATH");
  await page.getByRole("button", { name: "Save subject" }).click();
  await expect.poll(() => fixture.subjects.length).toBe(1);
  await page.getByRole("link", { name: "Question bank", exact: true }).click();
  await page.getByRole("button", { name: "Create question" }).click();
  await page
    .getByLabel("Question subject")
    .selectOption(fixture.subjects[0].id);
  await page.getByLabel("Question prompt").fill("What is 2 + 2?");
  await page.getByRole("button", { name: "Remove option D" }).click();
  await page.getByRole("button", { name: "Remove option C" }).click();
  await page.getByLabel("Option A text").fill("4");
  await page.getByLabel("Option B text").fill("5");
  await page.getByRole("button", { name: "Save question" }).click();
  await expect.poll(() => fixture.questions.length).toBe(1);
  await page.getByRole("button", { name: "Create question" }).click();
  await page
    .getByLabel("Question subject")
    .selectOption(fixture.subjects[0].id);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("SHORT_ANSWER");
  await page.getByLabel("Question prompt").fill("Find x in 3(x + 5) = 24.");
  await page.getByLabel("Marks", { exact: true }).fill("2");
  await page.getByLabel("Grading mode").selectOption("NUMERIC");
  await page.getByLabel("Accepted answers (one per line)").fill("3");
  await page.getByRole("button", { name: "Save question" }).click();
  await expect.poll(() => fixture.questions.length).toBe(2);
  await page.getByRole("link", { name: "Exams & builder" }).click();
  await page.getByRole("link", { name: "Create exam", exact: true }).click();
  await page.getByLabel("Exam title").fill("CCK Mock Admission Test");
  await page.getByRole("button", { name: "Create unpublished exam" }).click();
  await expect(
    page.getByRole("heading", { name: "CCK Mock Admission Test", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Subject", exact: true })
    .selectOption(fixture.subjects[0].id);
  await page.getByLabel("Duration (minutes)").fill("45");
  await page.getByRole("button", { name: "Add subject", exact: true }).click();
  await expect(page.getByLabel("Sequence")).toHaveValue("2");
  await page.getByRole("button", { name: "Build paper 1" }).click();
  await page
    .getByRole("button", { name: "Add question: What is 2 + 2?" })
    .click();
  await page
    .getByRole("button", { name: "Add question: Find x in 3(x + 5) = 24." })
    .click();
  await page.getByRole("button", { name: "Move question 2 earlier" }).click();
  await page.getByLabel("Marks override for question 1").fill("2");
  fixture.fail(true);
  await page.getByRole("button", { name: "Save ordered paper" }).click();
  await expect(page.getByRole("alert")).toContainText("Temporary save failure");
  expect(fixture.selections.get(fixture.papers[0].id)?.questions).toHaveLength(
    0,
  );
  fixture.fail(false);
  await page.getByRole("button", { name: "Save ordered paper" }).click();
  await expect
    .poll(() => fixture.selections.get(fixture.papers[0].id)?.questions.length)
    .toBe(2);
  expect(
    fixture.selections.get(fixture.papers[0].id)?.questions[0].question_id,
  ).toBe(fixture.questions[1].id);
  await page.getByRole("button", { name: "Publish exam", exact: true }).click();
  await expect.poll(() => fixture.exams[0].is_published).toBe(true);
  await page
    .getByRole("button", { name: "Enable starts", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Pause starts" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save ordered paper" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Release results (grading required)" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/admin-exam-workspace.png",
    fullPage: true,
  });
});

test("proctor cannot open admin tools or fetch question keys", async ({
  page,
  context,
}) => {
  const fixture = await backend(context, "PROCTOR");
  await page.goto("/admin/questions");
  await expect(
    page.getByRole("heading", { name: "Staff workspace" }),
  ).toBeVisible();
  expect(fixture.requests.some((path) => path.includes("/api/admin/"))).toBe(
    false,
  );
});
