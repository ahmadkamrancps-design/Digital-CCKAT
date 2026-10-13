/** Anchor server time to a monotonic clock. Changing the device date cannot extend time. */
export class ServerDeadline {
  private end = Number.NEGATIVE_INFINITY;
  private expiry: string | null = null;
  sync(expiresAt: string | null, serverTime: string, requestStarted: number) {
    const milliseconds = Date.parse(expiresAt || '') - Date.parse(serverTime);
    // Subtract the entire request duration conservatively; never grant response transit time.
    const candidateEnd = requestStarted + Math.max(0, milliseconds);
    this.end = this.expiry === expiresAt ? Math.min(this.end, candidateEnd) : candidateEnd;
    this.expiry = expiresAt;
  }
  seconds() { return Math.max(0, Math.ceil((this.end - performance.now()) / 1000)); }
  writable() { return Number.isFinite(this.end) && performance.now() < this.end; }
}
