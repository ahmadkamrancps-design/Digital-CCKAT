# Administration portal

The updated portal keeps the existing Milestone 6 management APIs and workflows,
with a CCK navy/gold workspace designed around common admissions tasks. Candidate
exam, submission and login templates retain their existing behavior.

## Access and preview

For **editable local management testing without Google**, use the
[management sandbox](management-sandbox.md) at
**http://localhost:5175/api/local-management**. Click **Open test administration**,
then open **Question bank → Edit question** to change marks, answer keys, accepted
answers and grading rules. It uses the actual APIs with a separate persistent
test database. Its launcher command and security boundaries are documented in the guide.

For the local design review, enable `VITE_ENABLE_UI_PREVIEW=true` in
`frontend/.env`, run the frontend, and open `http://localhost:5173/preview/admin`.
The current development workspace already enables this flag. Use the sidebar to
review the overview, candidates, exams, questions, subjects and staff history.
Candidate search and status filtering operate on synthetic examples, including an
Urdu name. All write controls are disabled and clearly labeled view only. Nothing
is saved, no session is issued, and no backend request is made. The preview is
excluded from production routing even when its environment flag is true.

For real administration, set the flag to `false`, restart Vite, and use an approved
ADMIN staff account at `/admin`. Provision staff using the existing backend command:

```bash
cd backend
source .venv/bin/activate
python -m app.cli register-staff \
  --email "approved-staff@gmail.com" --name "Staff Member" --role ADMIN
```

Configure staff Google sign-in as described in the root README. Candidate preview,
candidate accounts, proctors and examiners cannot access real administration APIs.

## Recommended workflow

1. **Overview:** check totals and recent activity, then follow the preparation links.
2. **Subjects:** create the configurable subject catalog. Archived subjects remain
   distinguishable from active subjects.
3. **Question bank:** add MCQs and short answers with their existing marking rules.
   The portal points to subject setup when the catalog is empty.
4. **Exams & builder:** create an unpublished exam, set its schedule, add ordered
   subjects and durations, and build each subject paper. Section links make a long
   exam setup page easier to navigate. Existing backend editing locks still apply.
5. **Candidates:** register or import official admission records, review roll number,
   full name and father's name, and assign candidates to their exams. Search, status
   and exam filters retain backend pagination. Clear filters resets the current view.
6. **Publication and starts:** review the exam before publishing it; enabling starts
   remains a separate, confirmed action. Neither overview nor preview starts an exam.
7. **Test day and results:** open monitoring or grading from the overview. Authorized
   staff manage manual grading in its existing workspace; result-release controls
   remain on the exam page and retain backend prerequisites.
8. **Staff actions:** review readable event labels, staff names and timestamps.

## Implementation

`AdminShell.tsx` owns the sidebar, account header, breadcrumb, skip link and footer.
It is a presentation component used by the guarded `AdminLayout` and the separate
`AdminPreviewPage`. `AdminOverviewPage` loads the aggregate endpoint through the
existing typed API client and remote-state hook. Failed loads show a retry action,
with no fabricated zero counts. Existing mutation handlers, CSRF tokens, error
preservation and server permission checks remain in place.

`GET /api/admin/overview` returns total/approved candidates, total/published exams,
total/active questions and subjects, and up to five recent exams and staff actions.
Counts are database aggregates across all records, independent of list pagination.
Published counts exclude archived exams. Four aggregate queries and two bounded
recent-item queries avoid transferring large catalogs. The explicit response
schemas exclude candidate details, question content, keys, answers and credentials.
Staff action responses also include the actor's current display name; existing
user IDs remain in the API. This is an additive API change with **no migration or
new dependency**.

`admin.css` scopes the workspace styling. Desktop layouts use a persistent sidebar,
summary cards and clear form/table groupings. At narrower widths the navigation
reflows, cards stack and tables scroll inside their containers. Buttons retain the
shared reduced-motion-aware press feedback. Status text accompanies color, form
labels remain associated with controls, and quick actions have distinct accessible
names and descriptions. Urdu names use the bundled Arabic-script font fallback.

Form guidance was informed by the
[W3C forms instructions tutorial](https://www.w3.org/WAI/tutorials/forms/instructions/)
and table layout by the
[GOV.UK table component guidance](https://design-system.service.gov.uk/components/table/).
These references informed the design; they are not an accessibility certification.

## Verification and limits

Backend tests check empty totals, counts beyond a 50-row page, active/disabled and
archived records, five-item bounds, response data minimization and role denial.
Frontend tests check overview loads/retries, task links, preview navigation/filtering,
no preview requests or credentials, and development/production flag guards.
Browser workflows cover overview-to-exam creation, the existing candidate/import and
paper-building flows, and unauthorized access. The HTTPS production rehearsal also
opens the real overview and candidate list against its isolated database.

Run checks using the commands in the root README. Design preview cannot validate
real Google configuration, writes, exam timing or operational capacity. Summary
figures refresh on entry or **Refresh overview**; they are not a live proctor feed.
The overview is a preparation aid and does not certify that a paper is ready for
publication. Staff-account creation remains a controlled CLI operation. Production
hosting and a realistic 7,000-candidate rehearsal remain separate deployment work.
