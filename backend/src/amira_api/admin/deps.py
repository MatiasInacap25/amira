from typing import Annotated

from fastapi import Depends, HTTPException

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.settings import Settings, get_settings


def require_admin(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    if current_user.id not in settings.admin_user_ids:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
