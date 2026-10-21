from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Db, require_csrf, require_origin
from app.core.permissions import require_roles
from app.models import CandidateStatus, Role
from app.schemas.admin_management import (
    AdminOverview,
    CandidateImport,
    CandidateResponse,
    CandidateWrite,
    PublicationWrite,
    ReleaseWrite,
    StaffActionResponse,
)
from app.schemas.attempt import AssignmentResponse
from app.schemas.exam_domain import ExamResponse
from app.services import admin_management_service as service
from app.services.auth_service import AuthContext

AdminAuth = Annotated[AuthContext, Depends(require_roles(Role.ADMIN))]
router = APIRouter(
    prefix="/admin", tags=["admin management"], dependencies=[Depends(require_roles(Role.ADMIN))]
)
mutations = [Depends(require_origin), Depends(require_csrf)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/overview", response_model=AdminOverview)
def overview(db: Db) -> AdminOverview:
    return service.overview(db)


@router.get("/candidates", response_model=list[CandidateResponse])
def candidates(
    db: Db,
    limit: Limit = 50,
    offset: Offset = 0,
    search: Annotated[str, Query(max_length=200)] = "",
    status: CandidateStatus | None = None,
    exam_id: UUID | None = None,
) -> list[CandidateResponse]:
    return service.list_candidates(db, limit, offset, search, status, exam_id)


@router.post(
    "/candidates", response_model=CandidateResponse, status_code=201, dependencies=mutations
)
def create_candidate(body: CandidateWrite, db: Db, context: AdminAuth) -> CandidateResponse:
    return service.write_candidate(db, body, context.user.id)


@router.post(
    "/candidates/import",
    response_model=list[CandidateResponse],
    status_code=201,
    dependencies=mutations,
)
def import_candidates(body: CandidateImport, db: Db, context: AdminAuth) -> list[CandidateResponse]:
    return service.import_candidates(db, body.candidates, context.user.id)


@router.put("/candidates/{candidate_id}", response_model=CandidateResponse, dependencies=mutations)
def update_candidate(
    candidate_id: UUID, body: CandidateWrite, db: Db, context: AdminAuth
) -> CandidateResponse:
    return service.write_candidate(db, body, context.user.id, candidate_id)


@router.get("/candidates/{candidate_id}/assignments", response_model=list[AssignmentResponse])
def assignments(candidate_id: UUID, db: Db) -> list[AssignmentResponse]:
    return service.assignments(db, candidate_id)


@router.post("/exams/{exam_id}/publication", response_model=ExamResponse, dependencies=mutations)
def publication(exam_id: UUID, body: PublicationWrite, db: Db, context: AdminAuth) -> ExamResponse:
    return service.publish_exam(db, exam_id, body.published, context.user.id)


@router.post("/exams/{exam_id}/result-release", response_model=ExamResponse, dependencies=mutations)
def release(exam_id: UUID, body: ReleaseWrite, db: Db, context: AdminAuth) -> ExamResponse:
    return service.release_results(
        db, exam_id, body.released, context.user.id, body.result_release_at
    )


@router.get("/actions", response_model=list[StaffActionResponse])
def actions(db: Db, limit: Limit = 50, offset: Offset = 0) -> list[StaffActionResponse]:
    return service.actions(db, limit, offset)
