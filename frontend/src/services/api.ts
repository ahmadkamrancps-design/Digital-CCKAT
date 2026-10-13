export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly detail?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 10_000);
  const cancel = () => controller.abort();
  options.signal?.addEventListener('abort', cancel, { once: true });
  if (options.signal?.aborted) cancel();
  try {
    const response = await fetch(`/api${path}`, {
      ...options,
      signal: controller.signal,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const detail = typeof body === 'object' && body !== null && 'detail' in body
        && typeof body.detail === 'string' ? body.detail : 'Unable to complete this request.';
      const data = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : undefined;
      throw new ApiError(response.status, detail, data);
    }
    return response.status === 204 ? undefined as T : await response.json() as T;
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    throw new ApiError(0, timedOut
      ? 'The server is taking too long to respond. Please try again.'
      : 'Unable to connect. Check your connection and try again.');
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', cancel);
  }
}
