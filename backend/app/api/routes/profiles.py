from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentAuth
from app.core.permissions import require_roles
from app.models import Role
from app.schemas.auth import MeResponse
from app.services.auth_service import AuthContext, profile

router = APIRouter(tags=["profiles"])


@router.get("/me", response_model=MeResponse)
def me(context: CurrentAuth) -> MeResponse:
    return profile(context)


@router.get("/candidate/me", response_model=MeResponse)
def candidate_me(
    context: Annotated[AuthContext, Depends(require_roles(Role.CANDIDATE))],
) -> MeResponse:
    return profile(context)
