import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../services/api";

export interface PollSnapshot<T> {
  data: T;
  requestedAt: number;
}

/** One request at a time. Retain labeled stale data on transient failures, clear it on access denial. */
export function usePoll<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
) {
  const loader = useRef(load);
  loader.current = load;
  const [snapshot, setSnapshot] = useState<PollSnapshot<T> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useRef<() => void>(() => {});
  useEffect(() => {
    let active = true;
    let busy = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    setSnapshot(null);
    setError("");
    setLoading(true);
    async function poll() {
      if (!active || busy) return;
      busy = true;
      clearTimeout(timer);
      controller = new AbortController();
      const requestedAt = performance.now();
      try {
        const data = await loader.current(controller.signal);
        if (active) {
          setSnapshot({ data, requestedAt });
          setError("");
          failures = 0;
        }
      } catch (cause) {
        if (active) {
          if (
            cause instanceof ApiError &&
            [401, 403, 404].includes(cause.status)
          )
            setSnapshot(null);
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to refresh monitoring.",
          );
          failures++;
        }
      } finally {
        busy = false;
        if (active) {
          setLoading(false);
          timer = setTimeout(
            () => {
              void poll();
            },
            Math.min(30_000, 5000 * 2 ** Math.min(failures, 3)),
          );
        }
      }
    }
    refresh.current = () => {
      void poll();
    };
    const online = () => {
      void poll();
    };
    const visible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    window.addEventListener("online", online);
    document.addEventListener("visibilitychange", visible);
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
      controller?.abort();
      refresh.current = () => {};
      window.removeEventListener("online", online);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [key]);
  return { snapshot, error, loading, refresh: () => refresh.current() };
}
