import { useState } from "react";
import { useAdminApi } from "../../services/admin";
import type { StaffAction } from "../../types/admin";
import { Pager, RemoteStatus, useRemote } from "./shared";

export function StaffActionsPage() {
  const client = useAdminApi();
  const [offset, setOffset] = useState(0);
  const list = useRemote(String(offset), () =>
    client.list<StaffAction>("/actions", {
      limit: "50",
      offset: String(offset),
    }),
  );
  return (
    <>
      <h1>Staff action history</h1>
      <p className="admin-muted">
        Server-recorded administrator actions. This list contains record
        identifiers and action types; it does not display candidate answers.
      </p>
      <section className="admin-panel">
        <button
          onClick={() => {
            void list.reload();
          }}
        >
          Refresh actions
        </button>
        <RemoteStatus resource={list} />
        <div className="admin-table-wrap">
          <table className="admin-table">
            <caption>Recent actions</caption>
            <thead>
              <tr>
                <th>Server time</th>
                <th>Action</th>
                <th>Record ID</th>
                <th>Staff ID</th>
              </tr>
            </thead>
            <tbody>
              {list.data?.map((item) => (
                <tr key={item.id}>
                  <td>
                    <time dateTime={item.server_timestamp}>
                      {new Date(item.server_timestamp).toLocaleString()}
                    </time>
                  </td>
                  <td>{item.event_type}</td>
                  <td>{item.entity_id}</td>
                  <td>{item.user_id}</td>
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
