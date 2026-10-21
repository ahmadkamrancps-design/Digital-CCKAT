import { useState } from "react";
import { useAdminApi } from "../../services/admin";
import type { StaffAction } from "../../types/admin";
import {
  AdminPageHeader,
  EmptyState,
  Pager,
  RemoteStatus,
  useRemote,
} from "./shared";
import { actionLabel } from "./AdminOverview";

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
      <AdminPageHeader
        title="Staff action history"
        description="Review who changed a record and when. Entries are recorded by the server and contain no candidate answers."
      />
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
                <th>Staff</th>
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
                  <td>{actionLabel(item.event_type)}</td>
                  <td>{item.entity_id}</td>
                  <td>
                    <bdi>{item.actor_name || item.user_id}</bdi>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!list.loading && !list.error && list.data?.length === 0 && (
          <EmptyState
            title="No staff actions yet"
            description="Actions will appear here after an administrator saves a change."
          />
        )}
        <Pager
          offset={offset}
          count={list.data?.length || 0}
          setOffset={setOffset}
        />
      </section>
    </>
  );
}
