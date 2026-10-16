import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DeviceReadiness } from '../src/features/candidate/DeviceReadiness';

beforeEach(() => {
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ status: 'ready' }), { headers: { 'Content-Type': 'application/json' } })));
});
afterEach(() => vi.unstubAllGlobals());

it('checks real writable IndexedDB and server readiness', async () => {
  render(<DeviceReadiness />);
  expect(await screen.findByText('Checks passed. Wait for your proctor before starting.')).toBeInTheDocument();
  expect(screen.getByText('Answer recovery storage: Passed')).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith('/api/health/ready', expect.objectContaining({ cache: 'no-store' }));
});

it('does not report ready when the service is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Service is not ready.' }), { status: 503 })));
  render(<DeviceReadiness />);
  expect(await screen.findByText('Exam service connection: Needs attention')).toBeInTheDocument();
  expect(screen.queryByText('Checks passed. Wait for your proctor before starting.')).not.toBeInTheDocument();
});

it('warns when the browser cannot preserve recovery drafts', async () => {
  vi.stubGlobal('indexedDB', { open: () => { throw new Error('Storage disabled'); } });
  render(<DeviceReadiness />);
  expect(await screen.findByText('Answer recovery storage: Needs attention')).toBeInTheDocument();
  expect(screen.queryByText('Checks passed. Wait for your proctor before starting.')).not.toBeInTheDocument();
});
