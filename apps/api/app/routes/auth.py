from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import SettingsDep
from app.demo_auth import LoginRequest, authenticate_demo_user

router = APIRouter(prefix="/auth", tags=["demo-auth"])


@router.post("/login")
def login(body: LoginRequest, settings: SettingsDep):
    session = authenticate_demo_user(settings, body.username, body.password)
    if session is None:
        return JSONResponse(status_code=401, content={"error": "invalid_credentials"})
    return session.model_dump(mode="json", by_alias=True)
