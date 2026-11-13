import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import SettingsDep
from app.demo_auth import AccessContext, verify_demo_session

_bearer = HTTPBearer(auto_error=False)


async def require_internal_access(
    request: Request,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AccessContext:
    supplied_token = credentials.credentials if credentials is not None else ""
    configured_token = settings.internal_api_token.get_secret_value()
    valid_scheme = credentials is not None and credentials.scheme.lower() == "bearer"
    valid_token = hmac.compare_digest(supplied_token, configured_token)

    if valid_scheme and valid_token:
        return AccessContext(username="service", role="service")

    session = verify_demo_session(settings, supplied_token) if valid_scheme else None
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    allowed_roles = _dashboard_roles(request.method, request.url.path)
    if session.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return session


def _dashboard_roles(method: str, path: str) -> set[str]:
    admin = {"admin"}
    if path == "/internal/voice-options" and method == "GET":
        return admin | {"hospital", "insurer"}
    if path == "/internal/workspace/documents" and method == "POST":
        return admin | {"hospital"}
    if path == "/internal/workspace/cases":
        return admin | ({"hospital"} if method == "POST" else {"insurer"})
    if path == "/internal/workspace/analytics" and method == "GET":
        return admin | {"insurer"}
    if path == "/internal/hospital/cases" and method == "GET":
        return admin | {"hospital"}
    if path == "/internal/workspace/alerts" and method == "GET":
        return admin | {"insurer"}
    if path.startswith("/internal/workspace/alerts/") and path.endswith("/resolve"):
        return admin | {"insurer"} if method == "POST" else set()
    if path.startswith("/internal/workspace/cases/"):
        return admin | {"insurer"}
    if path.startswith("/internal/caregiver/cases/") and method == "GET":
        return admin | {"caregiver"}
    # Medicine photos come from the patient's side only: the caregiver, never the insurer.
    if path.startswith("/internal/caregiver/cases/") and path.endswith("/photo"):
        return admin | {"caregiver"} if method == "POST" else set()
    return set()
