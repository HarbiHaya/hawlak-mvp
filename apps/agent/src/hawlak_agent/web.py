from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .control import CallControl, CallDispatcher, CallRequest, CallResult
from .settings import AgentSettings


def create_app(settings: AgentSettings, dispatcher: CallDispatcher) -> FastAPI:
    app = FastAPI(title="Hawlak call control", docs_url=None, redoc_url=None)
    control = CallControl(dispatcher)

    def authorize(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {settings.hawlak_control_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.mode}

    @app.post(
        "/calls",
        response_model=CallResult,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(authorize)],
    )
    async def request_call(
        request: CallRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CallResult:
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key is required",
            )
        try:
            return await control.request_call(request, idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return app


def create_app_from_env() -> FastAPI:
    from .control import MockCallDispatcher
    from .dispatch import LiveKitCallDispatcher

    settings = AgentSettings.from_env()
    dispatcher: CallDispatcher
    if settings.mode == "live":
        dispatcher = LiveKitCallDispatcher(agent_name=settings.agent_name)
    else:
        dispatcher = MockCallDispatcher()
    return create_app(settings, dispatcher)
