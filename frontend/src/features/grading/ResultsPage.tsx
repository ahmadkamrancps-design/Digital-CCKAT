import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import CandidateSidebar from "../../components/CandidateSidebar";
import { gradingApi } from "../../services/grading";
import type { AttemptResult } from "../../types/grading";
import { useAuth } from "../auth/AuthProvider";
import { Pager, RemoteStatus, useRemote } from "../admin/shared";
import "./grading.css";

export function ResultsPage() {
  const { profile, isPreview } = useAuth();
  if (!isPreview && !profile) return <Navigate to="/" replace />;
  if (!isPreview && (profile?.user.role !== "CANDIDATE" || !profile.candidate))
    return <Navigate to="/dashboard" replace />;
  return (
    <div className="dashboard-layout">
      <CandidateSidebar />
      <main className="dashboard-content" id="main" tabIndex={-1}>
        <section className="dashboard-welcome">
          <h1>Your results</h1>
          <p>Results appear here only when released by administration.</p>
        </section>
        {isPreview ? (
          <>
            <p role="status">
              Sample result for design testing. This is not an admission result.
            </p>
            <ResultCard result={sampleResult} />
          </>
        ) : (
          <LiveResults key={profile?.user.id} />
        )}
        <p>
          <Link to="/dashboard">Return to dashboard</Link>
        </p>
      </main>
    </div>
  );
}

function LiveResults() {
  const [offset, setOffset] = useState(0);
  const resource = useRemote(`candidate-results:${offset}`, () =>
    gradingApi("").results(offset),
  );
  useEffect(() => {
    const recheck = () => {
      if (document.visibilityState === "visible") void resource.reload();
    };
    window.addEventListener("online", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      window.removeEventListener("online", recheck);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [resource.reload]);
  return (
    <>
      <button
        className="secondary-button"
        onClick={() => {
          void resource.reload();
        }}
        disabled={resource.loading}
      >
        Refresh results
      </button>
      <RemoteStatus resource={resource} />
      {!resource.error &&
        !resource.loading &&
        resource.data?.map((item) => (
          <ResultCard key={item.attempt_id} result={item} />
        ))}
      {!resource.loading && !resource.error && resource.data?.length === 0 && (
        <section className="exam-card card">
          <p>No exam results are available for this account yet.</p>
        </section>
      )}
      <Pager
        offset={offset}
        count={resource.data?.length || 0}
        setOffset={setOffset}
      />
    </>
  );
}

function ResultCard({ result }: { result: AttemptResult }) {
  const visible =
    result.publication_status === "RELEASED" &&
    result.grading_status === "COMPLETE";
  return (
    <section className="exam-card card">
      <h2>{result.exam_title}</h2>
      {visible ? (
        <>
          <p className="result-badge">Result released</p>
          <dl className="result-summary">
            <div>
              <dt>Total marks</dt>
              <dd>
                {result.marks_awarded} / {result.maximum_marks}
              </dd>
            </div>
            <div>
              <dt>Percentage</dt>
              <dd>{result.percentage}%</dd>
            </div>
          </dl>
          <table className="result-table">
            <caption>Subject marks</caption>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Marks awarded</th>
                <th>Maximum marks</th>
              </tr>
            </thead>
            <tbody>
              {result.subjects.map((item) => (
                <tr key={item.sequence}>
                  <td>
                    <bdi>{item.subject_name}</bdi>
                  </td>
                  <td>{item.marks_awarded}</td>
                  <td>{item.maximum_marks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p>
          {result.publication_status === "SCHEDULED"
            ? "Your results await the scheduled release."
            : "Your result is not available yet. Administration will release results when ready."}
        </p>
      )}
    </section>
  );
}

// Development display data only; no session, actual marks, or answer keys.
const sampleResult: AttemptResult = {
  attempt_id: "sample-result",
  exam_id: "sample-exam",
  exam_title: "CCK Entry Test · Sample result",
  grading_status: "COMPLETE",
  publication_status: "RELEASED",
  maximum_marks: "300.00",
  marks_awarded: "246.00",
  percentage: "82.00",
  subjects: [
    {
      subject_name: "English",
      sequence: 1,
      maximum_marks: "100.00",
      marks_awarded: "84.00",
      pending_answers: 0,
    },
    {
      subject_name: "Mathematics",
      sequence: 2,
      maximum_marks: "100.00",
      marks_awarded: "90.00",
      pending_answers: 0,
    },
    {
      subject_name: "Urdu",
      sequence: 3,
      maximum_marks: "100.00",
      marks_awarded: "72.00",
      pending_answers: 0,
    },
  ],
};
