"""Synthetic data for a dedicated *_rehearsal database. Never seeds a live database."""

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import load_settings
from app.core.clock import DatabaseClock
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AcceptedAnswer,
    Candidate,
    CandidateExamAssignment,
    Exam,
    ExamQuestion,
    ExamSubject,
    GradingMode,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    Subject,
    User,
)
from app.services.attempt_service import authorize_start, begin_exam, begin_subject
from app.services.auth_service import issue_session, profile


def seed(db: Session, count: int, duration: int, output: Path) -> None:
    name = db.scalar(text("SELECT current_database()"))
    if not isinstance(name, str) or not name.endswith("_rehearsal"):
        raise ValueError("Synthetic seeding requires a dedicated database ending in _rehearsal.")
    if db.scalar(select(func.count()).select_from(User)) or db.scalar(
        select(func.count()).select_from(Exam)
    ):
        raise ValueError("Rehearsal database must have no users or exams.")
    if output.exists():
        raise ValueError("Manifest already exists; refusing to overwrite it.")
    settings = load_settings()
    admin = User(
        display_name="REHEARSAL Administrator",
        email="rehearsal-admin@example.invalid",
        role=Role.ADMIN,
    )
    exam = Exam(
        title="REHEARSAL CCK Class 8 Mock Examination",
        description="Synthetic data only; not an official admission test.",
    )
    db.add_all([admin, exam])
    db.flush()
    for sequence, (label, language, mode, accepted) in enumerate(
        [
            ("English", "en", GradingMode.EXACT, "light"),
            ("Mathematics", "en", GradingMode.NUMERIC, "3"),
            ("Urdu", "ur", GradingMode.MANUAL, None),
        ],
        1,
    ):
        subject = Subject(name=label, code=f"REHEARSAL_{sequence}")
        db.add(subject)
        db.flush()
        paper = ExamSubject(
            exam_id=exam.id, subject_id=subject.id, sequence=sequence, duration_minutes=duration
        )
        db.add(paper)
        db.flush()
        for number in range(1, 31):
            mcq = number % 2 == 1
            question = Question(
                subject_id=subject.id,
                type=QuestionType.MCQ if mcq else QuestionType.SHORT_ANSWER,
                prompt=("درست جواب منتخب کریں۔" if mcq else "مختصر جواب لکھیں۔")
                if language == "ur"
                else (
                    "Select the correct answer."
                    if mcq
                    else "Find x: 3(x + 5) = 24."
                    if label == "Mathematics"
                    else "Complete: From darkness unto _____."
                ),
                direction="rtl" if language == "ur" else "ltr",
                language=language,
                marks=Decimal("1"),
                grading_mode=None if mcq else mode,
                grading_config=None if mcq else {"mode": mode.value},
            )
            db.add(question)
            db.flush()
            if mcq:
                for order, value in enumerate(
                    (
                        ["کتاب", "درخت"]
                        if language == "ur"
                        else ["60", "45"]
                        if label == "Mathematics"
                        else ["light", "darkness"]
                    ),
                    1,
                ):
                    db.add(
                        QuestionOption(
                            question_id=question.id,
                            option_text=value,
                            display_order=order,
                            is_correct=order == 1,
                        )
                    )
            elif accepted is not None:
                db.add(
                    AcceptedAnswer(
                        question_id=question.id, grading_mode=mode.value, accepted_value=accepted
                    )
                )
            db.add(
                ExamQuestion(
                    exam_subject_id=paper.id,
                    subject_id=subject.id,
                    question_id=question.id,
                    sequence=number,
                )
            )
    credentials = []
    for number in range(count):
        user = User(display_name=f"REHEARSAL Candidate {number:05d}", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        candidate = Candidate(
            user_id=user.id,
            roll_number=f"REHEARSAL-{number:05d}",
            full_name=user.display_name,
            father_name=f"REHEARSAL Father {number:05d}",
        )
        db.add(candidate)
        db.flush()
        db.add(
            CandidateExamAssignment(
                candidate_id=candidate.id, exam_id=exam.id, assigned_by=admin.id, is_active=True
            )
        )
        credentials.append(
            {
                "roll_number": candidate.roll_number,
                "full_name": candidate.full_name,
                "father_name": candidate.father_name,
            }
        )
    db.commit()
    authorize_start(db, exam.id, True)
    # A reserved account leaves a one-minute paper unattended. Verification reads
    # storage directly, so an API request cannot accidentally perform the expiry.
    probe = Exam(title="REHEARSAL unattended expiry probe")
    db.add(probe)
    db.flush()
    first_question = db.scalar(select(Question).where(Question.type == QuestionType.MCQ))
    reserved = db.scalar(select(Candidate).where(Candidate.roll_number == "REHEARSAL-00001"))
    assert first_question is not None and reserved is not None
    probe_paper = ExamSubject(
        exam_id=probe.id,
        subject_id=first_question.subject_id,
        sequence=1,
        duration_minutes=1,
    )
    db.add(probe_paper)
    db.flush()
    db.add_all(
        [
            ExamQuestion(
                exam_subject_id=probe_paper.id,
                subject_id=first_question.subject_id,
                question_id=first_question.id,
                sequence=1,
            ),
            CandidateExamAssignment(
                candidate_id=reserved.id, exam_id=probe.id, assigned_by=admin.id, is_active=True
            ),
        ]
    )
    db.commit()
    authorize_start(db, probe.id, True)
    opened = begin_exam(db, probe.id, reserved.id, DatabaseClock())
    begin_subject(db, opened.id, opened.subjects[0].id, reserved.id, DatabaseClock())
    # Operator-only synthetic admin session; no authentication bypass endpoint exists.
    actor = db.scalar(select(User).where(User.id == admin.id).with_for_update())
    assert actor is not None
    context, token = issue_session(db, actor, None, settings)
    manifest = {
        "kind": "CCK_REHEARSAL_ONLY",
        "origin": settings.frontend_origin,
        "exam_id": str(exam.id),
        "expiry_subject_id": str(opened.subjects[0].id),
        "candidates": credentials,
        "admin": {"cookie": token, "profile": profile(context).model_dump(mode="json")},
    }
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with output.open("x") as stream:
        output.chmod(0o600)
        json.dump(manifest, stream, ensure_ascii=False)
    print(
        f"Synthetic rehearsal prepared: {count} candidates, 3 subjects, 90 questions. "
        "Manifest written securely."
    )


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Seed an empty dedicated CCK rehearsal database")
    parser.add_argument("--candidates", type=int, default=22)
    parser.add_argument("--duration-minutes", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.candidates <= 10002 or not 1 <= args.duration_minutes <= 60:
        parser.error("Use 3..10002 candidates and 1..60 minute subjects.")
    engine = create_db_engine(load_settings())
    try:
        with create_session_factory(engine)() as db:
            seed(db, args.candidates, args.duration_minutes, args.output)
    except Exception as error:
        # Trusted tool still avoids echoing credentials/SQL/answer configuration.
        parser.exit(
            1,
            f"Rehearsal preparation failed: {type(error).__name__}. "
            "Use a fresh *_rehearsal database.\n",
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
