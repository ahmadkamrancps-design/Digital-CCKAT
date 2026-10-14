import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PresenceReporter, sendPresence } from "../src/features/exam/presence";
import { ApiError } from "../src/services/api";
import type { PresenceWrite } from "../src/types/proctor";

const reporters: PresenceReporter[] = [];
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  reporters.splice(0).forEach((reporter) => reporter.stop());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
function reporter(
  send: (body: PresenceWrite, signal: AbortSignal) => Promise<unknown>,
) {
  const value = new PresenceReporter("subject-1", 1, send);
  reporters.push(value);
  value.start();
  return value;
}
describe("best-effort exam presence", () => {
  it("reports only subject, question position, and allowlisted events every 10 seconds", async () => {
    const send = vi.fn(
      async (_body: PresenceWrite, _signal: AbortSignal) => {},
    );
    const current = reporter(send);
    await vi.advanceTimersByTimeAsync(0);
    expect(send.mock.calls[0][0]).toEqual({
      subject_attempt_id: "subject-1",
      question_sequence: 1,
      events: [],
    });
    current.setPosition(23);
    document.dispatchEvent(new Event("fullscreenchange"));
    await vi.advanceTimersByTimeAsync(9999);
    expect(send).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(send.mock.calls[1][0]).toMatchObject({
      question_sequence: 23,
      events: [{ event_type: "FULLSCREEN_EXIT" }],
    });
    expect(Object.keys(send.mock.calls[1][0]).sort()).toEqual([
      "events",
      "question_sequence",
      "subject_attempt_id",
    ]);
    expect(Object.keys(send.mock.calls[1][0].events[0]).sort()).toEqual([
      "event_id",
      "event_type",
    ]);
  });
  it("reuses event identifiers after a lost acknowledgement and removes acknowledged events", async () => {
    const send = vi
      .fn(async (_body: PresenceWrite, _signal: AbortSignal) => {})
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new ApiError(0, "Interrupted"));
    reporter(send);
    await vi.advanceTimersByTimeAsync(0);
    window.dispatchEvent(new Event("offline"));
    await vi.advanceTimersByTimeAsync(10_000);
    const failed = send.mock.calls[1][0].events;
    await vi.advanceTimersByTimeAsync(20_000);
    expect(send.mock.calls[2][0].events).toEqual(failed);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(send.mock.calls[3][0].events).toEqual([]);
  });
  it("bounds buffered reports and each batch without sending arbitrary metadata", async () => {
    const send = vi.fn(
      async (_body: PresenceWrite, _signal: AbortSignal) => {},
    );
    reporter(send);
    await vi.advanceTimersByTimeAsync(0);
    for (let index = 0; index < 50; index++)
      document.dispatchEvent(new Event("fullscreenchange"));
    for (let index = 0; index < 5; index++)
      await vi.advanceTimersByTimeAsync(10_000);
    expect(
      send.mock.calls.slice(1).map(([body]) => body.events.length),
    ).toEqual([8, 8, 8, 8, 0]);
    expect(
      new Set(
        send.mock.calls.flatMap(([body]) =>
          body.events.map((event) => event.event_id),
        ),
      ).size,
    ).toBe(32);
  });
  it.each([401, 403, 410])(
    "stops reporting after access or subject closure (%s)",
    async (status) => {
      const send = vi.fn().mockRejectedValue(new ApiError(status, "Closed"));
      reporter(send);
      await vi.advanceTimersByTimeAsync(0);
      window.dispatchEvent(new Event("online"));
      await vi.advanceTimersByTimeAsync(60_000);
      expect(send).toHaveBeenCalledTimes(1);
    },
  );
  it("does not overlap slow requests and cancels them when the subject ends", async () => {
    let finish!: () => void;
    const send = vi.fn(
      async (_body: PresenceWrite, _signal: AbortSignal) =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const current = reporter(send);
    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(60_000);
    expect(send).toHaveBeenCalledTimes(1);
    current.stop();
    expect(send.mock.calls[0][1].aborted).toBe(true);
    finish();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(send).toHaveBeenCalledTimes(1);
  });
  it("sends authenticated CSRF-protected telemetry through the normal API client", async () => {
    const fetcher = vi.fn(
      async () =>
        new Response('{"server_time":"2026-10-15T09:00:00Z"}', {
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetcher);
    await sendPresence(
      "attempt-1",
      "test-csrf",
      { subject_attempt_id: "subject-1", question_sequence: 1, events: [] },
      new AbortController().signal,
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/candidate/attempts/attempt-1/presence",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf" }),
      }),
    );
  });
});
