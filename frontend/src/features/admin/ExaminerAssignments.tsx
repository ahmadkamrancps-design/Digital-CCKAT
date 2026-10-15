import { useState } from "react";
import { Link } from "react-router-dom";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type { ExaminerAssignment, ExaminerStaff } from "../../types/grading";
import { RemoteStatus, TaskStatus, useRemote, useTask } from "./shared";

export function ExaminerAssignments({ examId }: { examId: string }) {
  const client = useAdminApi();
  const task = useTask();
  const [userId, setUserId] = useState("");
  const resource = useRemote(`examiners:${examId}`, async () => {
    const [staff, assignments] = await Promise.all([
      allAdminRows<ExaminerStaff>(client, "/examiners"),
      client.list<ExaminerAssignment>(`/exams/${examId}/examiners`),
    ]);
    return { staff, assignments };
  });
  return (
    <section className="admin-panel">
      <h2>Examiner access</h2>
      <p>Assign approved examiners to review manual responses for this exam.</p>
      <RemoteStatus resource={resource} />
      <TaskStatus task={task} />
      {!resource.error && resource.data && (
        <>
          <form
            className="admin-toolbar"
            onSubmit={(event) => {
              event.preventDefault();
              void task.run(async () => {
                await client.assignExaminer(examId, userId, true);
                await resource.reload();
                setUserId("");
              });
            }}
          >
            <label>
              Examiner to assign{" "}
              <select
                value={userId}
                required
                onChange={(event) => setUserId(event.target.value)}
              >
                <option value="">Choose examiner</option>
                {resource.data.staff.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={task.pending || !userId}>Assign examiner</button>
          </form>
          {!resource.data.staff.length && (
            <p>
              No active examiner accounts. An operator can provision approved
              staff using the registration CLI.
            </p>
          )}
          <ul>
            {resource.data.assignments.map((item) => (
              <li key={item.user_id}>
                <bdi>{item.display_name}</bdi> ·{" "}
                {item.is_active ? "Assigned" : "Revoked"}{" "}
                <button
                  disabled={task.pending}
                  onClick={() => {
                    if (
                      !window.confirm(
                        item.is_active
                          ? "Revoke this examiner’s access to this exam?"
                          : "Restore this examiner’s access?",
                      )
                    )
                      return;
                    void task.run(async () => {
                      await client.assignExaminer(
                        examId,
                        item.user_id,
                        !item.is_active,
                      );
                      await resource.reload();
                    });
                  }}
                >
                  {item.is_active ? "Revoke examiner" : "Restore examiner"}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <p>
        <Link to="/grading">Open grading workspace</Link>
      </p>
    </section>
  );
}
