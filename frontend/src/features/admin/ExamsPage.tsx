import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type {
  AdminExam,
  AdminExamSubject,
  AdminExamSubjectWrite,
  AdminExamWrite,
  AdminSubject,
} from "../../types/admin";
import {
  localDate,
  Pager,
  RemoteStatus,
  TaskStatus,
  useRemote,
  useTask,
  utcDate,
} from "./shared";
import { PaperBuilder } from "./PaperBuilder";

export function ExamsPage() {
  const client = useAdminApi();
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const list = useRemote(`${offset}:${search}`, () =>
    client.list<AdminExam>("/exams", {
      limit: "50",
      offset: String(offset),
      search,
    }),
  );
  return (
    <>
      <h1>Exam management</h1>
      <p className="admin-muted">
        Configure papers, schedule the test, publish assignments, and authorize
        starts.
      </p>
      <Link className="admin-link" to="/admin/exams/new">
        Create exam
      </Link>
      <section className="admin-panel">
        <label>
          Search exams{" "}
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <RemoteStatus resource={list} />
        <div className="admin-table-wrap">
          <table className="admin-table">
            <caption>Configured exams</caption>
            <thead>
              <tr>
                <th>Exam</th>
                <th>Publication</th>
                <th>Start access</th>
                <th>Schedule</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {list.data?.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.title}
                    <br />
                    <span className="admin-muted">{item.status}</span>
                  </td>
                  <td>{item.is_published ? "Published" : "Unpublished"}</td>
                  <td>
                    {item.is_start_authorized
                      ? "Starts enabled"
                      : "Starts paused"}
                  </td>
                  <td>
                    {item.scheduled_start
                      ? new Date(item.scheduled_start).toLocaleString()
                      : "Not scheduled"}
                  </td>
                  <td>
                    <Link className="admin-link" to={`/admin/exams/${item.id}`}>
                      Manage {item.title}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pager
          offset={offset}
          count={list.data?.length || 0}
          setOffset={setOffset}
        />
      </section>
    </>
  );
}
export function CreateExamPage() {
  return (
    <>
      <h1>Create exam</h1>
      <ExamEditor />
    </>
  );
}
function ExamEditor({
  exam,
  saved,
}: {
  exam?: AdminExam;
  saved?: () => Promise<void>;
}) {
  const client = useAdminApi();
  const task = useTask();
  const navigate = useNavigate();
  const [title, setTitle] = useState(exam?.title || "");
  const [description, setDescription] = useState(exam?.description || "");
  const [status, setStatus] = useState<AdminExamWrite["status"]>(
    exam?.status || "DRAFT",
  );
  const [start, setStart] = useState(localDate(exam?.scheduled_start || null));
  const [end, setEnd] = useState(localDate(exam?.scheduled_end || null));
  const frozen =
    !!exam &&
    (exam.has_attempts ||
      exam.is_start_authorized ||
      exam.status === "ARCHIVED");
  return (
    <section className="admin-panel">
      <h2>Exam details and schedule</h2>
      <TaskStatus task={task} />
      {frozen && (
        <p className="admin-alert">
          Configuration is locked for authorized exams, existing attempts, or
          archived exams. Pause starts before editing an exam that has no
          attempts.
        </p>
      )}
      <form
        className="admin-form"
        onSubmit={(event) => {
          event.preventDefault();
          void task.run(async () => {
            const result = await client.saveExam(
              {
                title,
                description,
                status,
                scheduled_start: utcDate(start),
                scheduled_end: utcDate(end),
                is_published: exam?.is_published || false,
                result_release_at: exam?.result_release_at || null,
              },
              exam?.id,
            );
            if (saved) await saved();
            else navigate(`/admin/exams/${result.id}`);
          });
        }}
      >
        <fieldset disabled={task.pending || frozen}>
          <legend>Exam configuration</legend>
          <label>
            Exam title
            <input
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            Description
            <textarea
              maxLength={10000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <p className="admin-muted">
            Schedule times use this device’s time zone:{" "}
            {Intl.DateTimeFormat().resolvedOptions().timeZone}. Both times are
            required together. End time is a hard cutoff for every subject.
          </p>
          <div className="admin-row">
            <label>
              Scheduled start
              <input
                type="datetime-local"
                value={start}
                required={!!end}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label>
              Scheduled end
              <input
                type="datetime-local"
                value={end}
                required={!!start}
                min={start || undefined}
                onChange={(event) => setEnd(event.target.value)}
              />
            </label>
          </div>
          {exam && (
            <label>
              Exam status
              <select
                value={status}
                onChange={(event) =>
                  setStatus(event.target.value as AdminExamWrite["status"])
                }
              >
                <option>DRAFT</option>
                <option>ARCHIVED</option>
              </select>
            </label>
          )}
          <button className="primary-button">
            {exam ? "Save exam details" : "Create unpublished exam"}
          </button>
        </fieldset>
      </form>
    </section>
  );
}
export function ExamDetailPage() {
  const { examId = "" } = useParams();
  const client = useAdminApi();
  const task = useTask();
  const [paperId, setPaperId] = useState("");
  const resource = useRemote(examId, async () => {
    const [exam, papers, subjects] = await Promise.all([
      client.exam(examId),
      client.list<AdminExamSubject>(`/exams/${examId}/subjects`),
      allAdminRows<AdminSubject>(client, "/subjects"),
    ]);
    return { exam, papers, subjects };
  });
  const data = resource.data;
  const frozen =
    !!data &&
    (data.exam.has_attempts ||
      data.exam.is_start_authorized ||
      data.exam.status === "ARCHIVED");
  return (
    <>
      <h1>{data?.exam.title || "Exam workspace"}</h1>
      <Link to="/admin/exams">← All exams</Link>
      <RemoteStatus resource={resource} />
      <TaskStatus task={task} />
      {data && (
        <>
          <ExamEditor
            key={`${data.exam.id}:${data.exam.updated_at}:${data.exam.is_start_authorized}:${data.exam.has_attempts}`}
            exam={data.exam}
            saved={resource.reload}
          />
          <section className="admin-panel">
            <h2>Publication and test-day access</h2>
            <p>
              Visibility:{" "}
              <strong>
                {data.exam.is_published ? "Published" : "Unpublished"}
              </strong>{" "}
              · Start access:{" "}
              <strong>
                {data.exam.is_start_authorized ? "Enabled" : "Paused"}
              </strong>
            </p>
            <p className="admin-muted">
              Publication shows an assigned exam to candidates. Enabling starts
              validates every paper. Pausing or unpublishing stops new subjects;
              active subject deadlines and autosave continue.
            </p>
            <div className="admin-actions">
              <button
                disabled={task.pending || data.exam.status === "ARCHIVED"}
                onClick={() => {
                  void task.run(async () => {
                    await client.publish(examId, !data.exam.is_published);
                    await resource.reload();
                  });
                }}
              >
                {data.exam.is_published ? "Unpublish exam" : "Publish exam"}
              </button>
              <button
                disabled={
                  task.pending ||
                  (!data.exam.is_start_authorized &&
                    (!data.exam.is_published ||
                      data.exam.status === "ARCHIVED"))
                }
                onClick={() => {
                  if (
                    !window.confirm(
                      data.exam.is_start_authorized
                        ? "Pause all new exam and subject starts? Active subjects continue."
                        : "Allow assigned candidates to begin within the configured schedule? Paper editing will be locked.",
                    )
                  )
                    return;
                  void task.run(async () => {
                    await client.authorize(
                      examId,
                      !data.exam.is_start_authorized,
                    );
                    await resource.reload();
                  });
                }}
              >
                {data.exam.is_start_authorized
                  ? "Pause starts"
                  : "Enable starts"}
              </button>
            </div>
          </section>
          <ResultControls
            key={`${data.exam.id}:${data.exam.result_release_at}`}
            exam={data.exam}
            saved={resource.reload}
          />
          <SubjectConfiguration
            key={data.exam.id}
            exam={data.exam}
            papers={data.papers}
            subjects={data.subjects}
            frozen={frozen}
            saved={resource.reload}
            choosePaper={setPaperId}
          />
          {paperId && data.papers.some((item) => item.id === paperId) && (
            <PaperBuilder
              key={paperId}
              paperId={paperId}
              subjectId={
                data.papers.find((item) => item.id === paperId)!.subject_id
              }
              frozen={frozen}
              saved={resource.reload}
            />
          )}
        </>
      )}
    </>
  );
}
function ResultControls({
  exam,
  saved,
}: {
  exam: AdminExam;
  saved: () => Promise<void>;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [date, setDate] = useState(localDate(exam.result_release_at));
  return (
    <section className="admin-panel">
      <h2>Result publication</h2>
      <p>
        Results:{" "}
        <strong>{exam.results_released ? "Released" : "Withheld"}</strong>
      </p>
      <p className="admin-muted">
        Grading and candidate results arrive in Milestone 8. A planned release
        date can be recorded now; it does not publish ungraded results
        automatically.
      </p>
      <TaskStatus task={task} />
      <form
        className="admin-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          void task.run(async () => {
            await client.withhold(exam.id, utcDate(date));
            await saved();
          }, "Release plan saved. Results remain withheld.");
        }}
      >
        <label>
          Planned result release (local time)
          <input
            type="datetime-local"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <button disabled={task.pending}>
          Save release plan / keep withheld
        </button>
        <button type="button" disabled>
          Release results (grading required)
        </button>
      </form>
    </section>
  );
}
function SubjectConfiguration({
  exam,
  papers,
  subjects,
  frozen,
  saved,
  choosePaper,
}: {
  exam: AdminExam;
  papers: AdminExamSubject[];
  subjects: AdminSubject[];
  frozen: boolean;
  saved: () => Promise<void>;
  choosePaper: (id: string) => void;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [editing, setEditing] = useState<AdminExamSubject | null>(null);
  const [subject, setSubject] = useState("");
  const [duration, setDuration] = useState(60);
  const [sequence, setSequence] = useState(
    Math.max(0, ...papers.map((item) => item.sequence)) + 1,
  );
  const reset = () => {
    setEditing(null);
    setSubject("");
    setDuration(60);
    setSequence(Math.max(0, ...papers.map((item) => item.sequence)) + 1);
  };
  const reorder = (index: number, delta: number) => {
    const ids = papers.map((item) => item.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void task.run(async () => {
      await client.reorderSubjects(exam.id, ids);
      await saved();
    });
  };
  return (
    <section className="admin-panel">
      <h2>Subjects, durations, and order</h2>
      <TaskStatus task={task} />
      <form
        className="admin-form"
        onSubmit={(event) => {
          event.preventDefault();
          const value: AdminExamSubjectWrite = {
            subject_id: subject,
            duration_minutes: duration,
            sequence,
          };
          void task.run(async () => {
            const result = await client.saveExamSubject(
              exam.id,
              value,
              editing?.id,
            );
            await saved();
            reset();
            setSequence(
              Math.max(
                result.sequence,
                ...papers.map((item) => item.sequence),
              ) + 1,
            );
          });
        }}
      >
        <fieldset disabled={frozen || task.pending}>
          <legend>{editing ? "Edit exam subject" : "Add exam subject"}</legend>
          <div className="admin-row">
            <label>
              Subject
              <select
                required
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              >
                <option value="">Choose subject</option>
                {subjects
                  .filter(
                    (item) => item.is_active || item.id === editing?.subject_id,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Duration (minutes)
              <input
                type="number"
                required
                min={1}
                max={1440}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
              />
            </label>
            <label>
              Sequence
              <input
                type="number"
                required
                min={1}
                max={1000}
                value={sequence}
                onChange={(event) => setSequence(Number(event.target.value))}
              />
            </label>
          </div>
          <div className="admin-actions">
            <button>{editing ? "Save exam subject" : "Add subject"}</button>
            {editing && (
              <button type="button" onClick={reset}>
                Cancel subject editing
              </button>
            )}
          </div>
        </fieldset>
      </form>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <caption>Exam papers in subject order</caption>
          <thead>
            <tr>
              <th>Order / subject</th>
              <th>Minutes</th>
              <th>Questions / marks</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {papers.map((item, index) => (
              <tr key={item.id}>
                <td>
                  {item.sequence}.{" "}
                  {subjects.find((subject) => subject.id === item.subject_id)
                    ?.name || item.subject_id}
                </td>
                <td>{item.duration_minutes}</td>
                <td>
                  {item.question_count} / {item.total_marks}
                </td>
                <td>
                  <div className="admin-actions">
                    <button onClick={() => choosePaper(item.id)}>
                      Build paper {item.sequence}
                    </button>
                    <button
                      disabled={frozen || task.pending}
                      onClick={() => {
                        setEditing(item);
                        setSubject(item.subject_id);
                        setDuration(item.duration_minutes);
                        setSequence(item.sequence);
                      }}
                    >
                      Edit paper {item.sequence}
                    </button>
                    <button
                      aria-label={`Move subject ${item.sequence} earlier`}
                      disabled={frozen || task.pending || index === 0}
                      onClick={() => reorder(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      aria-label={`Move subject ${item.sequence} later`}
                      disabled={
                        frozen || task.pending || index === papers.length - 1
                      }
                      onClick={() => reorder(index, 1)}
                    >
                      ↓
                    </button>
                    <button
                      disabled={
                        frozen || task.pending || item.question_count > 0
                      }
                      onClick={() => {
                        if (!window.confirm("Remove this empty exam subject?"))
                          return;
                        void task.run(async () => {
                          await client.removeExamSubject(exam.id, item.id);
                          await saved();
                        });
                      }}
                    >
                      Remove paper {item.sequence}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="admin-muted">
        Clear a paper’s question selection before removing its subject. Linked
        questions remain protected against editing or archival.
      </p>
    </section>
  );
}
