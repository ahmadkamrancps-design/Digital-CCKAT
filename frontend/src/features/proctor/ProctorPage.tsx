import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import CCKLogo from "../../components/CCKLogo";
import { proctorApi } from "../../services/proctor";
import type {
  MonitoredCandidate,
  MonitoringResponse,
} from "../../types/proctor";
import { useAuth } from "../auth/AuthProvider";
import { usePoll, type PollSnapshot } from "./usePoll";
import "./proctor.css";

export function ProctorPage() {
  const { profile, isPreview } = useAuth();
  if (!profile)
    return isPreview ? (
      <main id="main" className="card session-state">
        <h1>Proctor sign-in required</h1>
        <p>
          Monitoring requires an approved proctor or administrator account.
          Candidate preview does not grant staff access.
        </p>
      </main>
    ) : (
      <Navigate to="/" replace />
    );
  if (!["ADMIN", "PROCTOR"].includes(profile.user.role))
    return <Navigate to="/dashboard" replace />;
  return <ProctorWorkspace key={profile.user.id} />;
}

function ProctorWorkspace() {
  const { profile, signOut } = useAuth();
  const [logoutError, setLogoutError] = useState("");
  const [signingOut, setSigningOut] = useState(false);
  const [exam, setExam] = useState("");
  const catalog = usePoll("monitored-exams", (signal) =>
    proctorApi.exams(signal),
  );
  const exams = catalog.snapshot?.data || [];
  return (
    <div className="proctor-layout">
      <a href="#proctor-main" className="skip-link">
        Skip to main content
      </a>
      <aside className="proctor-sidebar">
        <div className="sidebar-brand">
          <CCKLogo size={60} />
          <div>
            <strong>Cadet College</strong>
            <span>Kohat · Proctor</span>
          </div>
        </div>
        <nav aria-label="Proctor navigation">
          <Link to="/dashboard">Staff dashboard</Link>
          {profile?.user.role === "ADMIN" && (
            <Link to="/admin">Administration</Link>
          )}
          <span aria-current="page">Exam monitoring</span>
        </nav>
        <p className="sidebar-footer">
          CCK Digital Entry Test
          <br />
          Authorized monitoring
        </p>
      </aside>
      <main id="proctor-main" tabIndex={-1} className="proctor-content">
        <header className="proctor-header">
          <span>Proctor workspace</span>
          <bdi>{profile?.user.display_name}</bdi>
          <button
            disabled={signingOut}
            onClick={() => {
              setSigningOut(true);
              void signOut()
                .catch((cause) =>
                  setLogoutError(
                    cause instanceof Error
                      ? cause.message
                      : "Unable to sign out.",
                  ),
                )
                .finally(() => setSigningOut(false));
            }}
          >
            Sign out
          </button>
        </header>
        <h1>Exam monitoring</h1>
        <p className="proctor-muted">
          View assigned candidates and server-confirmed exam state. No candidate
          answers are shown.
        </p>
        {logoutError && <p role="alert">{logoutError}</p>}
        <section className="proctor-panel">
          <label>
            Exam to monitor{" "}
            <select
              value={exam}
              onChange={(event) => setExam(event.target.value)}
            >
              <option value="">Choose an assigned exam</option>
              {exams.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <button onClick={catalog.refresh}>Refresh exam list</button>
          {catalog.error && <p role="alert">{catalog.error}</p>}
          {catalog.loading && <p role="status">Loading assigned exams…</p>}
          {!catalog.loading && !catalog.error && !exams.length && (
            <p>
              No exams are assigned to your proctor account. Contact an
              administrator.
            </p>
          )}
        </section>
        {exam && exams.some((item) => item.id === exam) && (
          <Monitoring key={exam} examId={exam} />
        )}
      </main>
    </div>
  );
}

export function remainingTime(
  row: MonitoredCandidate,
  snapshot: PollSnapshot<MonitoringResponse>,
  monotonic: number,
) {
  if (!row.expires_at) return "—";
  const seconds = Math.max(
    0,
    Math.ceil(
      (Date.parse(row.expires_at) -
        Date.parse(snapshot.data.server_time) -
        (monotonic - snapshot.requestedAt)) /
        1000,
    ),
  );
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
function connectionLabel(
  row: MonitoredCandidate,
  snapshot: PollSnapshot<MonitoringResponse>,
  monotonic: number,
) {
  if (row.connection === "UNKNOWN" || !row.last_seen_at) return "Unknown";
  const age =
    Date.parse(snapshot.data.server_time) +
    (monotonic - snapshot.requestedAt) -
    Date.parse(row.last_seen_at);
  return age <= 30_000 ? "Online · recent contact" : "No recent contact";
}
function Monitoring({ examId }: { examId: string }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<{ id: string; roll: string } | null>(
    null,
  );
  const [monotonic, setMonotonic] = useState(performance.now());
  const resource = usePoll(
    `${examId}:${search}:${activeOnly}:${offset}`,
    (signal) => proctorApi.sessions(examId, offset, search, activeOnly, signal),
  );
  useEffect(() => {
    const timer = setInterval(() => setMonotonic(performance.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const snapshot = resource.snapshot;
  return (
    <>
      <section className="proctor-panel">
        <h2>Candidate sessions</h2>
        <form
          className="proctor-toolbar"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setSelected(null);
            setSearch(query);
          }}
        >
          <label>
            Search name or roll number
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <button>Search</button>
          <label>
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(event) => {
                setActiveOnly(event.target.checked);
                setSelected(null);
                setOffset(0);
              }}
            />
            Active subjects only
          </label>
          <button type="button" onClick={resource.refresh}>
            Refresh status
          </button>
        </form>
        <p className="proctor-muted">
          Refreshes every 5 seconds while connected. Position is
          candidate-reported; contact can lapse when a browser closes, sleeps,
          or loses connectivity.
        </p>
        {resource.loading && <p role="status">Loading candidate sessions…</p>}
        {resource.error && (
          <p role="alert" className="proctor-alert">
            {resource.error}
            {snapshot
              ? " Showing the last confirmed snapshot; status may be stale."
              : ""}
          </p>
        )}
        {snapshot && (
          <>
            <p>
              Last server snapshot:{" "}
              <time dateTime={snapshot.data.server_time}>
                {new Date(snapshot.data.server_time).toLocaleString()}
              </time>
            </p>
            <div className="proctor-table-wrap">
              <table className="proctor-table">
                <caption>Candidate monitoring — no answer content</caption>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Status / access</th>
                    <th>Subject / position</th>
                    <th>Time remaining</th>
                    <th>Connection</th>
                    <th>Review events</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.data.candidates.map((row) => (
                    <tr key={row.candidate_id}>
                      <td>
                        <strong>
                          <bdi>{row.roll_number}</bdi>
                        </strong>
                        <br />
                        <bdi>{row.full_name}</bdi>
                      </td>
                      <td>
                        {row.state.replaceAll("_", " ")}
                        {!row.access_active && (
                          <span className="proctor-blocked">
                            Access revoked / disabled
                          </span>
                        )}
                      </td>
                      <td>
                        <bdi>{row.subject_name || "—"}</bdi>
                        <br />
                        {row.reported_question_sequence
                          ? `Reported question ${row.reported_question_sequence} / ${row.question_count}`
                          : row.question_count
                            ? `${row.question_count} questions · position unavailable`
                            : "Not started"}
                      </td>
                      <td>{remainingTime(row, snapshot, monotonic)}</td>
                      <td>
                        {connectionLabel(row, snapshot, monotonic)}
                        {row.last_seen_at && (
                          <small>
                            Last contact:{" "}
                            {new Date(row.last_seen_at).toLocaleTimeString()}
                          </small>
                        )}
                      </td>
                      <td>
                        {row.review_event_count}{" "}
                        {row.attempt_id && (
                          <button
                            onClick={() =>
                              setSelected({
                                id: row.attempt_id!,
                                roll: row.roll_number,
                              })
                            }
                          >
                            Inspect events for {row.roll_number}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!snapshot.data.candidates.length && (
              <p>No candidates match these filters.</p>
            )}
            <nav className="proctor-pager" aria-label="Candidate pages">
              <button
                disabled={offset === 0}
                onClick={() => {
                  setSelected(null);
                  setOffset(Math.max(0, offset - 50));
                }}
              >
                Previous page
              </button>
              <span>Page {offset / 50 + 1}</span>
              <button
                disabled={snapshot.data.candidates.length < 50}
                onClick={() => {
                  setSelected(null);
                  setOffset(offset + 50);
                }}
              >
                Next page
              </button>
            </nav>
          </>
        )}
      </section>
      {selected && snapshot && (
        <EventHistory
          key={selected.id}
          attemptId={selected.id}
          roll={selected.roll}
          close={() => setSelected(null)}
        />
      )}
    </>
  );
}
function EventHistory({
  attemptId,
  roll,
  close,
}: {
  attemptId: string;
  roll: string;
  close: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const resource = usePoll(`${attemptId}:${offset}`, (signal) =>
    proctorApi.events(attemptId, offset, signal),
  );
  return (
    <section className="proctor-panel">
      <h2>
        Session events: <bdi>{roll}</bdi>
      </h2>
      <button onClick={close}>Close events</button>
      <p className="proctor-muted">
        Browser reports help human review and do not establish misconduct.
        Timestamps show server receipt; delayed reports may arrive after
        reconnection.
      </p>
      {resource.error && (
        <p role="alert">
          {resource.error}
          {resource.snapshot
            ? " Showing the last confirmed event snapshot."
            : ""}
        </p>
      )}
      {resource.loading && <p role="status">Loading events…</p>}
      {resource.snapshot && (
        <>
          <ul className="proctor-events">
            {resource.snapshot.data.map((event) => (
              <li key={event.id}>
                <strong>{event.event_type.replaceAll("_", " ")}</strong>
                <span>
                  {event.source === "CLIENT"
                    ? "Browser report"
                    : "Server event"}
                </span>
                <time dateTime={event.server_timestamp}>
                  {new Date(event.server_timestamp).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
          {!resource.snapshot.data.length && (
            <p>No recorded events for this attempt.</p>
          )}
          <nav className="proctor-pager" aria-label="Event pages">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Newer events
            </button>
            <button
              disabled={resource.snapshot.data.length < 50}
              onClick={() => setOffset(offset + 50)}
            >
              Older events
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
