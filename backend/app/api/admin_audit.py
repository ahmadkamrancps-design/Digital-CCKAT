from uuid import UUID

from fastapi import Request

from app.api.dependencies import CurrentAuth, Db


def audit_mutation(request: Request, context: CurrentAuth, db: Db) -> None:
    """Attach safe action context; the service commits the event with its mutation."""
    ids = [UUID(str(value)) for value in request.path_params.values()]
    db.info["admin_action"] = (
        context.user.id,
        request.scope["route"].name.upper(),
        ids[-1] if ids else None,
    )
