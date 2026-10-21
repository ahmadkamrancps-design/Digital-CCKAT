/** Real HTTPS/DB rehearsal. It is intentionally separate from mocked Playwright specs. */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium, expect } from '@playwright/test';

const manifest = JSON.parse(readFileSync(process.env.CCK_REHEARSAL_MANIFEST, 'utf8'));
if (manifest.kind !== 'CCK_REHEARSAL_ONLY') throw new Error('Only synthetic rehearsal manifests are accepted.');
const base = process.env.CCK_BASE_URL || manifest.origin;
const browser = await chromium.launch({ headless: true });
const contexts = [];
const restartControl = process.env.CCK_RESTART_CONTROL_DIRECTORY;
let phase = 'browser_start';
function checkpoint(next) {
  phase = next;
  console.log(`REHEARSAL_PHASE ${phase}`);
}
async function waitForRestartMarker(name) {
  const deadline = Date.now() + 150000;
  while (!existsSync(join(restartControl, name))) {
    if (Date.now() >= deadline) throw new Error(`Timed out waiting for restart stage: ${name}`);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}
function restartMarker(name) {
  writeFileSync(join(restartControl, name), '', { mode: 0o600, flag: 'wx' });
}
async function context() {
  const value = await browser.newContext({ ignoreHTTPSErrors: process.env.CCK_LOCAL_SELF_SIGNED === 'true', viewport: { width: 1366, height: 900 } });
  await value.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort());
  contexts.push(value);
  return value;
}
async function api(owner, method, path, body, csrf, statuses = [200]) {
  const response = await owner.request.fetch(`${base}/api${path}`, { method, headers: { Origin: manifest.origin, 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, ...(body === undefined ? {} : { data: body }) });
  if (!statuses.includes(response.status())) throw new Error(`Rehearsal API failed: ${method} ${path.replace(/[a-f0-9-]{36}/g, ':id')} status ${response.status()}`);
  return response.status() === 204 ? null : response.json();
}
try {
  checkpoint('candidate_login');
  const candidate = await context();
  const page = await candidate.newPage();
  const initial = await page.goto(`${base}/dashboard`);
  expect(initial.headers()['strict-transport-security']).toContain('max-age=');
  expect(initial.headers()['content-security-policy']).toContain("script-src 'self'");
  await expect(page.getByLabel('Roll number')).toBeVisible();
  await expect(page.getByText(/Development preview/)).toHaveCount(0);
  await expect(page.getByText(/Local management sandbox/)).toHaveCount(0);
  await api(candidate, 'GET', '/local-management', undefined, undefined, [404]);
  await api(candidate, 'POST', '/local-management', { nonce: 'not-a-sandbox' }, undefined, [404]);
  const credentials = manifest.candidates[0];
  await page.getByLabel('Roll number').fill(credentials.roll_number);
  await page.getByLabel('Full name').fill(credentials.full_name);
  await page.getByLabel('Father’s name').fill(credentials.father_name);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: `Welcome, ${credentials.full_name}.` })).toBeVisible();
  await page.goto(`${base}/system-check`);
  checkpoint('device_readiness');
  await expect(page.getByText('Checks passed. Wait for your proctor before starting.')).toBeVisible();
  await page.goto(`${base}/instructions`);
  await page.getByRole('link', { name: 'My Exam →' }).click();
  await page.getByRole('link', { name: 'View instructions →' }).click();
  await page.getByRole('button', { name: 'Open assigned exam' }).click();
  await page.getByRole('button', { name: 'Start English' }).click();
  checkpoint('english_answers');
  await expect(page.getByRole('heading', { name: 'Question 1 of 30' })).toBeVisible();
  const attemptId = new URL(page.url()).searchParams.get('attempt');
  let session = await api(candidate, 'GET', '/me');
  let attempt = await api(candidate, 'GET', `/candidate/attempts/${attemptId}`);
  const firstDeadline = attempt.subjects[0].expires_at;
  await page.getByRole('radio').first().check();
  await page.getByRole('button', { name: 'Mark for Review' }).click();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByLabel('Your answer', { exact: true }).fill('light');
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  if (restartControl) {
    checkpoint('service_restart');
    const subjectPath = `/candidate/attempts/${attemptId}/subjects/${attempt.subjects[0].id}`;
    const before = await api(candidate, 'GET', subjectPath + '/questions');
    restartMarker('before-restart');
    await waitForRestartMarker('services-stopped');
    await page.getByLabel('Your answer', { exact: true }).fill('restart recovery answer');
    await expect(page.getByText('Offline / waiting to sync', { exact: true })).toBeVisible({ timeout: 20000 });
    await expect(page.getByText('Saved on this device · awaiting server confirmation', { exact: true })).toBeVisible();
    restartMarker('draft-preserved');
    await waitForRestartMarker('api-restarted');
    await expect(page.getByText('Saved', { exact: true })).toBeVisible({ timeout: 20000 });
    const recovered = await api(candidate, 'GET', subjectPath + '/questions');
    expect(recovered.questions[1].answer.short_answer_text).toBe('restart recovery answer');
    expect(recovered.questions[1].answer.revision).toBe(before.questions[1].answer.revision + 1);
    expect(recovered.questions[0].answer).toEqual(before.questions[0].answer);
    const resumed = await api(candidate, 'GET', `/candidate/attempts/${attemptId}`);
    expect(resumed.subjects[0].expires_at).toBe(firstDeadline);
    expect(resumed.subjects[0].started_at).toBe(attempt.subjects[0].started_at);
    restartMarker('api-recovery-verified');
    await waitForRestartMarker('worker-restarted');
    checkpoint('relogin_resume');
    session = await api(candidate, 'POST', '/auth/candidate', credentials);
    const reopened = await api(candidate, 'POST', `/candidate/exams/${manifest.exam_id}/attempt`, undefined, session.csrf_token);
    expect(reopened.id).toBe(attemptId);
    expect(reopened.subjects[0].expires_at).toBe(firstDeadline);
    await page.reload();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(page.getByLabel('Your answer', { exact: true })).toHaveValue('restart recovery answer');
  }
  checkpoint('offline_recovery');
  await candidate.setOffline(true);
  await page.getByLabel('Your answer', { exact: true }).fill('offline recovery answer');
  await expect(page.getByText('Offline / waiting to sync', { exact: true })).toBeVisible();
  await candidate.setOffline(false);
  await expect(page.getByText('Saved', { exact: true })).toBeVisible({ timeout: 20000 });
  await page.reload();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByLabel('Your answer', { exact: true })).toHaveValue('offline recovery answer');
  attempt = await api(candidate, 'GET', `/candidate/attempts/${attemptId}`);
  expect(attempt.subjects[0].expires_at).toBe(firstDeadline);
  checkpoint('english_submission');
  await page.getByRole('button', { name: 'Finish', exact: true }).click();
  await page.getByRole('button', { name: 'Submit subject', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Test Submitted Successfully!' })).toBeVisible();
  await page.getByRole('link', { name: 'Continue to Mathematics' }).click();
  checkpoint('mathematics_answers');
  await page.getByRole('button', { name: 'Start Mathematics' }).click();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByLabel('Your answer', { exact: true }).fill('3');
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  checkpoint('mathematics_submission');
  await page.getByRole('button', { name: 'Finish', exact: true }).click();
  await page.getByRole('button', { name: 'Submit subject', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Test Submitted Successfully!' })).toBeVisible();
  await page.getByRole('link', { name: 'Continue to Urdu' }).click();
  checkpoint('urdu_answers');
  await page.getByRole('button', { name: 'Start Urdu' }).click();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByLabel('Your answer', { exact: true }).fill('اردو');
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  expect(await page.locator('.question-body').getAttribute('dir')).toBe('rtl');
  checkpoint('urdu_submission');
  await page.getByRole('button', { name: 'Finish', exact: true }).click();
  await page.getByRole('button', { name: 'Submit subject', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Test Submitted Successfully!' })).toBeVisible();
  await page.goto(`${base}/results`);
  checkpoint('withheld_results');
  await expect(page.getByText('Your result is not available yet. Administration will release results when ready.')).toBeVisible();
  const admin = await context();
  await admin.addCookies([{ name: 'cck_session', value: manifest.admin.cookie, domain: new URL(base).hostname, path: '/api', httpOnly: true, secure: true, sameSite: 'Lax' }]);
  const csrf = manifest.admin.profile.csrf_token;
  checkpoint('admin_overview');
  const staffPage = await admin.newPage();
  await staffPage.goto(`${base}/admin`);
  await expect(staffPage.getByRole('heading', { name: 'Administration overview' })).toBeVisible();
  await expect(staffPage.getByRole('link', { name: /Registered candidates/ })).toContainText(String(manifest.candidates.length));
  await staffPage.getByRole('navigation', { name: 'Administration', exact: true }).getByRole('link', { name: 'Candidates', exact: true }).click();
  await expect(staffPage.getByRole('heading', { name: 'Candidate management' })).toBeVisible();
  await expect(staffPage.getByText(manifest.candidates[0].roll_number, { exact: true })).toBeVisible();
  checkpoint('manual_grading');
  const pending = await api(admin, 'GET', `/grading/exams/${manifest.exam_id}/queue?limit=100`);
  for (const row of pending) {
    await api(admin, 'POST', `/grading/answers/${row.answer_id}/grade`, { expected_revision: 0, marks_awarded: '0.50', notes: 'Synthetic rehearsal manual mark' }, csrf);
  }
  // Other synthetic load candidates may also need manual marks; fetch successive pages
  // from the shrinking pending queue so publication is a real completeness check.
  for (let pass = 0; pass < 1000; pass++) {
    const remaining = await api(admin, 'GET', `/grading/exams/${manifest.exam_id}/queue?limit=100`);
    if (remaining.length === 0) break;
    for (const row of remaining) await api(admin, 'POST', `/grading/answers/${row.answer_id}/grade`, { expected_revision: 0, marks_awarded: '0.50', notes: 'Synthetic rehearsal manual mark' }, csrf);
  }
  await api(admin, 'POST', `/admin/exams/${manifest.exam_id}/start-authorization`, { authorized: false }, csrf);
  checkpoint('result_release');
  await api(admin, 'POST', `/admin/exams/${manifest.exam_id}/result-release`, { released: true, result_release_at: null }, csrf);
  await page.reload();
  await expect(page.getByText('Result released', { exact: true })).toBeVisible();
  const results = await api(candidate, 'GET', '/candidate/results');
  expect(results.find((value) => value.attempt_id === attemptId).publication_status).toBe('RELEASED');
  expect(results.find((value) => value.attempt_id === attemptId).marks_awarded).toBe('2.50');
  checkpoint('result_withholding');
  await api(admin, 'POST', `/admin/exams/${manifest.exam_id}/result-release`, { released: false, result_release_at: null }, csrf);
  await page.reload();
  await expect(page.getByText('Your result is not available yet. Administration will release results when ready.')).toBeVisible();
  console.log('PASS: production HTTPS, secure login, readiness, MCQ/short answer, review, offline recovery, refresh, three subjects, manual grading, release and withholding');
} catch (error) {
  // Publish only fixed phase labels and an allowlisted error category. Playwright's
  // full error can contain answer text or credentials and stays in private logs.
  const category = error?.name === 'TimeoutError' ? 'timeout' : 'assertion_or_request';
  console.log(`REHEARSAL_FAILURE phase=${phase} category=${category}`);
  throw error;
} finally {
  for (const value of contexts) await value.close();
  await browser.close();
}
