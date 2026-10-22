"""Install reviewed practice content in an existing LOCAL management sandbox only.

No application routes or production authentication changes. Defaults to a dry run.
Run from the repository root with PYTHONPATH=backend and the backend Python venv.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models import (
    AcceptedAnswer,
    AuditEvent,
    ExamQuestion,
    GradingMode,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    Subject,
    User,
)
from app.schemas.exam_domain import MCQWrite, QuestionWrite
from app.services.exam_domain_service import question_response
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

CATALOG_PATH = Path(__file__).parent / "question_banks/cck_class8_practice_v1.json"
QUESTION = TypeAdapter(QuestionWrite)


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,39}$")
    subject_code: str
    topic: str = Field(min_length=1)
    difficulty: Literal["FOUNDATION", "STANDARD", "CHALLENGING"]
    source_pages: list[int] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    question: dict[str, Any]


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack_id: str = Field(pattern=r"^[a-z0-9-]{1,100}$")
    title: str
    version: int = Field(ge=1)
    review_status: str
    copyright_note: str
    sources: list[dict[str, Any]]
    page_map: dict[str, Any]
    subjects: dict[str, str]
    items: list[CatalogItem] = Field(min_length=1)
    retire_examples: list[CatalogItem] = Field(default_factory=list)


def body_for(item: CatalogItem, subject_id: UUID) -> QuestionWrite:
    if "subject_id" in item.question:
        raise ValueError("Catalog questions must use the configured subject mapping.")
    return QUESTION.validate_python({**item.question, "subject_id": subject_id})


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    catalog = Catalog.model_validate_json(path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    prompts: set[tuple[str, str]] = set()
    for item in [*catalog.items, *catalog.retire_examples]:
        if item.key in keys or item.subject_code not in catalog.subjects:
            raise ValueError("Duplicate catalog key or unknown subject mapping.")
        if not all(1 <= page <= 14 for page in item.source_pages):
            raise ValueError("Invalid paper reference.")
        body = body_for(item, UUID(int=0))
        identity = (item.subject_code, body.prompt)
        if identity in prompts:
            raise ValueError("Duplicate question prompt in the catalog.")
        keys.add(item.key)
        prompts.add(identity)
    return catalog


def question_id(catalog: Catalog, item: CatalogItem) -> UUID:
    return uuid5(NAMESPACE_URL, f"cck-original-practice/{catalog.pack_id}/{item.key}")


def signature(body: QuestionWrite) -> dict[str, Any]:
    result = body.model_dump()
    if "accepted_answers" in result:
        result["accepted_answers"] = sorted(result["accepted_answers"])
    return result


def stored_signature(db: Session, question: Question) -> dict[str, Any]:
    response = question_response(db, question)
    value = response.model_dump(
        exclude={"id", "created_at", "updated_at", "options", "grading", "accepted_answers"}
    )
    if response.type == QuestionType.MCQ:
        value["options"] = [
            {"text": option.text, "is_correct": option.is_correct} for option in response.options
        ]
    else:
        value.update(grading=response.grading, accepted_answers=response.accepted_answers)
    return signature(QUESTION.validate_python(value))


def insert_question(db: Session, record_id: UUID, body: QuestionWrite) -> None:
    """Stage validated inserts; the caller owns the single batch transaction."""
    question = Question(
        id=record_id,
        subject_id=body.subject_id,
        type=QuestionType(body.type),
        prompt=body.prompt,
        marks=body.marks,
        direction=body.direction,
        language=body.language,
        is_active=body.is_active,
    )
    if not isinstance(body, MCQWrite):
        question.grading_mode = GradingMode(body.grading.mode)
        question.grading_config = body.grading.model_dump(mode="json")
    db.add(question)
    db.flush()
    if isinstance(body, MCQWrite):
        db.add_all(
            QuestionOption(
                question_id=record_id,
                option_text=option.text,
                display_order=index,
                is_correct=option.is_correct,
            )
            for index, option in enumerate(body.options, 1)
        )
    else:
        db.add_all(
            AcceptedAnswer(
                question_id=record_id,
                grading_mode=body.grading.mode,
                accepted_value=value,
            )
            for value in body.accepted_answers
        )
    db.flush()


def import_catalog(
    db: Session, actor_id: UUID, catalog: Catalog, *, apply: bool = False
) -> dict[str, Any]:
    """Preserve all existing catalog edits; retire only exact, unused demo snapshots."""
    report: dict[str, Any] = {
        "mode": "applied" if apply else "dry_run",
        "pack": catalog.pack_id,
        "create": 0,
        "unchanged": 0,
        "preserved_edits": [],
        "archive_unchanged_examples": 0,
    }
    with db.begin():
        actor = db.get(User, actor_id, with_for_update=True)
        if actor is None or not actor.is_active or actor.role != Role.ADMIN:
            raise ValueError("An active sandbox administrator is required.")
        subjects = {
            subject.code: subject
            for subject in db.scalars(
                select(Subject)
                .where(Subject.code.in_(catalog.subjects))
                .order_by(Subject.id)
                .with_for_update()
            )
        }
        if set(subjects) != set(catalog.subjects) or any(
            not subject.is_active for subject in subjects.values()
        ):
            raise ValueError("All configured sandbox subjects must exist and be active.")
        # Validate every question before staging any inserts/archives.
        bodies = [(item, body_for(item, subjects[item.subject_code].id)) for item in catalog.items]
        examples = [
            body_for(item, subjects[item.subject_code].id) for item in catalog.retire_examples
        ]
        for item, body in bodies:
            record_id = question_id(catalog, item)
            existing = db.get(Question, record_id, with_for_update=True)
            if existing is not None:
                if stored_signature(db, existing) == signature(body):
                    report["unchanged"] += 1
                else:
                    report["preserved_edits"].append(item.key)
                continue
            report["create"] += 1
            if apply:
                insert_question(db, record_id, body)
                db.add(
                    AuditEvent(
                        user_id=actor_id, event_type="QUESTION_BANK_ITEM_ADDED", entity_id=record_id
                    )
                )
        for body in examples:
            matches = list(
                db.scalars(
                    select(Question)
                    .where(
                        Question.subject_id == body.subject_id,
                        Question.prompt == body.prompt,
                        Question.is_active.is_(True),
                    )
                    .order_by(Question.id)
                    .with_for_update()
                )
            )
            for existing in matches:
                assigned = db.scalar(
                    select(ExamQuestion.id).where(ExamQuestion.question_id == existing.id).limit(1)
                )
                if assigned is not None or stored_signature(db, existing) != signature(body):
                    continue
                report["archive_unchanged_examples"] += 1
                if apply:
                    existing.is_active = False
                    db.add(
                        AuditEvent(
                            user_id=actor_id,
                            event_type="QUESTION_BANK_DEMO_ARCHIVED",
                            entity_id=existing.id,
                        )
                    )
        # No exams, assignments, sessions or results are created/modified here.
    return report


def sandbox_target(directory: Path) -> tuple[str, UUID, str]:
    manifest = directory / "sandbox.json"
    if (
        directory.is_symlink()
        or directory.stat().st_mode & 0o077
        or manifest.is_symlink()
        or manifest.stat().st_mode & 0o077
    ):
        raise ValueError("Use the private existing management sandbox directory.")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    url = make_url(value["database_url"])
    if (
        value.get("kind") != "LOCAL_CCK_MANAGEMENT_SANDBOX"
        or url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.query
        or not re.fullmatch(r"cck_management_[a-f0-9]{12}_rehearsal", url.database or "")
    ):
        raise ValueError("This content installer supports isolated localhost sandboxes only.")
    return value["database_url"], UUID(value["administrator_id"]), str(url.database)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("test-results/management-sandbox"))
    parser.add_argument("--apply", action="store_true", help="Commit the planned content changes")
    args = parser.parse_args()
    try:
        catalog = load_catalog()
        database_url, actor_id, expected_name = sandbox_target(args.directory)
        engine = create_engine(
            database_url,
            hide_parameters=True,
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000 -c lock_timeout=5000",
            },
        )
        try:
            with engine.connect() as connection:
                if connection.scalar(text("SELECT current_database()")) != expected_name:
                    raise ValueError("Connected database does not match the sandbox manifest.")
            with Session(engine) as db:
                report = import_catalog(db, actor_id, catalog, apply=args.apply)
        finally:
            engine.dispose()
    except (OSError, ValueError, KeyError, ValidationError, SQLAlchemyError):
        # Never print DSNs, raw SQL parameters, accepted answers or private manifest contents.
        parser.exit(
            1, "Content import failed; check the catalog, local database and sandbox metadata.\n"
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
