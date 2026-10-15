from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.dependencies import Db, require_csrf, require_origin
from app.api.routes.attempts import AdminAuth, CandidateAuth, ServerClock, candidate_id
from app.core.permissions import require_roles
from app.models import CandidateExamAssignment, Exam, ExamAttempt, Role
from app.schemas.attempt import AssignmentWrite
from app.schemas.grading import (
    AttemptResult,
    ExaminerAssignment,
    ExaminerStaff,
    GradeResponse,
    GradingAttempt,
    GradingExam,
    ManualGradeWrite,
    ManualResponse,
)
from app.services import grading_service as service
from app.services.auth_service import AuthContext
from app.services.exam_domain_service import get_record
from app.services.result_service import candidate_result

StaffAuth = Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.EXAMINER))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
mutations = [Depends(require_origin), Depends(require_csrf)]
router = APIRouter(tags=["grading and results"])


@router.get("/admin/examiners", response_model=list[ExaminerStaff])
def staff(db: Db, context: AdminAuth, limit: Limit = 50, offset: Offset = 0) -> list[ExaminerStaff]:
    return service.staff(db, limit, offset)


@router.get("/admin/exams/{exam_id}/examiners", response_model=list[ExaminerAssignment])
def assignments(exam_id: UUID, db: Db, context: AdminAuth) -> list[ExaminerAssignment]:
    return service.assignments(db, exam_id)


@router.put(
    "/admin/exams/{exam_id}/examiners/{user_id}",
    response_model=list[ExaminerAssignment],
    dependencies=mutations,
)
def assign(
    exam_id: UUID, user_id: UUID, body: AssignmentWrite, db: Db, context: AdminAuth
) -> list[ExaminerAssignment]:
    return service.assign(db, exam_id, user_id, body.is_active, context.user.id)


@router.get("/grading/exams", response_model=list[GradingExam])
def exams(db: Db, context: StaffAuth, limit: Limit = 50, offset: Offset = 0) -> list[GradingExam]:
    return service.exams(db, context.user, limit, offset)


@router.get("/grading/exams/{exam_id}/attempts", response_model=list[GradingAttempt])
def attempts(
    exam_id: UUID, db: Db, context: StaffAuth, limit: Limit = 50, offset: Offset = 0
) -> list[GradingAttempt]:
    return service.attempts(db, exam_id, context.user, limit, offset)


@router.get("/grading/exams/{exam_id}/queue", response_model=list[ManualResponse])
def queue(
    exam_id: UUID,
    db: Db,
    context: StaffAuth,
    include_graded: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[ManualResponse]:
    return service.manual_queue(db, exam_id, context.user, include_graded, limit, offset)


@router.get("/grading/answers/{answer_id}/history", response_model=list[GradeResponse])
def history(answer_id: UUID, db: Db, context: StaffAuth) -> list[GradeResponse]:
    return service.history(db, answer_id, context.user)


@router.post(
    "/grading/answers/{answer_id}/grade", response_model=GradeResponse, dependencies=mutations
)
def manual_grade(
    answer_id: UUID, body: ManualGradeWrite, db: Db, context: StaffAuth, clock: ServerClock
) -> GradeResponse:
    return service.manual_grade(db, answer_id, context.user, body, clock)


@router.post("/admin/attempts/{attempt_id}/grade", dependencies=mutations)
def automatic_grade(
    attempt_id: UUID, db: Db, context: AdminAuth, clock: ServerClock
) -> dict[str, int]:
    return {"grades_created": service.grade_attempt(db, attempt_id, context.user, clock)}


@router.get("/candidate/results", response_model=list[AttemptResult])
def results(
    db: Db, context: CandidateAuth, clock: ServerClock, limit: Limit = 50, offset: Offset = 0
) -> list[AttemptResult]:
    rows = list(
        db.scalars(
            select(ExamAttempt)
            .join(CandidateExamAssignment, CandidateExamAssignment.id == ExamAttempt.assignment_id)
            .where(
                ExamAttempt.candidate_id == candidate_id(context),
                CandidateExamAssignment.is_active.is_(True),
            )
            .order_by(ExamAttempt.started_at.desc(), ExamAttempt.id)
            .limit(limit)
            .offset(offset)
        )
    )
    # Serialize publication/withholding with result reads. Acquire multiple exam
    # locks in UUID order so candidates with different exam histories cannot deadlock.
    catalog = {
        exam_id: get_record(db, Exam, exam_id, lock=True)
        for exam_id in sorted({row.exam_id for row in rows})
    }
    now = clock.now(db)
    return [candidate_result(db, row, catalog[row.exam_id], now) for row in rows]
