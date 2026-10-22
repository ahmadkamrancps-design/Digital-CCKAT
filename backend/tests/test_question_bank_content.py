import importlib.util
import json
import sys
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import (
    AcceptedAnswer,
    Answer,
    AuditEvent,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamSubject,
    Question,
    Role,
    Subject,
    User,
)
from app.schemas.exam_domain import MCQWrite
from app.services.auto_grading_service import automatic_score
from app.services.exam_domain_service import write_question

specification = importlib.util.spec_from_file_location(
    "import_question_bank", Path(__file__).resolve().parents[2] / "ops/import_question_bank.py"
)
assert specification is not None and specification.loader is not None
bank = importlib.util.module_from_spec(specification)
sys.modules[specification.name] = bank
specification.loader.exec_module(bank)


@pytest.fixture
def seeded(db_factory):
    catalog = bank.load_catalog()
    with db_factory() as db:
        admin = User(display_name="Content test administrator", role=Role.ADMIN)
        subjects = [Subject(code=code, name=name) for code, name in catalog.subjects.items()]
        db.add_all([admin, *subjects])
        db.commit()
        mapping = {subject.code: subject.id for subject in subjects}
        examples = [
            write_question(db, bank.body_for(item, mapping[item.subject_code])).id
            for item in catalog.retire_examples
        ]
        return catalog, admin.id, examples


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_catalog_format_coverage_and_manual_marking_guidance():
    catalog = bank.load_catalog()
    assert len(catalog.items) == 90
    assert Counter(item.subject_code for item in catalog.items) == {
        "TEST_ENG": 30,
        "TEST_MATH": 30,
        "TEST_UR": 30,
    }
    assert sum(item.key.startswith("I") for item in catalog.items) == 9
    bodies = [bank.body_for(item, uuid4()) for item in catalog.items]
    assert Counter(body.type for body in bodies) == {"MCQ": 53, "SHORT_ANSWER": 37}
    assert Counter(body.grading.mode for body in bodies if not isinstance(body, MCQWrite)) == {
        "EXACT": 14,
        "NUMERIC": 15,
        "MANUAL": 8,
    }
    for item, body in zip(catalog.items, bodies, strict=True):
        assert item.topic and item.rationale and item.source_pages
        assert "<script" not in body.prompt.casefold()
        if item.subject_code == "TEST_UR":
            assert body.direction == "rtl" and body.language == "ur"
        if not isinstance(body, MCQWrite) and body.grading.mode == "MANUAL":
            assert not body.accepted_answers
            assert "2 marks" in item.rationale or "۲ نمبر" in item.rationale


def test_import_is_atomic_repeatable_and_does_not_change_exams(db_factory, seeded):
    catalog, admin_id, examples = seeded
    with db_factory() as db:
        exam = Exam(title="Keep this draft", is_published=False)
        db.add(exam)
        db.commit()
        exam_id = exam.id
        plan = bank.import_catalog(db, admin_id, catalog)
        assert plan["create"] == 90 and plan["archive_unchanged_examples"] == 4
        assert count(db, Question) == 4 and count(db, AuditEvent) == 0
        assert all(db.get(Question, record_id).is_active for record_id in examples)
        db.rollback()
        applied = bank.import_catalog(db, admin_id, catalog, apply=True)
        assert applied["create"] == 90 and applied["preserved_edits"] == []
        assert count(db, Question) == 94 and count(db, AuditEvent) == 94
        assert not any(db.get(Question, record_id).is_active for record_id in examples)
        assert count(db, Exam) == 1 and count(db, ExamQuestion) == 0
        assert count(db, ExamAttempt) == 0
        exam = db.get(Exam, exam_id)
        assert not exam.is_published and not exam.is_start_authorized
        db.rollback()
        repeated = bank.import_catalog(db, admin_id, catalog, apply=True)
        assert repeated["create"] == repeated["archive_unchanged_examples"] == 0
        assert repeated["unchanged"] == 90
        assert count(db, Question) == 94 and count(db, AuditEvent) == 94


