import { useCallback, useEffect, useRef, useState } from "react";

export function useRemote<T>(key: string, load: () => Promise<T>) {
  const loader = useRef(load);
  loader.current = load;
  const version = useRef(0);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    const current = ++version.current;
    setLoading(true);
    setError("");
    try {
      const value = await loader.current();
      if (current === version.current) setData(value);
    } catch (cause) {
      if (current === version.current)
        setError(
          cause instanceof Error ? cause.message : "Unable to load records.",
        );
    } finally {
      if (current === version.current) setLoading(false);
    }
    // A new key deliberately invalidates the old request and creates a new reload callback.
  }, [key]);
  useEffect(() => {
    setData(null);
    void reload();
    return () => {
      ++version.current;
    };
  }, [reload]);
  return { data, error, loading, reload };
}
export function useTask() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const busy = useRef(false);
  async function run(work: () => Promise<void>, message = "Changes saved.") {
    if (busy.current) return false;
    busy.current = true;
    setPending(true);
    setError("");
    setNotice("");
    try {
      await work();
      setNotice(message);
      return true;
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to save changes.",
      );
      return false;
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return { pending, error, notice, run };
}
export function RemoteStatus({
  resource,
}: {
  resource: { loading: boolean; error: string; reload: () => Promise<void> };
}) {
  return resource.error ? (
    <div className="admin-alert" role="alert">
      {resource.error}{" "}
      <button
        onClick={() => {
          void resource.reload();
        }}
      >
        Retry loading
      </button>
    </div>
  ) : resource.loading ? (
    <p role="status">Loading records…</p>
  ) : null;
}
export function TaskStatus({
  task,
}: {
  task: { error: string; notice: string };
}) {
  return (
    <>
      {task.error && (
        <p className="admin-alert" role="alert">
          {task.error}
        </p>
      )}
      {task.notice && (
        <p className="admin-notice" role="status">
          {task.notice}
        </p>
      )}
    </>
  );
}
export function Pager({
  offset,
  count,
  setOffset,
}: {
  offset: number;
  count: number;
  setOffset: (offset: number) => void;
}) {
  return (
    <nav className="admin-pager" aria-label="Record pages">
      <button
        disabled={offset === 0}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Previous page
      </button>
      <span>Page {offset / 50 + 1}</span>
      <button disabled={count < 50} onClick={() => setOffset(offset + 50)}>
        Next page
      </button>
    </nav>
  );
}
export function localDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}
export function utcDate(local: string): string | null {
  return local ? new Date(local).toISOString() : null;
}
