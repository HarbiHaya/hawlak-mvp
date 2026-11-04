import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import SettingsDep

_bearer = HTTPBearer(auto_error=False)


async def require_internal_access(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    supplied_token = credentials.credentials if credentials is not None else ""
    configured_token = settings.internal_api_token.get_secret_value()
    valid_scheme = credentials is not None and credentials.scheme.lower() == "bearer"
    valid_token = hmac.compare_digest(supplied_token, configured_token)

    if not valid_scheme or not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
