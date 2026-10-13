/** Test implementation of the browser lock lifetime; production uses navigator.locks. */
export class TestLocks {
  private held = new Set<string>();
  private jobs = new Set<Promise<unknown>>();
  request<T>(name: string, _options: LockOptions, callback: (lock: Lock | null) => Promise<T>): Promise<T> {
    const acquired = !this.held.has(name);
    if (acquired) this.held.add(name);
    const job = Promise.resolve().then(() => callback(acquired ? { name, mode: 'exclusive' } as Lock : null))
      .finally(() => { if (acquired) this.held.delete(name); this.jobs.delete(job); });
    this.jobs.add(job);
    return job;
  }
  async idle() { await Promise.allSettled([...this.jobs]); }
}
