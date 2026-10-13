from collections.abc import Callable

from fastapi import HTTPException

from app.api.dependencies import CurrentAuth
from app.models import Role
from app.services.auth_service import AuthContext


def require_roles(*roles: Role) -> Callable[..., AuthContext]:
    def check(context: CurrentAuth) -> AuthContext:
        if context.user.role not in roles:
            raise HTTPException(403, "You do not have permission to access this resource.")
        return context

    return check
