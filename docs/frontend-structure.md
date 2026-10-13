# Frontend structure

The requested source structure is in place alongside the existing authentication
and API modules. Google sign-in and the protected dashboard remain functional.

```text
frontend/
├── public/assets/cck/
│   ├── README.md
│   ├── logo.png
│   ├── login-background.png
│   └── dashboard-campus.png
├── src/
│   ├── components/
│   │   ├── CCKLogo.tsx
│   │   ├── CandidateSidebar.tsx
│   │   ├── ExamHeader.tsx
│   │   ├── ExamTimer.tsx
│   │   ├── FinishPreviewDialog.tsx
│   │   ├── Layout.tsx
│   │   ├── QuestionPalette.tsx
│   │   ├── QuestionRenderer.tsx
│   │   └── SaveStatus.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── CandidateInfoPage.tsx
│   │   ├── ExamPage.tsx
│   │   └── SubmissionPage.tsx
│   ├── data/mockExam.ts
│   ├── features/auth/
│   ├── features/exam/
│   │   ├── AssignedExams.tsx
│   │   ├── LiveExam.tsx
│   │   ├── LiveSubmission.tsx
│   │   ├── AnswerQueue.ts
│   │   ├── createSession.ts
│   │   ├── ServerDeadline.ts
│   │   └── ExamSessions.tsx
│   ├── features/exam-preview/ExamPreview.tsx
│   ├── features/exam-preview/SubmissionPreview.tsx
│   ├── features/preview/preview.ts
│   ├── services/api.ts
│   ├── services/exam.ts
│   ├── storage/recovery.ts
│   ├── types/
│   │   ├── auth.ts
│   │   ├── attempt.ts
│   │   └── exam.ts
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── tests/auth.test.tsx, api.test.ts, preview.test.tsx, exam-preview.test.tsx,
│   exam-state.test.ts, live-exam.test.tsx, recovery.test.ts, browser-storage.ts
├── e2e/resilience.spec.ts
└── playwright.config.ts
```

The stylesheet moved from `styles.css` to `index.css`. The dashboard uses the new
candidate sidebar and shared CCK logo component. The sidebar uses the supplied
navy design and six navigation links. Instructions, system check, and support
destinations are information scaffolds; profile displays registration details.
It appears only for candidate profiles. Existing authentication modules
and the shared layout were retained to preserve the working foundation. The login
route uses its own full-page layout with the supplied campus background, logo,
motto, and card. It uses the existing Google Identity Services control rather
than an inert Google button. Email sign-in is visibly disabled until a supported
backend flow exists; the footer labels are text pending their destinations.
Outside development preview, Google's configured control uses its blue Continue with Google button and popup
credential flow. Before a client ID is configured, a disabled button remains
visible with a setup message. The client ID must match the backend's Google
audience configuration; no candidate approval check is bypassed.

The candidate dashboard has its own full-page sidebar/content layout and campus
banner. Name, avatar initial, roll number, and registered email come from the
authenticated server profile. In live mode, exam cards show assignments and subject
names/durations/order from the backend. Sample dates and subjects appear only in
the explicitly labeled development preview. Existing sign-out, session checks,
and staff account behavior are preserved. The original campus banner crop remains.

`App.tsx` uses a default export. `/` is the login route; `/login` is retained as
a redirect to `/`, and unknown paths redirect to `/`. Approved sessions visiting
home return to `/dashboard`. Outside development preview, `/exam` and
`/submission` are protected live candidate pages.
`BrowserRouter` stays in `main.tsx`, wrapping the authentication provider and app
once. Session loading and recoverable API errors remain part of routing.
The public login layout renders immediately while the session check runs, with
an inline loading or retry message in its card. Sign-in becomes available only
after that check succeeds or confirms an anonymous session. Protected routes
continue to require a successful session check. API requests time out after ten
seconds rather than leaving the interface stuck indefinitely.

Outside development preview, `/exam` and `/submission` require an authenticated
candidate profile. `/exam` without parameters lists assignments. `?exam=<id>`
shows instructions before opening a new attempt; `?attempt=<id>` resumes its
server state and explicitly starts the next subject. `/submission?attempt=<id>&subject=<id>`
fetches the server-confirmed receipt; missing parameters show an empty state and
an active or inaccessible subject never shows success. Staff return to their dashboard.
Backend authorization remains necessary for every exam API; route guards only control navigation.

