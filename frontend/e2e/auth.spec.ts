import { test, expect } from './fixtures';

test('candidate signs in with admissions details, refreshes, and signs out without Google', async ({ page, context }) => {
  let signedIn = false;
  const writes: unknown[] = [];
  const profile = {
    user: { id: 'admissions-user', email: null, display_name: 'محمد احمد', role: 'CANDIDATE' },
    candidate: { id: 'admissions-candidate', roll_number: 'CCK-PORTAL-104', full_name: 'محمد احمد', status: 'APPROVED' },
    csrf_token: 'browser-test-csrf', session_expires_at: '2030-01-01T09:00:00Z',
  };
  await context.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const send = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (path === '/api/me') return signedIn ? send(profile) : send({ detail: 'Please sign in.' }, 401);
    if (path === '/api/auth/candidate') {
      writes.push(request.postDataJSON());
      signedIn = true;
      return send(profile);
    }
    if (path === '/api/candidate/exams') return send([]);
    if (path === '/api/auth/logout') {
      expect(request.headers()['x-csrf-token']).toBe(profile.csrf_token);
      signedIn = false;
      return route.fulfill({ status: 204 });
    }
    throw new Error(`Unexpected request: ${request.method()} ${path}`);
  });
  await page.goto('/');
  await expect(page.getByLabel('Roll number')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue with Google' })).not.toBeVisible();
  await page.getByLabel('Roll number').fill('CCK-PORTAL-104');
  await page.getByLabel('Full name').fill('محمد احمد');
  await page.getByLabel('Father’s name').fill('محمد کامران');
  await page.screenshot({ path: 'test-results/candidate-login.png', fullPage: true });
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome, محمد احمد.' })).toBeVisible();
  expect(writes).toEqual([{ roll_number: 'CCK-PORTAL-104', full_name: 'محمد احمد', father_name: 'محمد کامران' }]);
  await page.reload();
  await expect(page.getByText('CCK-PORTAL-104', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Roll number')).toBeVisible();
});

test('invalid admissions details preserve input and keep the candidate outside the dashboard', async ({ page, context }) => {
  await context.route('**/api/**', (route) => route.fulfill({
    status: 401, contentType: 'application/json',
    body: JSON.stringify({ detail: 'Unable to sign in. Check your admissions details or contact admissions.' }),
  }));
  await page.goto('/');
  await page.getByLabel('Roll number').fill('UNKNOWN-104');
  await page.getByLabel('Full name').fill('Example Candidate');
  await page.getByLabel('Father’s name').fill('Example Father');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Check your admissions details');
  await expect(page.getByLabel('Roll number')).toHaveValue('UNKNOWN-104');
  await expect(page).toHaveURL('/');
});
