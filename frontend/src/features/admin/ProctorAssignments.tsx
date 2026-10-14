import { useState } from "react";
import { Link } from "react-router-dom";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type { ProctorStaff } from "../../types/proctor";
import { RemoteStatus, TaskStatus, useRemote, useTask } from "./shared";

export function ProctorAssignments({ examId }: { examId: string }) {
  const client = useAdminApi();
  const task = useTask();
  const [userId, setUserId] = useState("");
  const resource = useRemote(examId, async () => {
    const [staff, assignments] = await Promise.all([
      allAdminRows<ProctorStaff>(client, "/proctors"),
      client.proctorAssignments(examId),
    ]);
    return { staff, assignments };
  });
  return (
    <section className="admin-panel">
      <h2>Proctor access</h2>
      <p className="admin-muted">
        Assign approved proctor accounts to this exam. Proctors can monitor
        status and events; exam controls remain with administrators.
      </p>
      <RemoteStatus resource={resource} />
      <TaskStatus task={task} />
      {resource.data && (
        <>
          <form
            className="admin-toolbar"
            onSubmit={(event) => {
              event.preventDefault();
              if (userId)
                void task.run(async () => {
                  await client.assignProctor(examId, userId, true);
                  await resource.reload();
                  setUserId("");
                });
            }}
          >
            <label>
              Proctor to assign
              <select
                required
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              >
                <option value="">Choose proctor</option>
                {resource.data.staff.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={task.pending}>Assign proctor</button>
          </form>
          {!resource.data.staff.length && (
            <p>
              No active proctor accounts. An operator must provision approved
              staff using the registration CLI.
            </p>
          )}
          <ul>
            {resource.data.assignments.map((assignment) => (
              <li key={assignment.user_id}>
                <bdi>{assignment.display_name}</bdi> ·{" "}
                {assignment.is_active ? "Assigned" : "Revoked"}
                {!assignment.user_is_active && " · Account disabled"}{" "}
                <button
                  disabled={
                    task.pending ||
                    (!assignment.is_active && !assignment.user_is_active)
                  }
                  onClick={() => {
                    if (
                      !window.confirm(
                        assignment.is_active
                          ? "Revoke this proctor’s access to this exam?"
                          : "Restore this proctor’s monitoring access?",
                      )
                    )
                      return;
                    void task.run(async () => {
                      await client.assignProctor(
                        examId,
                        assignment.user_id,
                        !assignment.is_active,
                      );
                      await resource.reload();
                    });
                  }}
                >
                  {assignment.is_active ? "Revoke proctor" : "Restore proctor"}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <p>
        <Link to="/proctor">Open proctor monitoring</Link>
      </p>
    </section>
  );
}
