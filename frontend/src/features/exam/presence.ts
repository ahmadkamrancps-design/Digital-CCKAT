import { api, ApiError } from "../../services/api";
import type {
  ClientEvent,
  ClientEventType,
  PresenceWrite,
} from "../../types/proctor";

/** Best-effort monitoring only. No answers, exam timers, or recovery journals enter this channel. */
export class PresenceReporter {
  private events: ClientEvent[] = [];
  private active = false;
  private running = false;
  private timer?: ReturnType<typeof setTimeout>;
  private failures = 0;
  private controller?: AbortController;
  private position: number;
  constructor(
    private readonly subject: string,
    position: number,
    private readonly send: (
      body: PresenceWrite,
      signal: AbortSignal,
    ) => Promise<unknown>,
  ) {
    this.position = position;
  }
  setPosition(position: number) {
    this.position = position;
  }
  private report(type: ClientEventType) {
    if (!this.active) return;
    if (this.events.length === 32) this.events.shift();
    this.events.push({ event_id: crypto.randomUUID(), event_type: type });
  }
  private offline = () => this.report("CONNECTION_LOST");
  private online = () => {
    this.report("CONNECTION_RESTORED");
    void this.flush();
  };
  private visibility = () => {
    this.report(
      document.visibilityState === "hidden"
        ? "VISIBILITY_HIDDEN"
        : "VISIBILITY_VISIBLE",
    );
  };
  private fullscreen = () =>
    this.report(
      document.fullscreenElement ? "FULLSCREEN_ENTER" : "FULLSCREEN_EXIT",
    );
  start() {
    if (this.active) return;
    this.active = true;
    window.addEventListener("offline", this.offline);
    window.addEventListener("online", this.online);
    document.addEventListener("visibilitychange", this.visibility);
    document.addEventListener("fullscreenchange", this.fullscreen);
    void this.flush();
  }
  private async flush() {
    if (!this.active || this.running) return;
    clearTimeout(this.timer);
    this.running = true;
    this.controller = new AbortController();
    const events = this.events.slice(0, 8);
    try {
      await this.send(
        {
          subject_attempt_id: this.subject,
          question_sequence: this.position,
          events,
        },
        this.controller.signal,
      );
      const acknowledged = new Set(events.map((event) => event.event_id));
      this.events = this.events.filter(
        (event) => !acknowledged.has(event.event_id),
      );
      this.failures = 0;
    } catch (cause) {
      if (cause instanceof ApiError && [401, 403, 410].includes(cause.status))
        this.stop();
      else this.failures++;
    } finally {
      this.running = false;
      if (this.active)
        this.timer = setTimeout(
          () => {
            void this.flush();
          },
          Math.min(30_000, 10_000 * 2 ** Math.min(this.failures, 2)),
        );
    }
  }
  stop() {
    this.active = false;
    clearTimeout(this.timer);
    this.controller?.abort();
    window.removeEventListener("offline", this.offline);
    window.removeEventListener("online", this.online);
    document.removeEventListener("visibilitychange", this.visibility);
    document.removeEventListener("fullscreenchange", this.fullscreen);
  }
}

export function sendPresence(
  attemptId: string,
  csrf: string,
  body: PresenceWrite,
  signal: AbortSignal,
) {
  return api<{ server_time: string }>(
    `/candidate/attempts/${encodeURIComponent(attemptId)}/presence`,
    {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      body: JSON.stringify(body),
      signal,
    },
  );
}
