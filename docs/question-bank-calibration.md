# Class 8 question-bank calibration

## Sources and provenance

Review date: 21 October 2026. CCK's [official download centre](https://www.cck.edu.pk/resources/download_center/)
lists Class 8 past papers and a syllabus. The official
[syllabus address](https://www.cck.edu.pk/web/sites/default/files/2025-06/FSYLLABUS.pdf)
was also found in search results. Direct requests to the official server timed out
or failed, so the review used college-headed scans hosted on a public mirror:

- [Fourteen-page Class 8 paper scan](https://gotest.com.pk/wp-content/uploads/2025/09/cadet-college-kohat-8th-class-papers.pdf):
  all pages read visually, covering the 2020–2023 entries.
- [Two-page syllabus scan](https://gotest.com.pk/wp-content/uploads/2025/09/cadet-college-kohat-SYLLABUS.pdf):
  both pages read visually.

The mirror's identity with the unavailable official download cannot be verified.
The catalog records the reviewed files' SHA-256 hashes and page references. Do not
describe this as verification of the latest official paper or syllabus. The scanned
papers and screenshots are ignored local research artifacts, not distributed assets.

The papers emphasize contextual English grammar and vocabulary, short explanations
and writing; multi-step fraction/algebra/percentage/mensuration problems; and Urdu
grammar, idioms and composition alongside Islamiat. Mathematics is calculator-free.
The reviewed syllabus gives three one-hour, 100-mark papers, with Urdu/Islamiat
split 70/30. These observations guided topic coverage and reasoning demand.

## Original practice content

The private operator catalog is
[`ops/question_banks/cck_class8_practice_v1.json`](../ops/question_banks/cck_class8_practice_v1.json).
It contains **original authored practice**, not copied official questions, an
official mock examination, or CCK-endorsed content. New numerical values, sentences,
contexts and options are used. Essays, long explanations, letters, memorized long
passages and construction drawings are excluded. A few language-production and
construction skills are adapted into brief responses or conceptual MCQs; this
changes what is measured and cannot replicate the full written-paper assessment.

| Bank                                           |   MCQs | Short answers |  Total |
| ---------------------------------------------- | -----: | ------------: | -----: |
| English, including two general-awareness items |     18 |            12 |     30 |
| Mathematics                                    |     15 |            15 |     30 |
| Urdu / Islamiat                                |     20 |            10 |     30 |
| **Total**                                      | **53** |        **37** | **90** |

The third bank has 21 Urdu and nine explicitly prefixed `اسلامیات:` questions,
following the syllabus's content proportions. This is a **question-count split**,
not an automatically constructed 70/30 mark allocation. The existing subject name
stays Urdu; administrators can configure a combined label or separate subjects.
Search `اسلامیات:` to find or omit those items when building a paper.

Each catalog entry records a topic, estimated difficulty, relevant scanned-paper
pages and a private answer rationale or manual marking rubric. Difficulty is
editorial judgment, not a measured equivalence to CCK examinations:

- **FOUNDATION:** a direct fact, rule or one-step operation.
- **STANDARD:** application in context or a familiar calculation with several steps.
- **CHALLENGING:** combined rules, less routine reasoning, algebraic manipulation
  or a brief constructed explanation/transformation.

English and Mathematics each have 6 foundation, 15 standard and 9 challenging
items. The combined Urdu/Islamiat pool has 6 foundation, 21 standard and 3 challenging
items. Language tasks become shorter in this format, and these labels should be
revised after teacher review and a pilot. No claim of equivalent overall exam
difficulty, timing, reliability or complete syllabus coverage is made.

MCQs carry one mark and short answers two marks. These are bank defaults; each
30-question pool is not a complete 100-mark paper. Use the exam builder to select
an appropriate paper and explicitly review marks, workload and timing. No exam
is populated, published, activated or rescheduled by the installer.

## Answer checking and teacher review

The 37 short answers use 14 EXACT, 15 NUMERIC and 8 MANUAL configurations:

- EXACT uses explicit NFC normalization, trimming, whitespace collapsing and
  case-insensitive comparison. It suits constrained words/fills; it does not
  perform spelling correction, synonym matching or Urdu/Arabic letter substitution.
  Accepted alternatives are explicitly listed where needed.
- NUMERIC uses zero tolerance and terminating numeric results. Prompts specify
  number-only input, units and any chosen value of pi. Fractions requiring a
  non-terminating decimal are avoided. The independent calculation checks cover
  all numerical short-answer keys.
- MANUAL handles translation, sentence transformation, interpretation and short
  ethical explanations with multiple valid phrasings. The private catalog includes
  two-mark rubrics and instructions to accept equivalent wording. The application
  does not yet store/show these editorial rubrics in the examiner UI; give assigned
  examiners the relevant catalog rubrics through an authorized staff channel.

**Subject-teacher review is still required before use in an actual examination.**
Review distractors, Urdu conventions, translation alternatives, Islamiat accuracy,
coverage, expected working time and marking consistency. Then run a realistic
pilot and revise using observed difficulty and discrimination. The catalog remains
`DRAFT_REQUIRES_SUBJECT_TEACHER_REVIEW` until that external review takes place.

Keys and editorial notes stay in the operator catalog and backend database.
Nothing is added to frontend assets, static design previews or candidate API schemas.
Existing backend RBAC, safe candidate serialization, examiner permissions and
result-release rules continue to apply.

## Install into the editable local management workspace

Start the existing [management sandbox](management-sandbox.md). From the repository
root, preview the import and then apply it:

```bash
PYTHONPATH=backend backend/.venv/bin/python ops/import_question_bank.py
PYTHONPATH=backend backend/.venv/bin/python ops/import_question_bank.py --apply
```

For another explicitly created sandbox, add `--directory test-results/your-sandbox`.
The installer requires its private manifest, a loopback PostgreSQL sandbox database,
the expected subject codes (`TEST_ENG`, `TEST_MATH`, `TEST_UR`) and an active test
administrator. It checks the connected database name and refuses ordinary/remote
database targets. It adds no public endpoint or production authentication bypass.

The entire import uses one transaction. Deterministic catalog IDs make retries
safe: unchanged records are skipped, staff changes (including archived state) are
reported and preserved. Four original sandbox demo snapshots are archived only
when their full content and marking configuration still match and they are not
assigned to any paper. Records are never deleted. New items and archived demos
receive append-oriented audit events without answer text or keys.

After import, open **http://localhost:5175/api/local-management**, click
**Open test administration**, then **Question bank**. Filter by subject and
**Active**, and use **Edit question** to inspect the keys, marks and grading modes.
The static preview at port 5173 is separate and is not updated by a database import.
The main development database and any production database are also untouched.

## Automated verification

`backend/tests/test_question_bank_content.py` checks catalog validation, coverage,
RTL configuration, real backend grading for every imported item, independent
numeric calculations, dry-run behavior, repeat imports, preservation of staff edits
and assigned demos, interrupted-batch rollback, authorization and target guards.
It runs against the existing SQLite unit-test fixtures or isolated PostgreSQL
schemas with `TEST_DATABASE_URL` configured. The existing suite covers candidate
API key isolation and the rest of the exam lifecycle.
