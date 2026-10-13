import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../src/services/api';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function pendingFetch() {
  return vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
    options.signal?.addEventListener('abort', () => {
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  }));
}

describe('API request lifecycle', () => {
  it('aborts a stalled request and returns a safe retry message after ten seconds', async () => {
    const fetcher = pendingFetch();
    vi.stubGlobal('fetch', fetcher);
    const result = api('/me').catch((error: unknown) => error);
    const signal = fetcher.mock.calls[0][1].signal;
    await vi.advanceTimersByTimeAsync(9_999);
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const error = await result;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, message: 'The server is taking too long to respond. Please try again.' });
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears the timeout after a successful response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }))));
    expect(await api('/health')).toEqual({ status: 'ok' });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('forwards caller cancellation without leaving a timeout behind', async () => {
    const fetcher = pendingFetch();
    vi.stubGlobal('fetch', fetcher);
    const controller = new AbortController();
    const result = api('/me', { signal: controller.signal }).catch((error: unknown) => error);
    controller.abort();
    expect(await result).toBeInstanceOf(ApiError);
    expect(fetcher.mock.calls[0][1].signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