def test_import_preserves_staff_edits_to_prompts_keys_and_archival(db_factory, seeded):
    catalog, admin_id, _ = seeded
    with db_factory() as db:
        bank.import_catalog(db, admin_id, catalog, apply=True)
        ids = {item.key: bank.question_id(catalog, item) for item in catalog.items}
        db.get(Question, ids["E01"]).prompt = "Staff replacement prompt"
        db.get(Question, ids["U01"]).is_active = False
        key = db.scalar(select(AcceptedAnswer).where(AcceptedAnswer.question_id == ids["M22"]))
        key.accepted_value = "7"
        db.commit()
        report = bank.import_catalog(db, admin_id, catalog, apply=True)
        assert set(report["preserved_edits"]) == {"E01", "U01", "M22"}
        assert report["unchanged"] == 87 and report["create"] == 0
        assert db.get(Question, ids["E01"]).prompt == "Staff replacement prompt"
        assert not db.get(Question, ids["U01"]).is_active
        db.refresh(key)
        assert key.accepted_value == "7"


def test_modified_or_assigned_examples_are_never_archived(db_factory, seeded):
    catalog, admin_id, examples = seeded
    with db_factory() as db:
        first = db.get(Question, examples[0])
        db.get(Question, examples[1]).marks = Decimal("7")
        exam = Exam(title="Existing draft", is_published=False)
        db.add(exam)
        db.flush()
        subject = ExamSubject(
            exam_id=exam.id, subject_id=first.subject_id, duration_minutes=60, sequence=1
        )
        db.add(subject)
        db.flush()
        db.add(
            ExamQuestion(
                exam_subject_id=subject.id,
                subject_id=first.subject_id,
                question_id=first.id,
                sequence=1,
            )
        )
        db.commit()
        report = bank.import_catalog(db, admin_id, catalog, apply=True)
        assert report["archive_unchanged_examples"] == 2
        assert db.get(Question, examples[0]).is_active
        assert db.get(Question, examples[1]).is_active
        assert count(db, ExamQuestion) == 1


def test_interrupted_batch_rolls_back_questions_and_audit(db_factory, seeded, monkeypatch):
    catalog, admin_id, examples = seeded
    original = bank.insert_question
    staged = 0

    def interrupt(db, record_id, body):
        nonlocal staged
        original(db, record_id, body)
        staged += 1
        if staged == 3:
            raise RuntimeError("Simulated interrupted batch")

    monkeypatch.setattr(bank, "insert_question", interrupt)
    with db_factory() as db:
        with pytest.raises(RuntimeError, match="interrupted"):
            bank.import_catalog(db, admin_id, catalog, apply=True)
        assert count(db, Question) == 4 and count(db, AuditEvent) == 0
        assert all(db.get(Question, record_id).is_active for record_id in examples)


@pytest.mark.parametrize(
    ("role", "active"),
    [(Role.CANDIDATE, True), (Role.PROCTOR, True), (Role.EXAMINER, True), (Role.ADMIN, False)],
)
def test_import_requires_active_administrator(db_factory, seeded, role, active):
    catalog, admin_id, _ = seeded
    with db_factory() as db:
        actor = db.get(User, admin_id)
        actor.role, actor.is_active = role, active
        db.commit()
        with pytest.raises(ValueError, match="active sandbox administrator"):
            bank.import_catalog(db, admin_id, catalog, apply=True)
        assert count(db, Question) == 4 and count(db, AuditEvent) == 0


def test_missing_subject_aborts_before_writes(db_factory, seeded):
    catalog, admin_id, _ = seeded
    with db_factory() as db:
        subject = db.scalar(select(Subject).where(Subject.code == "TEST_UR"))
        subject.is_active = False
        db.commit()
        with pytest.raises(ValueError, match="must exist and be active"):
            bank.import_catalog(db, admin_id, catalog, apply=True)
        assert count(db, Question) == 4


