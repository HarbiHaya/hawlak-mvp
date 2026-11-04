from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionDep

router = APIRouter()


@router.get("/health")
def health(response: Response, session: SessionDep) -> dict[str, str]:
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return {
            "status": "degraded",
            "service": "hawlak-api",
            "time": now,
            "database": "unavailable",
        }
    return {"status": "ok", "service": "hawlak-api", "time": now, "database": "ok"}
