import { useEffect, useRef } from "react";
import { useAuth } from "../auth/AuthProvider";
import { PresenceReporter, sendPresence } from "./presence";

export function useExamPresence(
  attemptId: string,
  subjectId: string,
  position: number,
  enabled: boolean,
) {
  const { profile } = useAuth();
  const token = useRef("");
  token.current = profile?.csrf_token || "";
  const reporter = useRef<PresenceReporter | null>(null);
  const latestPosition = useRef(position);
  latestPosition.current = position;
  useEffect(() => {
    if (!enabled) return;
    const current = new PresenceReporter(
      subjectId,
      latestPosition.current,
      (body, signal) => sendPresence(attemptId, token.current, body, signal),
    );
    reporter.current = current;
    current.start();
    return () => {
      current.stop();
      reporter.current = null;
    };
  }, [attemptId, subjectId, enabled]);
  useEffect(() => reporter.current?.setPosition(position), [position]);
}
