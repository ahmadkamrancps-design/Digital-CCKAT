import react from '@vitejs/plugin-react';
import { loadEnv, type ProxyOptions } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxy = { '/api': {
    target: env.DEV_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true,
    configure(proxyServer) {
      proxyServer.on('proxyReq', (request) => {
        // The development proxy is not an identity gateway. Never forward client claims of IP.
        for (const header of ['forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto']) request.removeHeader(header);
      });
    },
  } } satisfies Record<string, ProxyOptions>;
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true, proxy,
      headers: {
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
        'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
        'X-Content-Type-Options': 'nosniff',
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
