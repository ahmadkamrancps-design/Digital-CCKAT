import { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { AdminOverview } from "../../types/admin";
import { AdminShell } from "./AdminShell";
import { actionLabel, AdminOverviewContent } from "./AdminOverview";
import { AdminPageHeader, EmptyState, StatusPill } from "./shared";

/** Synthetic display fixtures only. No session credentials, answer keys or API client. */
const sampleOverview: AdminOverview = {
  candidate_count: 6,
  approved_candidates: 5,
  exam_count: 2,
  published_exams: 1,
  question_count: 3,
  active_questions: 3,
  subject_count: 3,
  active_subjects: 3,
  recent_exams: [
    {
      id: "sample-entry",
      title: "Sample Class 8 Entry Test",
      status: "DRAFT",
      is_published: true,
      is_start_authorized: false,
      results_released: false,
      scheduled_start: null,
    },
    {
      id: "sample-practice",
      title: "Sample Practice Examination",
      status: "DRAFT",
      is_published: false,
      is_start_authorized: false,
      results_released: false,
      scheduled_start: null,
    },
  ],
  recent_actions: [
    {
      id: "sample-action-1",
      actor_name: "Sample administrator",
      event_type: "EXAM_PUBLISHED",
      server_timestamp: "2026-10-20T09:30:00Z",
    },
    {
      id: "sample-action-2",
      actor_name: "Sample administrator",
      event_type: "CANDIDATE_CREATED",
      server_timestamp: "2026-10-20T09:15:00Z",
    },
    {
      id: "sample-action-3",
      actor_name: "Sample administrator",
      event_type: "QUESTION_CREATED",
      server_timestamp: "2026-10-20T09:00:00Z",
    },
  ],
};
const sampleCandidates = Array.from({ length: 6 }, (_, index) => ({
  roll: `CCK-DEMO-00${index + 1}`,
  name:
    index === 2
      ? "نمونہ امیدوار"
      : `Sample Candidate ${String(index + 1).padStart(2, "0")}`,
  father: `Sample Father ${String(index + 1).padStart(2, "0")}`,
  approved: index !== 5,
}));
const sampleSubjects = [
  {
    name: "English",
    code: "ENG",
    prompt: "Choose the correctly spelled word.",
    type: "MCQ",
    direction: "ltr",
  },
  {
    name: "Mathematics",
    code: "MATH",
    prompt: "Find the value of x: 3(x + 5) = 24.",
    type: "Short answer",
    direction: "ltr",
  },
  {
    name: "Urdu",
    code: "UR",
    prompt: "درست جواب منتخب کریں۔",
    type: "MCQ",
    direction: "rtl",
  },
] as const;

export function AdminPreviewPage() {
  const { section = "" } = useParams();
  if (
    !["", "candidates", "exams", "subjects", "questions", "actions"].includes(
      section,
    )
  )
    return <Navigate to="/preview/admin" replace />;
  return (
    <AdminShell
      name="CCK preview"
      preview
      actions={
        <Link className="admin-link" to="/">
          Exit preview
        </Link>
      }
    >
      {section === "" ? (
        <>
          <AdminPageHeader
            title="Administration overview"
            description="Explore your CCK administration workspace with sample records."
          />
          <AdminOverviewContent data={sampleOverview} preview />
        </>
      ) : section === "candidates" ? (
        <PreviewCandidates />
      ) : section === "exams" ? (
        <PreviewExams />
      ) : section === "subjects" ? (
        <>
          <AdminPageHeader
            title="Subject catalog"
            description="Create a flexible subject catalog, then choose durations and order for each exam."
          />
          <section className="admin-panel">
            <table className="admin-table">
              <caption>Sample subjects · View only</caption>
              <thead>
                <tr>
                  <th scope="col">Subject</th>
                  <th scope="col">Code</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {sampleSubjects.map((subject) => (
                  <tr key={subject.code}>
                    <th scope="row">{subject.name}</th>
                    <td>{subject.code}</td>
                    <td>
                      <StatusPill tone="success">Active</StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : section === "questions" ? (
        <>
          <AdminPageHeader
            title="Question bank"
            description="Organize multiple-choice and short-answer questions by subject. These prompts are synthetic examples."
          />
          <section className="admin-panel">
            <ul className="admin-bank-list">
              {sampleSubjects.map((subject) => (
                <li key={subject.code}>
                  <div className="admin-row">
                    <span className="admin-badge">{subject.type}</span>
                    <span className="admin-muted">{subject.name} · 1 mark</span>
                    <StatusPill tone="success">Active</StatusPill>
                  </div>
                  <p
                    dir={subject.direction}
                    lang={subject.code === "UR" ? "ur" : "en"}
                  >
                    {subject.prompt}
                  </p>
                  <p className="admin-muted">
                    Question editing and marking rules are available in the
                    authenticated portal.
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : (
        <>
          <AdminPageHeader
            title="Staff action history"
            description="Review recorded staff activity. Sample entries below contain no candidate answers."
          />
          <section className="admin-panel">
            <ul className="admin-activity-list">
              {sampleOverview.recent_actions.map((action) => (
                <li key={action.id}>
                  <span className="admin-activity-dot" aria-hidden="true" />
                  <div>
                    <strong>{actionLabel(action.event_type)}</strong>
                    <span>
                      {action.actor_name} ·{" "}
                      <time dateTime={action.server_timestamp}>
                        {new Date(action.server_timestamp).toLocaleString()}
                      </time>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </AdminShell>
  );
}

function PreviewCandidates() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const candidates = sampleCandidates.filter(
    (candidate) =>
      `${candidate.roll} ${candidate.name} ${candidate.father}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!status || candidate.approved === (status === "approved")),
  );
  return (
    <>
      <AdminPageHeader
        title="Candidate management"
        description="Register official admission details, then assign candidates to the correct exam."
        actions={
          <button disabled aria-describedby="admin-preview-message">
            Create candidate · View only
          </button>
        }
      />
      <section className="admin-panel">
        <div className="admin-toolbar">
          <label>
            Search candidates
            <input
              value={search}
              placeholder="Name, roll number, or father’s name"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="approved">Approved</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <caption>
              Sample candidate records · {candidates.length} shown
            </caption>
            <thead>
              <tr>
                <th scope="col">Roll number</th>
                <th scope="col">Candidate</th>
                <th scope="col">Father’s name</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr key={candidate.roll}>
                  <th scope="row">{candidate.roll}</th>
                  <td>
                    <bdi>{candidate.name}</bdi>
                  </td>
                  <td>{candidate.father}</td>
                  <td>
                    <StatusPill
                      tone={candidate.approved ? "success" : "neutral"}
                    >
                      {candidate.approved ? "Approved" : "Disabled"}
                    </StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!candidates.length && (
          <EmptyState
            title="No matching candidates"
            description="Try another name or roll number, or change the status filter."
          />
        )}
      </section>
    </>
  );
}

function PreviewExams() {
  return (
    <>
      <AdminPageHeader
        title="Exam management"
        description="Keep exam preparation, publication, start access and result release in one workspace."
        actions={
          <button disabled aria-describedby="admin-preview-message">
            Create exam · View only
          </button>
        }
      />
      {sampleOverview.recent_exams.map((exam) => (
        <section key={exam.id} className="admin-panel">
          <div className="admin-section-heading">
            <div>
              <h2>{exam.title}</h2>
              <p>Class 8 · Sample configuration</p>
            </div>
            <StatusPill tone={exam.is_published ? "success" : "warning"}>
              {exam.is_published ? "Published" : "Unpublished"}
            </StatusPill>
          </div>
          <div className="admin-preview-exam-meta">
            <span>
              Start access <strong>Paused</strong>
            </span>
            <span>
              Schedule <strong>Not scheduled</strong>
            </span>
            <span>
              Results <strong>Withheld</strong>
            </span>
          </div>
          <h3>Subjects and papers</h3>
          <div className="admin-preview-subjects">
            {sampleSubjects.map((subject, index) => (
              <div key={subject.code}>
                <span>{index + 1}</span>
                <strong>{subject.name}</strong>
                <small>60 minutes · Sample paper</small>
              </div>
            ))}
          </div>
          <p className="admin-muted">
            In the live portal, configure subjects and papers, assign staff,
            publish the exam, and enable starts when authorized.
          </p>
        </section>
      ))}
    </>
  );
}
