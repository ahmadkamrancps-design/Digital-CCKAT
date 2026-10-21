import { test, expect } from './fixtures';

test('candidate identity text stays inert and the portal cannot be framed', async ({ page, context }) => {
  const name = '<img src=x onerror="window.untrustedScriptRan=true">';
  const profile = {
    user: { id: 'security-user', email: null, display_name: name, role: 'CANDIDATE' },
    candidate: { id: 'security-candidate', roll_number: 'CCK-SECURITY-104', full_name: name, status: 'APPROVED' },
    csrf_token: 'test-csrf', session_expires_at: '2030-01-01T09:00:00Z',
  };
  await context.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/me') return route.fulfill({ json: profile });
    if (path === '/api/candidate/exams') return route.fulfill({ json: [] });
    throw new Error(`Unexpected request: ${path}`);
  });
  const response = await page.goto('/dashboard');
  expect(response?.headers()['x-frame-options']).toBe('DENY');
  expect(response?.headers()['content-security-policy']).toContain("frame-ancestors 'none'");
  await expect(page.getByRole('heading', { name: `Welcome, ${name}.` })).toBeVisible();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(await page.evaluate(() => 'untrustedScriptRan' in window)).toBe(false);
});

for (const path of ['/admin', '/proctor', '/grading', '/preview/admin']) {
  test(`anonymous navigation to ${path} never fetches staff data`, async ({ page, context }) => {
    const requested: string[] = [];
    await context.route('**/api/**', (route) => {
      requested.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 401, json: { detail: 'Please sign in.' } });
    });
    await page.goto(path);
    await expect(page.getByLabel('Roll number')).toBeVisible();
    expect(requested.length).toBeGreaterThan(0);
    expect(requested.every((request) => request === '/api/me')).toBe(true);
  });
}
