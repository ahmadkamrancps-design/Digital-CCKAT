from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import Db, require_csrf, require_origin
from app.core.clock import Clock
from app.core.permissions import require_roles
from app.models import Role
from app.schemas.attempt import (
    AnswerSaveResponse,
    AnswerWrite,
    AssignedExamResponse,
    AssignmentResponse,
    AssignmentWrite,
    AttemptResponse,
    StartAuthorizationResponse,
    StartAuthorizationWrite,
    SubjectPaperResponse,
)
from app.services import attempt_service as service
from app.services.auth_service import AuthContext


def get_clock(request: Request) -> Clock:
    return request.app.state.clock  # type: ignore[no-any-return]


ServerClock = Annotated[Clock, Depends(get_clock)]
CandidateAuth = Annotated[AuthContext, Depends(require_roles(Role.CANDIDATE))]
AdminAuth = Annotated[AuthContext, Depends(require_roles(Role.ADMIN))]
mutations = [Depends(require_origin), Depends(require_csrf)]
router = APIRouter(prefix="/candidate", tags=["candidate attempts"])
admin_router = APIRouter(prefix="/admin", tags=["admin attempt access"])


def candidate_id(context: AuthContext) -> UUID:
    assert context.candidate is not None  # Authentication dependency enforces registration.
    return context.candidate.id


@admin_router.put(
    "/exams/{exam_id}/candidates/{candidate_id}",
    response_model=AssignmentResponse,
    dependencies=mutations,
)
def assign(
    exam_id: UUID, candidate_id: UUID, body: AssignmentWrite, db: Db, context: AdminAuth
) -> AssignmentResponse:
    return service.assign_candidate(db, exam_id, candidate_id, context.user.id, body.is_active)


@admin_router.post(
    "/exams/{exam_id}/start-authorization",
    response_model=StartAuthorizationResponse,
    dependencies=mutations,
)
def authorize(
    exam_id: UUID, body: StartAuthorizationWrite, db: Db, context: AdminAuth
) -> StartAuthorizationResponse:
    return service.authorize_start(db, exam_id, body.authorized)


@router.get("/exams", response_model=list[AssignedExamResponse])
def exams(db: Db, context: CandidateAuth) -> list[AssignedExamResponse]:
    return service.assigned_exams(db, candidate_id(context))


@router.post("/exams/{exam_id}/attempt", response_model=AttemptResponse, dependencies=mutations)
def begin_exam(
    exam_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock
) -> AttemptResponse:
    return service.begin_exam(db, exam_id, candidate_id(context), clock)


@router.get("/attempts/{attempt_id}", response_model=AttemptResponse)
def resume(attempt_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock) -> AttemptResponse:
    return service.resume_exam(db, attempt_id, candidate_id(context), clock)


@router.post(
    "/attempts/{attempt_id}/subjects/{subject_id}/start",
    response_model=AttemptResponse,
    dependencies=mutations,
)
def begin_subject(
    attempt_id: UUID, subject_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock
) -> AttemptResponse:
    return service.begin_subject(db, attempt_id, subject_id, candidate_id(context), clock)


@router.get(
    "/attempts/{attempt_id}/subjects/{subject_id}/questions", response_model=SubjectPaperResponse
)
def paper(
    attempt_id: UUID, subject_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock
) -> SubjectPaperResponse:
    return service.subject_paper(db, attempt_id, subject_id, candidate_id(context), clock)


@router.put(
    "/attempts/{attempt_id}/subjects/{subject_id}/answers/{exam_question_id}",
    response_model=AnswerSaveResponse,
    dependencies=mutations,
)
def save(
    attempt_id: UUID,
    subject_id: UUID,
    exam_question_id: UUID,
    body: AnswerWrite,
    db: Db,
    context: CandidateAuth,
    clock: ServerClock,
) -> AnswerSaveResponse:
    return service.save_answer(
        db, attempt_id, subject_id, exam_question_id, candidate_id(context), body, clock
    )


@router.post(
    "/attempts/{attempt_id}/subjects/{subject_id}/submit",
    response_model=AttemptResponse,
    dependencies=mutations,
)
def submit_subject(
    attempt_id: UUID, subject_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock
) -> AttemptResponse:
    return service.submit_subject(db, attempt_id, subject_id, candidate_id(context), clock)


@router.post(
    "/attempts/{attempt_id}/submit", response_model=AttemptResponse, dependencies=mutations
)
def submit_exam(
    attempt_id: UUID, db: Db, context: CandidateAuth, clock: ServerClock
) -> AttemptResponse:
    return service.submit_exam(db, attempt_id, candidate_id(context), clock)
