import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxy = { '/api': { target: env.DEV_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } };
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true, proxy,
      headers: {
        'Referrer-Policy': 'no-referrer-when-downgrade',
        'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
      },
    },
    // Preview uses the same origin/port as the configured OAuth development site.
    preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    test: {
      include: ['tests/**/*.test.{ts,tsx}'], environment: 'jsdom', setupFiles: './tests/setup.ts', restoreMocks: true,
      // Bound concurrent jsdom instances to avoid CPU/memory contention on WSL and CI.
      maxWorkers: 2,
    },
  };
});
