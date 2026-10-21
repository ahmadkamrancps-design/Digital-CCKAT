import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  ClipboardList,
  Plus,
  RefreshCw,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAdminApi } from "../../services/admin";
import type { AdminOverview as OverviewData } from "../../types/admin";
import {
  AdminPageHeader,
  EmptyState,
  RemoteStatus,
  StatusPill,
  useRemote,
} from "./shared";

export function AdminOverviewPage() {
  const client = useAdminApi();
  const resource = useRemote("admin-overview", () => client.overview());
  return (
    <>
      <AdminPageHeader
        title="Administration overview"
        description="A clear view of your admissions, exam preparation, and recent staff activity."
        actions={
          <button
            disabled={resource.loading}
            onClick={() => {
              void resource.reload();
            }}
          >
            <RefreshCw size={16} aria-hidden="true" /> Refresh overview
          </button>
        }
      />
      <RemoteStatus resource={resource} />
      {!resource.error && resource.data && (
        <div aria-busy={resource.loading}>
          <AdminOverviewContent data={resource.data} />
        </div>
      )}
    </>
  );
}

export function actionLabel(value: string): string {
  const words = value.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function AdminOverviewContent({
  data,
  preview = false,
}: {
  data: OverviewData;
  preview?: boolean;
}) {
  const base = preview ? "/preview/admin" : "/admin";
  const stats = [
    {
      label: "Registered candidates",
      value: data.candidate_count,
      detail: `${data.approved_candidates.toLocaleString()} approved`,
      icon: Users,
      path: "candidates",
      tone: "blue",
    },
    {
      label: "Configured exams",
      value: data.exam_count,
      detail: `${data.published_exams.toLocaleString()} published`,
      icon: CalendarDays,
      path: "exams",
      tone: "gold",
    },
    {
      label: "Question bank",
      value: data.question_count,
      detail: `${data.active_questions.toLocaleString()} active questions`,
      icon: ClipboardList,
      path: "questions",
      tone: "green",
    },
    {
      label: "Subjects",
      value: data.subject_count,
      detail: `${data.active_subjects.toLocaleString()} active subjects`,
      icon: BookOpen,
      path: "subjects",
      tone: "violet",
    },
  ];
  return (
    <>
      <section className="admin-stats" aria-label="Administration totals">
        {stats.map(({ label, value, detail, icon: Icon, path, tone }) => (
          <Link
            className="admin-stat"
            to={`${base}/${path}`}
            key={path}
            aria-label={`${label}: ${value.toLocaleString()}. ${detail}.`}
          >
            <div className="admin-stat-top">
              <span>{label}</span>
              <span className={`admin-stat-icon admin-icon-${tone}`}>
                <Icon size={21} aria-hidden="true" />
              </span>
            </div>
            <strong>{value.toLocaleString()}</strong>
            <span className="admin-stat-detail">
              {detail}
              <ArrowRight size={15} aria-hidden="true" />
            </span>
          </Link>
        ))}
      </section>
      <div className="admin-overview-grid">
        <section
          className="admin-panel admin-recent-exams"
          aria-labelledby="recent-exams-heading"
        >
          <div className="admin-section-heading">
            <div>
              <h2 id="recent-exams-heading">Recent exams</h2>
              <p>Pick an exam to continue preparation.</p>
            </div>
            <Link to={`${base}/exams`}>
              View all <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          {data.recent_exams.length ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <caption className="sr-only">
                  Five most recently updated exams
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Exam</th>
                    <th scope="col">Status</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_exams.map((exam) => (
                    <tr key={exam.id}>
                      <th scope="row">
                        <strong>{exam.title}</strong>
                        <small>
                          {exam.scheduled_start
                            ? new Date(exam.scheduled_start).toLocaleString()
                            : "Schedule to be confirmed"}
                        </small>
                      </th>
                      <td>
                        <StatusPill
                          tone={
                            exam.status === "ARCHIVED"
                              ? "neutral"
                              : exam.is_start_authorized && exam.is_published
                                ? "success"
                                : "warning"
                          }
                        >
                          {exam.status === "ARCHIVED"
                            ? "Archived"
                            : exam.is_start_authorized && exam.is_published
                              ? "Starts enabled"
                              : exam.is_published
                                ? "Published · Starts paused"
                                : "Unpublished"}
                        </StatusPill>
                      </td>
                      <td>
                        <Link
                          className="admin-link"
                          to={
                            preview
                              ? `${base}/exams`
                              : `${base}/exams/${exam.id}`
                          }
                          aria-label={`Manage ${exam.title}`}
                        >
                          Manage <ArrowRight size={14} aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="Your first exam starts here"
              description="Create an exam, add its subjects, and build the papers before publishing it."
            />
          )}
        </section>
        <section
          className="admin-panel admin-quick-actions"
          aria-labelledby="quick-actions-heading"
        >
          <div className="admin-section-heading">
            <div>
              <h2 id="quick-actions-heading">Quick actions</h2>
              <p>Your most-used tasks, one click away.</p>
            </div>
          </div>
          {[
            {
              title: "Manage candidates",
              text: "Register, import and assign admissions records.",
              path: "candidates",
              icon: Users,
            },
            {
              title: preview ? "Explore exam setup" : "Create an exam",
              text: "Set up a test and build its subject papers.",
              path: preview ? "exams" : "exams/new",
              icon: Plus,
            },
            {
              title: "Open question bank",
              text: "Organize MCQs and short-answer questions.",
              path: "questions",
              icon: ClipboardList,
            },
          ].map(({ title, text, path, icon: Icon }) => (
            <Link
              key={path}
              className="admin-quick-link"
              to={`${base}/${path}`}
              aria-label={title}
              aria-describedby={`admin-quick-description-${path.replaceAll("/", "-")}`}
            >
              <span className="admin-quick-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <span>
                <strong>{title}</strong>
                <small
                  id={`admin-quick-description-${path.replaceAll("/", "-")}`}
                >
                  {text}
                </small>
              </span>
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
          ))}
        </section>
      </div>
      <section className="admin-panel" aria-labelledby="preparation-heading">
        <div className="admin-section-heading">
          <div>
            <h2 id="preparation-heading">Prepare an entry test</h2>
            <p>
              Follow these steps for each new exam. Publishing and enabling
              starts are separate actions.
            </p>
          </div>
          <BookOpen size={23} aria-hidden="true" />
        </div>
        <ol className="admin-preparation-steps">
          {[
            [
              "Set up subjects",
              "Create the subject catalog for your papers.",
              "subjects",
            ],
            [
              "Add questions",
              "Write questions and review their marking rules.",
              "questions",
            ],
            [
              "Build the exam",
              "Choose questions, order, duration and schedule.",
              "exams",
            ],
            [
              "Assign candidates",
              "Check admission details and assign the exam.",
              "candidates",
            ],
          ].map(([title, description, path], index) => (
            <li key={path}>
              <span>{index + 1}</span>
              <div>
                <Link to={`${base}/${path}`}>{title}</Link>
                <p>{description}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      <div className="admin-overview-grid">
        <section
          className="admin-panel"
          aria-labelledby="recent-activity-heading"
        >
          <div className="admin-section-heading">
            <div>
              <h2 id="recent-activity-heading">Recent staff activity</h2>
              <p>Recorded actions from your administration team.</p>
            </div>
            <Link to={`${base}/actions`}>
              View history <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          {data.recent_actions.length ? (
            <ul className="admin-activity-list">
              {data.recent_actions.map((action) => (
                <li key={action.id}>
                  <span className="admin-activity-dot" aria-hidden="true" />
                  <div>
                    <strong>{actionLabel(action.event_type)}</strong>
                    <span>
                      <bdi>{action.actor_name}</bdi> ·{" "}
                      <time dateTime={action.server_timestamp}>
                        {new Date(action.server_timestamp).toLocaleString()}
                      </time>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No staff activity yet"
              description="Saved administrative actions will appear here."
            />
          )}
        </section>
        <section
          className="admin-panel admin-test-day"
          aria-labelledby="test-day-heading"
        >
          <span className="admin-eyebrow">When preparation is complete</span>
          <h2 id="test-day-heading">Your test-day workspace</h2>
          <p>
            Monitor sessions in the proctor dashboard. Review manual responses
            in grading, then release results from the exam workspace.
          </p>
          {preview ? (
            <p className="admin-muted">
              Monitoring and grading require an authorized staff session.
            </p>
          ) : (
            <div className="admin-actions">
              <Link className="admin-link" to="/proctor">
                Open monitoring <ArrowRight size={14} aria-hidden="true" />
              </Link>
              <Link className="admin-link" to="/grading">
                Open grading <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