The exam header, timer, palette, and question renderer are presentation components.
The timer takes a display value; live integration derives it from server timestamps
and monotonic elapsed time. The save-status component is not used to claim
successful saving in the preview. `mockExam.ts` is imported only by the development
exam preview and contains no answer keys. Subjects are ordinary data rather than
a fixed subject enumeration. Live short answers allow 500 Unicode characters,
with local language/direction and plain text rendering. MCQ cross-out is a local
presentation preference. Serialized autosave and explicit conflict resolution live
in the exam feature modules. Background session checks do not discard drafts on
temporary network failure. Server denial still removes access. See
[Milestone 4 handover](milestone-4.md) for timing and interface details and
[Milestone 5 handover](milestone-5.md) for persistent recovery and synchronization.
Live queues journal drafts/revisions/pending requests in IndexedDB before upload,
retry transient failures, and require an explicit choice for stale recovered answers.
Storage failures visibly block edits until recovery saving works again. Web Locks
prevent two tabs editing the same subject in one browser profile. Fully synchronized
closed subjects clear their local copy; unsynchronized closed drafts remain local
and are disclosed without attempting a late save. Explicit logout clears that
account's recovery copies. The development preview remains intentionally in memory.

## Development preview

`VITE_ENABLE_UI_PREVIEW=true` in `frontend/.env` enables UI-only access during
`npm run dev`. The explicit `import.meta.env.DEV` guard disables this mode in
production builds, even if the flag is set. The default in `.env.example` is false.
The local workspace has preview enabled at the project owner's request.

In preview, the auth provider keeps its real profile null, skips session requests,
and blocks Google credential exchange. Separate display fixtures contain no session
or CSRF credentials. A visible banner identifies all screens as sample data, and
the login page links directly to the dashboard. No browser tokens are created or
persisted, and the backend retains its existing authentication and eligibility checks.

Dashboard, exam, submission, instructions, system-check, profile, and help routes
can be opened directly without a backend. `/exam` renders the CCK exam layout:
navy branded header, subject selector, paused timer, question palette, MCQ and
short-answer controls, previous/next navigation, review flags, and Clear Answer.
Native radio inputs and a native confirmation dialog support keyboard interaction;
Urdu content applies its own language and RTL direction. Mathematics expressions
are plain text rather than executable HTML.

The fixture repeats a small set of synthetic questions to fill a 30-question
palette per subject. Responses and question positions remain in React memory
while switching subjects. Refreshing or leaving the exam view resets them.
Finish locks only the local subject preview and displays the submission design;
it creates
no backend attempt, submission receipt, score, storage entry, or deadline.
The confirmation has CCK branding, a green check, subject, sample submission time,
question count, status, and an explicit notice that no test was submitted to CCK.
Continue follows the fixture's subject order, preserving other subject responses
in memory; the last subject links back to the dashboard. Restart clears only the
current subject's preview responses. There is no automatic redirect.
`/submission` also shows this design directly in development preview; an optional
`subject` query selects the sample subject. The paused timer does not represent
an active examination. Information pages do not implement exam or device-check logic.
Set the flag to false and restart Vite to restore the real login workflow.

## Image assets

These PNG assets are present in
`frontend/public/assets/cck/`:

- `logo.png`
- `login-background.png`
- `dashboard-campus.png`

`CCKLogo` loads `/assets/cck/logo.png` directly and
accepts an optional `size` prop (default 52 pixels). The login page uses
`login-background.png`; the dashboard banner uses `dashboard-campus.png`.
Public assets are accessible without authentication
and must never contain candidate records or sensitive exam content.

## Verification

Run `npm test` and `npm run build` from `frontend/`. Tests cover the existing login,
session restoration, access rejection, and logout behavior, plus protected routes,
staff redirects, and absence of fabricated server exam/submission state.
Preview tests cover answer retention during navigation and subject switching,
MCQ clearing, review flags, numeric input, Urdu text, Finish confirmation and
restart, continuation through subjects, direct submission design access, refresh
reset, and absence of API requests. Live tests exercise the real client against
stateful HTTP fixtures for saving/review, slow saves, conflict/retry handling,
refresh/resume, deadline locking, failed submission, server receipts, and next-subject
readiness. Recovery tests also exercise IndexedDB isolation, transactions, logout
invalidation, retry backoff, and storage failures. After installing Chromium with
`npx playwright install --with-deps chromium`, run `npm run test:e2e` for real-browser
offline/reload, lost acknowledgement, tab handoff, expiry, and conflict scenarios.

See the root README for Ubuntu/WSL development commands. Milestone 1's real Google
browser acceptance check still requires the configured OAuth client and approved
test account.
