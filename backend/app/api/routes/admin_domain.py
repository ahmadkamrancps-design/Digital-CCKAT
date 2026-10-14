from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.admin_audit import audit_mutation
from app.api.dependencies import Db, require_csrf, require_origin
from app.core.permissions import require_roles
from app.models import Exam, Question, QuestionType, Role
from app.schemas.exam_domain import (
    AdminQuestionResponse,
    ExamResponse,
    ExamSubjectResponse,
    ExamSubjectWrite,
    ExamWrite,
    PaperResponse,
    PaperWrite,
    QuestionWrite,
    SubjectOrderWrite,
    SubjectResponse,
    SubjectWrite,
)
from app.services import exam_domain_service as service

router = APIRouter(
    prefix="/admin", tags=["admin exam domain"], dependencies=[Depends(require_roles(Role.ADMIN))]
)
mutations = [Depends(require_origin), Depends(require_csrf), Depends(audit_mutation)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/subjects", response_model=list[SubjectResponse])
def subjects(db: Db, limit: Limit = 50, offset: Offset = 0) -> list[SubjectResponse]:
    return service.list_subjects(db, limit, offset)


@router.post("/subjects", response_model=SubjectResponse, status_code=201, dependencies=mutations)
def create_subject(body: SubjectWrite, db: Db) -> SubjectResponse:
    return service.write_subject(db, body)


@router.put("/subjects/{subject_id}", response_model=SubjectResponse, dependencies=mutations)
def update_subject(subject_id: UUID, body: SubjectWrite, db: Db) -> SubjectResponse:
    return service.write_subject(db, body, subject_id)


@router.get("/exams", response_model=list[ExamResponse])
def exams(
    db: Db,
    limit: Limit = 50,
    offset: Offset = 0,
    search: Annotated[str, Query(max_length=200)] = "",
) -> list[ExamResponse]:
    return service.list_exams(db, limit, offset, search)


@router.get("/exams/{exam_id}", response_model=ExamResponse)
def exam(exam_id: UUID, db: Db) -> ExamResponse:
    return service.exam_response(service.get_record(db, Exam, exam_id), db)


@router.post("/exams", response_model=ExamResponse, status_code=201, dependencies=mutations)
def create_exam(body: ExamWrite, db: Db) -> ExamResponse:
    return service.write_exam(db, body)


@router.put("/exams/{exam_id}", response_model=ExamResponse, dependencies=mutations)
def update_exam(exam_id: UUID, body: ExamWrite, db: Db) -> ExamResponse:
    return service.write_exam(db, body, exam_id)


@router.get("/exams/{exam_id}/subjects", response_model=list[ExamSubjectResponse])
def exam_subjects(exam_id: UUID, db: Db) -> list[ExamSubjectResponse]:
    return service.list_exam_subjects(db, exam_id)


@router.put(
    "/exams/{exam_id}/subject-order",
    response_model=list[ExamSubjectResponse],
    dependencies=mutations,
)
def reorder_subjects(exam_id: UUID, body: SubjectOrderWrite, db: Db) -> list[ExamSubjectResponse]:
    return service.reorder_subjects(db, exam_id, body.subject_ids)


@router.post(
    "/exams/{exam_id}/subjects",
    response_model=ExamSubjectResponse,
    status_code=201,
    dependencies=mutations,
)
def create_exam_subject(exam_id: UUID, body: ExamSubjectWrite, db: Db) -> ExamSubjectResponse:
    return service.write_exam_subject(db, exam_id, body)


@router.put(
    "/exams/{exam_id}/subjects/{exam_subject_id}",
    response_model=ExamSubjectResponse,
    dependencies=mutations,
)
def update_exam_subject(
    exam_id: UUID, exam_subject_id: UUID, body: ExamSubjectWrite, db: Db
) -> ExamSubjectResponse:
    return service.write_exam_subject(db, exam_id, body, exam_subject_id)


@router.delete(
    "/exams/{exam_id}/subjects/{exam_subject_id}", status_code=204, dependencies=mutations
)
def remove_exam_subject(exam_id: UUID, exam_subject_id: UUID, db: Db) -> None:
    service.remove_exam_subject(db, exam_id, exam_subject_id)


@router.get("/questions", response_model=list[AdminQuestionResponse])
def questions(
    db: Db,
    limit: Limit = 50,
    offset: Offset = 0,
    subject_id: UUID | None = None,
    question_type: QuestionType | None = None,
    search: Annotated[str, Query(max_length=200)] = "",
    is_active: bool | None = None,
) -> list[AdminQuestionResponse]:
    return service.list_questions(db, limit, offset, subject_id, question_type, search, is_active)


@router.get("/questions/{question_id}", response_model=AdminQuestionResponse)
def question(question_id: UUID, db: Db) -> AdminQuestionResponse:
    return service.question_response(db, service.get_record(db, Question, question_id))


@router.post(
    "/questions", response_model=AdminQuestionResponse, status_code=201, dependencies=mutations
)
def create_question(body: QuestionWrite, db: Db) -> AdminQuestionResponse:
    return service.write_question(db, body)


@router.put(
    "/questions/{question_id}", response_model=AdminQuestionResponse, dependencies=mutations
)
def update_question(question_id: UUID, body: QuestionWrite, db: Db) -> AdminQuestionResponse:
    return service.write_question(db, body, question_id)


@router.post(
    "/questions/{question_id}/archive", response_model=AdminQuestionResponse, dependencies=mutations
)
def archive_question(question_id: UUID, db: Db) -> AdminQuestionResponse:
    return service.archive_question(db, question_id)


@router.get("/exam-subjects/{exam_subject_id}/questions", response_model=PaperResponse)
def paper(exam_subject_id: UUID, db: Db) -> PaperResponse:
    return service.paper_response(db, exam_subject_id)


@router.put(
    "/exam-subjects/{exam_subject_id}/questions",
    response_model=PaperResponse,
    dependencies=mutations,
)
def replace_paper(exam_subject_id: UUID, body: PaperWrite, db: Db) -> PaperResponse:
    return service.replace_paper(db, exam_subject_id, body)
