import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5174', browserName: 'chromium', viewport: { width: 1366, height: 900 }, trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run dev -- --port 5174', wait: { stdout: /Local:/ }, reuseExistingServer: false,
    env: { VITE_ENABLE_UI_PREVIEW: 'false', VITE_GOOGLE_CLIENT_ID: '' },
  },
});
