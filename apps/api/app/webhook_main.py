"""Public, webhook-only ASGI app for the Meta WhatsApp callback.

Run this app behind a temporary tunnel during local development. Keeping it
separate prevents internal demo and storage routes from being published.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config import get_settings
from app.routes import twilio_webhook, whatsapp_webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings_provider = application.dependency_overrides.get(get_settings, get_settings)
    settings_provider()
    yield


app = FastAPI(title="Hawlak WhatsApp Webhook", lifespan=lifespan)
app.include_router(whatsapp_webhook.router)
app.include_router(twilio_webhook.router)


@app.middleware("http")
async def safe_access_log(request: Request, call_next):
    """Log reachability without query strings, headers, or payload contents."""
    response = await call_next(request)
    logger.info(
        "Public webhook request method=%s path=%s status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response
