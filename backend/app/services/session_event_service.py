from datetime import datetime

from sqlalchemy.orm import Session

from app.models import EventSource, ExamAttempt, SessionEvent, SessionEventType, SubjectAttempt


def record_event(
    db: Session,
    attempt: ExamAttempt,
    event_type: SessionEventType,
    now: datetime,
    subject: SubjectAttempt | None = None,
) -> None:
    db.add(
        SessionEvent(
            exam_attempt_id=attempt.id,
            subject_attempt_id=subject.id if subject else None,
            event_type=event_type,
            source=EventSource.SERVER,
            server_timestamp=now,
        )
    )
