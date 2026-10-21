import { useState } from "react";
import { useAdminApi } from "../../services/admin";
import type { AdminSubject, AdminSubjectWrite } from "../../types/admin";
import {
  AdminPageHeader,
  EmptyState,
  Pager,
  RemoteStatus,
  StatusPill,
  TaskStatus,
  useRemote,
  useTask,
} from "./shared";

export function SubjectsPage() {
  const client = useAdminApi();
  const task = useTask();
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<AdminSubject | null>(null);
  const [value, setValue] = useState<AdminSubjectWrite>({
    name: "",
    code: "",
    is_active: true,
  });
  const list = useRemote(String(offset), () =>
    client.list<AdminSubject>("/subjects", {
      limit: "50",
      offset: String(offset),
    }),
  );
  return (
    <>
      <AdminPageHeader
        title="Subject catalog"
        description="Set up the subjects used in your question bank. Choose each subject’s duration and order separately when building an exam."
      />
      <TaskStatus task={task} />
      <div className="admin-catalog-layout">
        <section className="admin-panel">
          <h2>{editing ? "Edit subject" : "Create subject"}</h2>
          <form
            className="admin-form"
            onSubmit={(event) => {
              event.preventDefault();
              void task.run(async () => {
                await client.subject(value, editing?.id);
                setEditing(null);
                setValue({ name: "", code: "", is_active: true });
                await list.reload();
              });
            }}
          >
            <fieldset disabled={task.pending}>
              <legend>Subject details</legend>
              <label>
                Subject name
                <input
                  required
                  maxLength={100}
                  value={value.name}
                  dir="auto"
                  onChange={(event) =>
                    setValue({ ...value, name: event.target.value })
                  }
                />
              </label>
              <label>
                Subject code
                <input
                  required
                  maxLength={32}
                  pattern="[A-Za-z0-9_-]+"
                  value={value.code}
                  onChange={(event) =>
                    setValue({ ...value, code: event.target.value })
                  }
                />
              </label>
              <label className="admin-check">
                <input
                  type="checkbox"
                  checked={value.is_active}
                  onChange={(event) =>
                    setValue({ ...value, is_active: event.target.checked })
                  }
                />
                Active subject
              </label>
              <div className="admin-actions">
                <button className="primary-button">Save subject</button>
                {editing && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(null);
                      setValue({ name: "", code: "", is_active: true });
                    }}
                  >
                    Cancel editing
                  </button>
                )}
              </div>
            </fieldset>
          </form>
        </section>
        <section className="admin-panel">
          <RemoteStatus resource={list} />
          <div className="admin-table-wrap">
            <table className="admin-table">
              <caption>Configured subjects</caption>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {list.data?.map((item) => (
                  <tr key={item.id}>
                    <td>{item.code}</td>
                    <td>
                      <bdi>{item.name}</bdi>
                    </td>
                    <td>
                      <StatusPill tone={item.is_active ? "success" : "neutral"}>
                        {item.is_active ? "Active" : "Inactive"}
                      </StatusPill>
                    </td>
                    <td>
                      <button
                        disabled={task.pending}
                        onClick={() => {
                          setEditing(item);
                          setValue({
                            name: item.name,
                            code: item.code,
                            is_active: item.is_active,
                          });
                        }}
                      >
                        Edit {item.code}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!list.loading && !list.error && list.data?.length === 0 && (
            <EmptyState
              title="Create your first subject"
              description="Use the form to add a name and a short, unique subject code."
            />
          )}
          <Pager
            offset={offset}
            count={list.data?.length || 0}
            setOffset={setOffset}
          />
        </section>
      </div>
    </>
  );
}
