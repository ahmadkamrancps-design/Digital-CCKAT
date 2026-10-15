import { useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import CCKLogo from "../../components/CCKLogo";
import { gradingApi } from "../../services/grading";
import { ApiError } from "../../services/api";
import type { Grade, GradingExam, ManualResponse } from "../../types/grading";
import { useAuth } from "../auth/AuthProvider";
import {
  Pager,
  RemoteStatus,
  TaskStatus,
  useRemote,
  useTask,
} from "../admin/shared";
import "../admin/admin.css";
import "./grading.css";

export function GradingPage() {
  const { profile, isPreview } = useAuth();
  if (!profile)
    return isPreview ? (
      <main id="main" className="card session-state">
        <h1>Examiner sign-in required</h1>
        <p>Grading requires an approved examiner or administrator account.</p>
      </main>
    ) : (
      <Navigate to="/" replace />
    );
  if (!["ADMIN", "EXAMINER"].includes(profile.user.role))
    return <Navigate to="/dashboard" replace />;
  return <GradingWorkspace key={profile.user.id} />;
}

function GradingWorkspace() {
  const { profile, signOut } = useAuth();
  const client = useMemo(
    () => gradingApi(profile?.csrf_token || ""),
    [profile?.csrf_token],
  );
  const catalog = useRemote("grading-exams", client.exams);
  const task = useTask();
  const [exam, setExam] = useState("");
  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="sidebar-brand">
          <CCKLogo size={60} />
          <div>
            <strong>Cadet College</strong>
            <span>Kohat · Examiner</span>
          </div>
        </div>
        <nav aria-label="Grading navigation">
          <Link to="/dashboard">Staff dashboard</Link>
          {profile?.user.role === "ADMIN" && (
            <Link to="/admin/exams">Exam management</Link>
          )}
        </nav>
      </aside>
      <main id="main" className="admin-content" tabIndex={-1}>
        <header className="admin-header">
          <span>Grading &amp; results</span>
          <bdi>{profile?.user.display_name}</bdi>
          <button
            disabled={task.pending}
            onClick={() => {
              void task.run(signOut);
            }}
          >
            Sign out
          </button>
        </header>
        <h1>Examiner workspace</h1>
        <p>
          Review submitted short answers. Marks and corrections remain separate
          from the candidate’s response.
        </p>
        <TaskStatus task={task} />
        <RemoteStatus resource={catalog} />
        {!catalog.error && (
          <label>
            Exam to grade{" "}
            <select
              value={exam}
              onChange={(event) => setExam(event.target.value)}
            >
              <option value="">Choose exam</option>
              {catalog.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        )}
        {!catalog.error && catalog.data?.find((item) => item.id === exam) && (
          <ExamGrading
            key={exam}
            exam={catalog.data.find((item) => item.id === exam)!}
            refreshAccess={catalog.reload}
          />
        )}
      </main>
    </div>
  );
}

function ExamGrading({
  exam,
  refreshAccess,
}: {
  exam: GradingExam;
  refreshAccess: () => Promise<void>;
}) {
  const { profile } = useAuth();
  const client = useMemo(
    () => gradingApi(profile?.csrf_token || ""),
    [profile?.csrf_token],
  );
  const [includeGraded, setIncludeGraded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [attemptOffset, setAttemptOffset] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const queue = useRemote(`${exam.id}:${offset}:${includeGraded}`, () =>
    client.queue(exam.id, offset, includeGraded),
  );
  const roster = useRemote(`${exam.id}:${attemptOffset}`, () =>
    client.attempts(exam.id, attemptOffset),
  );
  const task = useTask();
  const refresh = async () => {
    await Promise.all([queue.reload(), roster.reload(), refreshAccess()]);
  };
  if (blocked)
    return (
      <section className="admin-panel" role="alert">
        Access to this exam is no longer available. Choose another exam or sign
        in again.
      </section>
    );
  return (
    <>
      <section className="admin-panel">
        <h2>Grading status</h2>
        <RemoteStatus resource={roster} />
        <TaskStatus task={task} />
        <button
          onClick={() => {
            void refresh();
          }}
        >
          Refresh grading
        </button>
        {!roster.error && (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <caption>Candidate grading progress</caption>
              <thead>
                <tr>
                  <th>Roll number</th>
                  <th>Candidate</th>
                  <th>Status</th>
                  <th>Pending responses</th>
                  <th>Marks</th>
                  {profile?.user.role === "ADMIN" && <th>Action</th>}
                </tr>
              </thead>
              <tbody>
                {roster.data?.map((row) => (
                  <tr key={row.attempt_id}>
                    <td>
                      <bdi>{row.roll_number}</bdi>
                    </td>
                    <td>
                      <bdi>{row.full_name}</bdi>
                    </td>
                    <td>
                      {row.status} · {row.grading_status}
                    </td>
                    <td>{row.pending_answers}</td>
                    <td>
                      {row.marks_awarded ?? "Pending"} / {row.maximum_marks}
                    </td>
                    {profile?.user.role === "ADMIN" && (
                      <td>
                        <button
                          disabled={
                            task.pending ||
                            row.status !== "SUBMITTED" ||
                            exam.results_released
                          }
                          onClick={() => {
                            void task.run(async () => {
                              await client.automatic(row.attempt_id);
                              await refresh();
                            }, "Automatic grading checked.");
                          }}
                        >
                          Grade automatic answers for {row.roll_number}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager
          offset={attemptOffset}
          count={roster.data?.length || 0}
          setOffset={setAttemptOffset}
        />
      </section>
      <section className="admin-panel">
        <h2>Manual review queue</h2>
        <p>
          Published or scheduled results must be withheld before marks can
          change.
        </p>
        <label>
          <input
            type="checkbox"
            checked={includeGraded}
            onChange={(event) => {
              setIncludeGraded(event.target.checked);
              setOffset(0);
            }}
          />{" "}
          Include graded responses
        </label>
        <RemoteStatus resource={queue} />
        {!queue.error &&
          queue.data?.map((row) => (
            <Review
              key={`${row.answer_id}:${row.current_grade?.revision || 0}`}
              row={row}
              frozen={exam.results_released}
              saved={refresh}
              denied={() => setBlocked(true)}
            />
          ))}
        {!queue.error && queue.data?.length === 0 && (
          <p>No responses need review in this view.</p>
        )}
        <Pager
          offset={offset}
          count={queue.data?.length || 0}
          setOffset={setOffset}
        />
      </section>
    </>
  );
}

function Review({
  row,
  frozen,
  saved,
  denied,
}: {
  row: ManualResponse;
  frozen: boolean;
  saved: () => Promise<void>;
  denied: () => void;
}) {
  const { profile } = useAuth();
  const client = useMemo(
    () => gradingApi(profile?.csrf_token || ""),
    [profile?.csrf_token],
  );
  const [marks, setMarks] = useState(row.current_grade?.marks_awarded || "");
  const [notes, setNotes] = useState("");
  const [history, setHistory] = useState<Grade[] | null>(null);
  const task = useTask();
  async function guarded(work: () => Promise<void>) {
    try {
      await work();
    } catch (cause) {
      if (cause instanceof ApiError && [401, 403, 404].includes(cause.status))
        denied();
      throw cause;
    }
  }
  return (
    <article className="grading-response">
      <h3>
        {row.subject_name} · Question {row.question_number}
      </h3>
      <p dir={row.direction} className="grading-text">
        {row.prompt}
      </p>
      <h4>Submitted response</h4>
      <p dir="auto" className="grading-answer">
        {row.answer_text || "(No answer)"}
      </p>
      {row.current_grade && (
        <p>
          Current marks: {row.current_grade.marks_awarded} / {row.maximum_marks}{" "}
          · Revision {row.current_grade.revision}
        </p>
      )}
      <TaskStatus task={task} />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void task.run(
            () =>
              guarded(async () => {
                await client.grade(row.answer_id, {
                  expected_revision: row.current_grade?.revision || 0,
                  marks_awarded: marks,
                  notes,
                });
                await saved();
              }),
            "Grade saved.",
          );
        }}
      >
        <fieldset disabled={frozen || task.pending}>
          <legend>Grade this response</legend>
          <label>
            Marks for question {row.question_number}
            <input
              type="number"
              min="0"
              max={row.maximum_marks}
              step="0.01"
              required
              value={marks}
              onChange={(event) => setMarks(event.target.value)}
            />
          </label>
          <label>
            Examiner notes for question {row.question_number}
            <textarea
              maxLength={2000}
              required={!!row.current_grade}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
          <p>
            Maximum {row.maximum_marks}. Explain any correction in the notes.
          </p>
          <button className="primary-button">
            Save grade for question {row.question_number}
          </button>
        </fieldset>
      </form>
      <button
        disabled={task.pending}
        onClick={() => {
          void task.run(
            () =>
              guarded(async () =>
                setHistory(await client.history(row.answer_id)),
              ),
            "History loaded.",
          );
        }}
      >
        View history for question {row.question_number}
      </button>
      {history && (
        <ol aria-label={`Grade history for question ${row.question_number}`}>
          {history.map((item) => (
            <li key={item.id}>
              Revision {item.revision}: {item.marks_awarded} /{" "}
              {item.maximum_marks} · {item.method} ·{" "}
              <time dateTime={item.graded_at}>
                {new Date(item.graded_at).toLocaleString()}
              </time>
              {item.graded_by && (
                <>
                  {" "}
                  · Examiner <bdi>{item.graded_by}</bdi>
                </>
              )}
              <p className="grading-text">{item.notes}</p>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