def test_imported_keys_work_with_real_backend_grader(db_factory, seeded):
    catalog, admin_id, _ = seeded
    with db_factory() as db:
        bank.import_catalog(db, admin_id, catalog, apply=True)
        for item in catalog.items:
            question = db.get(Question, bank.question_id(catalog, item))
            response = bank.question_response(db, question)
            answer = Answer()
            if question.type == "MCQ":
                keys = [option.id for option in response.options if option.is_correct]
                assert len(keys) == 1
                for option in response.options:
                    answer.selected_option_id = option.id
                    assert automatic_score(answer, question, keys, []) == (
                        option.is_correct,
                        "MCQ",
                    ), item.key
            elif question.grading_mode == "MANUAL":
                answer.short_answer_text = "A response for examiner review"
                assert automatic_score(answer, question, [], []) is None, item.key
            else:
                for value in response.accepted_answers:
                    answer.short_answer_text = "  " + value.upper() + "  "
                    assert automatic_score(answer, question, [], response.accepted_answers) == (
                        True,
                        str(question.grading_mode),
                    ), item.key
                answer.short_answer_text = (
                    "999999999" if question.grading_mode == "NUMERIC" else "___wrong___"
                )
                assert automatic_score(answer, question, [], response.accepted_answers) == (
                    False,
                    str(question.grading_mode),
                ), item.key


def test_multi_step_mathematics_keys_against_independent_calculations():
    catalog = bank.load_catalog()
    questions = {item.key: item.question for item in catalog.items}
    expected = {
        "M16": Fraction(125, 100) / Fraction(5, 100) - 3 * Fraction(2, 3),
        "M17": 36,
        "M18": 5 * 18 - sum([12, 16, 19, 21]),
        "M19": Fraction(75, 360) * 120,
        "M20": (103 - 97) * (103 + 97),
        "M21": Fraction(5, 7) * 840,
        "M22": (Fraction(9, 4) - Fraction(5, 6)) / Fraction(7, 12) + Fraction(1, 14),
        "M23": 4,
        "M24": Fraction(2800 * 100, 112),
        "M25": (2 * 3**3 - 3 * 3**2 - 8 * 3 + 12) / (3 - 2),
        "M26": Fraction(22, 7) * 7**2 * 18,
        "M27": Fraction(22, 7) * 35**2 * 80 / 1000,
        "M28": 8,
        "M29": 9 * (9 + 5),
        "M30": 99 * Fraction(6, 11),
    }
    for key, value in expected.items():
        assert Fraction(questions[key]["accepted_answers"][0]) == value, key
    x = Fraction(questions["M23"]["accepted_answers"][0])
    assert (3 * x - 2) / 4 - (x + 1) / 6 == Fraction(5, 3)
    son = int(questions["M28"]["accepted_answers"][0])
    assert 3 * son + 8 == 2 * (son + 8)
    a = int(questions["M30"]["accepted_answers"][0])
    assert Fraction(2, 3) * a == Fraction(4, 5) * (99 - a)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://local:local@localhost/cck_digital_test",
        "postgresql+psycopg://local:local@external.example/cck_management_012345abcdef_rehearsal",
        "postgresql+psycopg://local:local@localhost/cck_management_012345abcdef_rehearsal?host=external.example",
    ],
)
def test_installer_rejects_regular_remote_and_overridden_targets(tmp_path, database_url):
    tmp_path.chmod(0o700)
    manifest = tmp_path / "sandbox.json"
    manifest.write_text(
        json.dumps(
            {
                "kind": "LOCAL_CCK_MANAGEMENT_SANDBOX",
                "database_url": database_url,
                "administrator_id": str(uuid4()),
            }
        )
    )
    manifest.chmod(0o600)
    with pytest.raises(ValueError, match="isolated localhost"):
        bank.sandbox_target(tmp_path)
