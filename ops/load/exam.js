// Run only against a dedicated synthetic rehearsal database. Never real candidates.
import http from 'k6/http';
import { check, sleep, fail } from 'k6';
import { SharedArray } from 'k6/data';
import { Rate, Trend } from 'k6/metrics';

const manifestPath = __ENV.CCK_REHEARSAL_MANIFEST;
if (!manifestPath) throw new Error('Set CCK_REHEARSAL_MANIFEST to the private synthetic manifest.');
const manifest = new SharedArray('synthetic exam metadata', () => {
  const value = JSON.parse(open(manifestPath));
  return [{ kind: value.kind, origin: value.origin, exam_id: value.exam_id }];
})[0];
if (manifest.kind !== 'CCK_REHEARSAL_ONLY') throw new Error('A synthetic rehearsal manifest is required.');
const candidates = new SharedArray('synthetic candidates', () => JSON.parse(open(manifestPath)).candidates);
const vus = Number(__ENV.CCK_VUS || 20);
const offset = Number(__ENV.CCK_CANDIDATE_OFFSET || 2);
const ramp = Number(__ENV.CCK_RAMP_SECONDS || 10);
const sectionSeconds = Number(__ENV.CCK_SECTION_SECONDS || 0);
const questionPause = Number(__ENV.CCK_QUESTION_PAUSE_SECONDS || 0.1);
const base = (__ENV.CCK_BASE_URL || manifest.origin).replace(/\/$/, '');
if (vus < 1 || vus + offset > candidates.length || vus > 7000) throw new Error('Seed enough synthetic candidates for 1..7000 VUs plus the reserved browser accounts.');
const integrityFailures = new Rate('integrity_failures');
const saves = new Trend('answer_save_ms', true);

export const options = {
  scenarios: { examination: { executor: 'per-vu-iterations', vus, iterations: 1, maxDuration: __ENV.CCK_MAX_DURATION || '3h30m' } },
  thresholds: {
    http_req_failed: ['rate<0.001'], checks: ['rate>0.999'],
    integrity_failures: ['rate==0'], answer_save_ms: ['p(95)<1500', 'p(99)<3000'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
  // Self-signed TLS is allowed only with an explicit local-rehearsal switch.
  insecureSkipTLSVerify: __ENV.CCK_LOCAL_SELF_SIGNED === 'true',
};

function verify(condition, label) {
  const valid = check(condition, { [label]: (value) => value === true });
  integrityFailures.add(!valid);
  if (!valid) fail(label);
}

function request(method, path, body, csrf, expected = [200]) {
  const response = http.request(method, `${base}/api${path}`, body === undefined ? null : JSON.stringify(body), {
    headers: { Origin: manifest.origin, 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    responseCallback: http.expectedStatuses(...expected), timeout: '35s',
    tags: { name: path.replace(/[a-f0-9]{8}-[a-f0-9-]{27,}/g, ':id') },
  });
  verify(expected.includes(response.status), `${method} expected status`);
  return response;
}

let lastHeartbeat = 0;
function pace(seconds, attemptPath, subjectId, csrf) {
  const until = Date.now() + seconds * 1000;
  while (Date.now() < until) {
    if (Date.now() - lastHeartbeat >= 10000) {
      lastHeartbeat = Date.now();
      const response = request('POST', `${attemptPath}/presence`, { subject_attempt_id: subjectId, question_sequence: 1, events: [] }, csrf, [200, 410]);
      if (response.status === 410) return;
    }
    sleep(Math.min(1, Math.max(0, (until - Date.now()) / 1000)));
  }
}

export default function () {
  sleep((__VU - 1) * ramp / vus);
  const credentials = candidates[__VU - 1 + offset];
  verify(credentials.roll_number.startsWith('REHEARSAL-'), 'Synthetic candidate identity');
  const signed = request('POST', '/auth/candidate', credentials).json();
  verify(signed.candidate.roll_number === credentials.roll_number, 'Correct candidate authorized');
  const csrf = signed.csrf_token;
  const assigned = request('GET', '/candidate/exams').json();
  verify(assigned.some((exam) => exam.exam_id === manifest.exam_id && exam.title.startsWith('REHEARSAL ')), 'Assigned synthetic exam');
  let attempt = request('POST', `/candidate/exams/${manifest.exam_id}/attempt`, undefined, csrf).json();
  const resumed = request('POST', `/candidate/exams/${manifest.exam_id}/attempt`, undefined, csrf).json();
  verify(attempt.id === resumed.id, 'One logical exam attempt');
  const attemptPath = `/candidate/attempts/${attempt.id}`;
  for (let index = 0; index < attempt.subjects.length; index++) {
    const subjectPath = `${attemptPath}/subjects/${attempt.subjects[index].id}`;
    attempt = request('POST', `${subjectPath}/start`, undefined, csrf).json();
    const startedAt = Date.now();
    const deadline = attempt.subjects[index].expires_at;
    const paper = request('GET', `${subjectPath}/questions`).json();
    verify(paper.questions.length === 30, 'Complete configured paper');
    verify(!JSON.stringify(paper).match(/is_correct|accepted_answers|correct_option_id|grading_config/), 'No private answer keys');
    for (let number = 0; number < paper.questions.length; number++) {
      const question = paper.questions[number];
      const body = { expected_revision: 0,
        selected_option_id: question.type === 'MCQ' ? question.options[0].id : null,
        short_answer_text: question.type === 'MCQ' ? null : index === 0 ? 'light' : index === 1 ? '3' : 'اردو',
        is_marked_for_review: number === 0 };
      const path = `${subjectPath}/answers/${question.exam_question_id}`;
      const response = request('PUT', path, body, csrf);
      saves.add(response.timings.duration);
      verify(response.json().answer.revision === 1, 'Answer stored once');
      if (number === 0) {
        verify(request('PUT', path, body, csrf).json().answer.revision === 1, 'Retry is idempotent');
        request('PUT', path, { ...body, is_marked_for_review: false }, csrf, [409]);
        const refreshed = request('GET', subjectPath + '/questions').json();
        verify(refreshed.questions[0].answer.revision === 1 && refreshed.questions[0].answer.is_marked_for_review, 'Stale retry preserves answer and review flag');
      }
      const pause = sectionSeconds > 0 ? Math.max(0, (sectionSeconds - 30) / 30) : questionPause;
      pace(pause, attemptPath, attempt.subjects[index].id, csrf);
    }
    pace(Math.max(0, sectionSeconds - (Date.now() - startedAt) / 1000), attemptPath, attempt.subjects[index].id, csrf);
    const refreshed = request('GET', attemptPath).json();
    verify(refreshed.subjects[index].expires_at === deadline, 'Resume never resets deadline');
    // A long soak may intentionally reach its server deadline before this call.
    attempt = request('POST', `${subjectPath}/submit`, undefined, csrf).json();
    verify(['SUBMITTED', 'EXPIRED'].includes(attempt.subjects[index].status), 'Subject locked');
    request('PUT', `${subjectPath}/answers/${paper.questions[0].exam_question_id}`, { expected_revision: 1, selected_option_id: paper.questions[0].options[0].id, short_answer_text: null, is_marked_for_review: false }, csrf, [410]);
  }
  attempt = request('POST', attemptPath + '/submit', undefined, csrf).json();
  verify(attempt.status === 'SUBMITTED', 'Final submission recorded');
  const result = request('GET', '/candidate/results').json().find((item) => item.attempt_id === attempt.id);
  verify(result && result.marks_awarded === null && result.subjects.length === 0, 'Results remain withheld');
}
