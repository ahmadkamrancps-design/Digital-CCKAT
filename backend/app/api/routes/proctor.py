from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Db, require_csrf, require_origin
from app.api.routes.attempts import CandidateAuth, ServerClock, candidate_id
from app.core.permissions import require_roles
from app.models import Role
from app.schemas.attempt import AssignmentWrite
from app.schemas.proctor import (
    MonitoredExam,
    MonitoringResponse,
    PresenceResponse,
    PresenceWrite,
    ProctorAssignmentResponse,
    ProctorStaff,
    SessionEventResponse,
)
from app.services import proctor_service as service
from app.services.auth_service import AuthContext

StaffAuth = Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.PROCTOR))]
AdminAuth = Annotated[AuthContext, Depends(require_roles(Role.ADMIN))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
router = APIRouter(tags=["proctor monitoring"])
mutations = [Depends(require_origin), Depends(require_csrf)]


@router.get("/admin/proctors", response_model=list[ProctorStaff])
def staff(db: Db, context: AdminAuth, limit: Limit = 50, offset: Offset = 0) -> list[ProctorStaff]:
    return service.staff(db, limit, offset)


@router.get("/admin/exams/{exam_id}/proctors", response_model=list[ProctorAssignmentResponse])
def assignments(exam_id: UUID, db: Db, context: AdminAuth) -> list[ProctorAssignmentResponse]:
    return service.assignments(db, exam_id)


@router.put(
    "/admin/exams/{exam_id}/proctors/{user_id}",
    response_model=list[ProctorAssignmentResponse],
    dependencies=mutations,
)
def assign(
    exam_id: UUID, user_id: UUID, body: AssignmentWrite, db: Db, context: AdminAuth
) -> list[ProctorAssignmentResponse]:
    return service.assign(db, exam_id, user_id, body.is_active, context.user.id)


@router.get("/proctor/exams", response_model=list[MonitoredExam])
def exams(db: Db, context: StaffAuth, limit: Limit = 50, offset: Offset = 0) -> list[MonitoredExam]:
    return service.exams(db, context.user, limit, offset)


@router.get("/proctor/exams/{exam_id}/sessions", response_model=MonitoringResponse)
def sessions(
    exam_id: UUID,
    db: Db,
    context: StaffAuth,
    clock: ServerClock,
    limit: Limit = 50,
    offset: Offset = 0,
    search: Annotated[str, Query(max_length=200)] = "",
    active_only: bool = False,
) -> MonitoringResponse:
    return service.sessions(db, exam_id, context.user, clock, limit, offset, search, active_only)


@router.get("/proctor/attempts/{attempt_id}/events", response_model=list[SessionEventResponse])
def events(
    attempt_id: UUID, db: Db, context: StaffAuth, limit: Limit = 50, offset: Offset = 0
) -> list[SessionEventResponse]:
    return service.events(db, attempt_id, context.user, limit, offset)


@router.post(
    "/candidate/attempts/{attempt_id}/presence",
    response_model=PresenceResponse,
    dependencies=mutations,
)
def heartbeat(
    attempt_id: UUID, body: PresenceWrite, db: Db, context: CandidateAuth, clock: ServerClock
) -> PresenceResponse:
    return service.heartbeat(db, attempt_id, candidate_id(context), body, clock)
