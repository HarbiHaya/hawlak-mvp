import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from hmac import compare_digest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.routes import auth, health, internal, storage, twilio_webhook, whatsapp_webhook
from app.services.whatsapp_client import MetaApiError, WhatsAppApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()  # fail fast on a bad .env instead of on the first request
    application.state.dashboard_origin = settings.dashboard_origin
    yield


class ExactDashboardCORSMiddleware(CORSMiddleware):
    """Allow browser calls only from the configured local demo origin."""

    def __init__(self, app: ASGIApp, *, origin_provider: Callable[[], str]) -> None:
        self._origin_provider = origin_provider
        super().__init__(
            app,
            allow_origins=[],
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            allow_credentials=False,
        )

    def is_allowed_origin(self, origin: str) -> bool:
        return compare_digest(origin, self._origin_provider())


app = FastAPI(title="Hawlak API", lifespan=lifespan)
app.add_middleware(
    ExactDashboardCORSMiddleware,
    origin_provider=lambda: app.state.dashboard_origin,
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(storage.router)
app.include_router(whatsapp_webhook.router)
app.include_router(twilio_webhook.router)
app.include_router(internal.router)


@app.exception_handler(WhatsAppApiError)
async def whatsapp_api_error(_: Request, exc: WhatsAppApiError) -> JSONResponse:
    error = "meta_api_error" if isinstance(exc, MetaApiError) else "whatsapp_api_error"
    return JSONResponse(
        status_code=502,
        content={"error": error, "message": str(exc)},
    )
