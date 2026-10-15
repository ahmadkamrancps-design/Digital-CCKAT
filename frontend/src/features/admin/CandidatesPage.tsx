import { useState } from "react";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type {
  AdminCandidate,
  AdminCandidateWrite,
  AdminExam,
} from "../../types/admin";
import { candidateCsv } from "./candidateCsv";
import { Pager, RemoteStatus, TaskStatus, useRemote, useTask } from "./shared";

export function CandidatesPage() {
  const client = useAdminApi();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [exam, setExam] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<AdminCandidate | "new" | null>(null);
  const [assigned, setAssigned] = useState<AdminCandidate | null>(null);
  const [importing, setImporting] = useState(false);
  const panelOpen = editing !== null || assigned !== null || importing;
  const exams = useRemote("candidate-exams", () =>
    allAdminRows<AdminExam>(client, "/exams"),
  );
  const list = useRemote(`${search}:${status}:${exam}:${offset}`, () =>
    client.list<AdminCandidate>("/candidates", {
      search,
      ...(status ? { status } : {}),
      ...(exam ? { exam_id: exam } : {}),
      offset: String(offset),
      limit: "50",
    }),
  );
  return (
    <>
      <h1>Candidate management</h1>
      <p className="admin-muted">
        Manage approved identities and exam assignments. Disabling a candidate
        blocks further authenticated access.
      </p>
      <div className="admin-actions">
        <button
          className="primary-button"
          disabled={panelOpen}
          onClick={() => {
            setEditing("new");
            setAssigned(null);
            setImporting(false);
          }}
        >
          Create candidate
        </button>
        <button
          disabled={panelOpen}
          onClick={() => {
            setImporting(true);
            setEditing(null);
            setAssigned(null);
          }}
        >
          Import CSV
        </button>
      </div>
      {editing && (
        <CandidateEditor
          key={editing === "new" ? "new" : editing.id}
          candidate={editing === "new" ? null : editing}
          close={() => setEditing(null)}
          saved={list.reload}
        />
      )}
      {importing && (
        <CandidateImporter
          close={() => setImporting(false)}
          saved={list.reload}
        />
      )}
      {assigned && (
        <Assignments
          key={assigned.id}
          candidate={assigned}
          exams={exams.data || []}
          close={() => setAssigned(null)}
        />
      )}
      <section className="admin-panel">
        <form
          className="admin-toolbar"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setSearch(query);
          }}
        >
          <label>
            Search candidates{" "}
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Name, roll number, or email"
            />
          </label>
          <button>Search</button>
          <label>
            Status{" "}
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              <option>APPROVED</option>
              <option>DISABLED</option>
            </select>
          </label>
          <label>
            Assigned exam{" "}
            <select
              value={exam}
              onChange={(event) => {
                setExam(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All candidates</option>
              {exams.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        </form>
        <RemoteStatus resource={exams} />
        <RemoteStatus resource={list} />
        {list.data && (
          <>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <caption>Candidate records</caption>
                <thead>
                  <tr>
                    <th>Roll number</th>
                    <th>Name</th>
                    <th>Authorized email</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <bdi>{item.roll_number}</bdi>
                      </td>
                      <td>
                        <bdi>{item.full_name}</bdi>
                      </td>
                      <td>
                        <bdi>{item.email}</bdi>
                      </td>
                      <td>{item.status}</td>
                      <td>
                        <div className="admin-actions">
                          <button
                            disabled={panelOpen}
                            onClick={() => {
                              setEditing(item);
                              setAssigned(null);
                              setImporting(false);
                            }}
                          >
                            Edit {item.roll_number}
                          </button>
                          <button
                            disabled={panelOpen}
                            onClick={() => {
                              setAssigned(item);
                              setEditing(null);
                              setImporting(false);
                            }}
                          >
                            Assign {item.roll_number}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!list.data.length && <p>No candidates match these filters.</p>}
            <Pager
              offset={offset}
              count={list.data.length}
              setOffset={setOffset}
            />
          </>
        )}
      </section>
    </>
  );
}
function CandidateEditor({
  candidate,
  close,
  saved,
}: {
  candidate: AdminCandidate | null;
  close: () => void;
  saved: () => Promise<void>;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [value, setValue] = useState<AdminCandidateWrite>(
    candidate || {
      email: "",
      full_name: "",
      father_name: "",
      roll_number: "",
      google_subject: null,
      status: "APPROVED",
    },
  );
  const patch = (change: Partial<AdminCandidateWrite>) =>
    setValue((previous) => ({ ...previous, ...change }));
  return (
    <section className="admin-panel">
      <h2>{candidate ? "Edit candidate" : "Create candidate"}</h2>
      <TaskStatus task={task} />
      <form
        className="admin-form"
        onSubmit={(event) => {
          event.preventDefault();
          const accessChanged =
            candidate &&
            (candidate.email !== value.email ||
              candidate.google_subject !== value.google_subject ||
              candidate.status !== value.status ||
              candidate.roll_number !== value.roll_number ||
              candidate.full_name !== value.full_name ||
              candidate.father_name !== value.father_name);
          if (
            accessChanged &&
            !window.confirm(
              "This changes the candidate’s authorized identity or eligibility and ends their current login session. Save this change?",
            )
          )
            return;
          void task.run(async () => {
            await client.candidate(
              {
                email: value.email || null,
                full_name: value.full_name,
                father_name: value.father_name || null,
                roll_number: value.roll_number,
                google_subject: value.google_subject,
                status: value.status,
              },
              candidate?.id,
            );
            await saved();
            close();
          });
        }}
      >
        <fieldset disabled={task.pending}>
          <legend>Candidate registration</legend>
          <label>
            Full name
            <input
              required
              maxLength={200}
              value={value.full_name}
              dir="auto"
              onChange={(event) => patch({ full_name: event.target.value })}
            />
          </label>
          <label>
            Father’s name
            <input
              required={!candidate}
              maxLength={200}
              value={value.father_name || ""}
              dir="auto"
              onChange={(event) => patch({ father_name: event.target.value })}
            />
          </label>
          <label>
            Roll number
            <input
              required
              maxLength={64}
              value={value.roll_number}
              onChange={(event) => patch({ roll_number: event.target.value })}
            />
          </label>
          <p className="admin-muted">Use the roll number and names from the official admission record. This system does not issue admission roll numbers.</p>
          <label>
            Authorized email
            <input
              type="email"
              maxLength={254}
              value={value.email || ""}
              onChange={(event) => patch({ email: event.target.value })}
            />
          </label>
          <label>
            Verified Google subject (optional)
            <input
              maxLength={255}
              value={value.google_subject || ""}
              onChange={(event) =>
                patch({ google_subject: event.target.value || null })
              }
            />
          </label>
          <p className="admin-muted">
            Email and Google identity are optional for candidate roll-number login.
            Enter a subject identifier only after independent verification.
            Gmail/verified Workspace identities can bind to the approved email
            on first sign-in.
          </p>
          <label>
            Candidate status
            <select
              value={value.status}
              onChange={(event) =>
                patch({
                  status: event.target.value as AdminCandidateWrite["status"],
                })
              }
            >
              <option>APPROVED</option>
              <option>DISABLED</option>
            </select>
          </label>
          <div className="admin-actions">
            <button className="primary-button">
              {task.pending ? "Saving…" : "Save candidate"}
            </button>
            <button type="button" onClick={close}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
function CandidateImporter({
  close,
  saved,
}: {
  close: () => void;
  saved: () => Promise<void>;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [text, setText] = useState("");
  const [rows, setRows] = useState<AdminCandidateWrite[] | null>(null);
  const [error, setError] = useState("");
  const parse = () => {
    try {
      setRows(candidateCsv(text));
      setError("");
    } catch (cause) {
      setRows(null);
      setError(cause instanceof Error ? cause.message : "Invalid CSV.");
    }
  };
  return (
    <section className="admin-panel">
      <h2>Import candidates</h2>
      <p className="admin-muted">
        Required headers: roll_number,full_name,father_name. Optional:
        email,google_subject,status. Blank status means APPROVED. Maximum 500 rows;
        any rejected row prevents the entire import.
        Legacy email-based files are supported; records without a father’s name cannot use candidate sign-in.
      </p>
      <TaskStatus task={task} />
      {error && (
        <p role="alert" className="admin-alert">
          {error}
        </p>
      )}
      <form
        className="admin-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (rows)
            void task.run(async () => {
              await client.importCandidates(rows);
              await saved();
              setRows(null);
              setText("");
            }, `${rows.length} candidates imported.`);
        }}
      >
        <fieldset disabled={task.pending}>
          <legend>CSV input and review</legend>
          <label>
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                setRows(null);
                if (file.size > 1_000_000) {
                  setError("CSV is too large.");
                  return;
                }
                void file
                  .text()
                  .then((content) => {
                    setText(content);
                    setError("");
                  })
                  .catch(() => setError("Unable to read the CSV file."));
              }}
            />
          </label>
          <label>
            CSV content
            <textarea
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setRows(null);
              }}
              placeholder={
                "roll_number,full_name,father_name\nCCK-104,Test Candidate,Test Father"
              }
            />
          </label>
          <button type="button" onClick={parse}>
            Review import
          </button>
          {rows && (
            <>
              <p>
                {rows.length} candidate records ready for import. Review the
                first 10 below.
              </p>
              <ul>
                {rows.slice(0, 10).map((item) => (
                  <li key={item.roll_number}>
                    <bdi>{item.full_name}</bdi> · <bdi>{item.father_name || "Father’s name missing"}</bdi> · <bdi>{item.roll_number}</bdi>{" "}
                    · {item.status}
                  </li>
                ))}
              </ul>
              <button className="primary-button">
                Import {rows.length} candidates
              </button>
            </>
          )}
          <button type="button" onClick={close}>
            Close import
          </button>
        </fieldset>
      </form>
    </section>
  );
}
function Assignments({
  candidate,
  exams,
  close,
}: {
  candidate: AdminCandidate;
  exams: AdminExam[];
  close: () => void;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [exam, setExam] = useState("");
  const assignments = useRemote(candidate.id, () =>
    client.assignments(candidate.id),
  );
  return (
    <section className="admin-panel">
      <h2>
        Exam assignments: <bdi>{candidate.roll_number}</bdi>
      </h2>
      <TaskStatus task={task} />
      <RemoteStatus resource={assignments} />
      <form
        className="admin-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          if (exam)
            void task.run(async () => {
              await client.assign(exam, candidate.id, true);
              await assignments.reload();
            });
        }}
      >
        <label>
          Exam to assign
          <select
            required
            value={exam}
            onChange={(event) => setExam(event.target.value)}
          >
            <option value="">Choose exam</option>
            {exams
              .filter((item) => item.status !== "ARCHIVED")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
          </select>
        </label>
        <button disabled={task.pending || candidate.status !== "APPROVED"}>
          Assign exam
        </button>
        <button type="button" disabled={task.pending} onClick={close}>
          Close assignments
        </button>
      </form>
      <ul>
        {assignments.data?.map((item) => (
          <li key={item.id}>
            {exams.find((exam) => exam.id === item.exam_id)?.title ||
              item.exam_id}{" "}
            · {item.is_active ? "Assigned" : "Revoked"}{" "}
            <button
              disabled={task.pending}
              onClick={() => {
                if (
                  item.is_active &&
                  !window.confirm(
                    "Revoke this candidate’s exam access? Existing deadlines continue.",
                  )
                )
                  return;
                void task.run(async () => {
                  await client.assign(
                    item.exam_id,
                    candidate.id,
                    !item.is_active,
                  );
                  await assignments.reload();
                });
              }}
            >
              {item.is_active ? "Revoke assignment" : "Restore assignment"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
