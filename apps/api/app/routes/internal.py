from fastapi import APIRouter, Depends

from app.routes import (
    care_journeys,
    cases,
    demo,
    inbound,
    journey_delivery,
    reminders,
    review_events,
    voice,
)
from app.security import require_internal_access

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal_access)])
router.include_router(care_journeys.router)
router.include_router(cases.router)
router.include_router(demo.router)
router.include_router(inbound.router)
router.include_router(journey_delivery.router)
router.include_router(reminders.router)
router.include_router(review_events.router)
router.include_router(voice.router)
