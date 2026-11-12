import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_factory
from app.models import DeliveryRun, utc_now
from app.services.journey_delivery import (
    JourneyDeliveryOrchestrator,
    build_journey_delivery_adapter,
)

logger = logging.getLogger(__name__)


async def run_once() -> int:
    settings = get_settings()
    adapter = build_journey_delivery_adapter(settings)
    with get_session_factory()() as session:
        case_ids = list(
            session.scalars(
                select(DeliveryRun.case_id)
                .where(
                    DeliveryRun.status.in_(["pending", "claimed"]),
                    DeliveryRun.scheduled_at <= utc_now(),
                )
                .distinct()
            ).all()
        )
        for case_id in case_ids:
            await JourneyDeliveryOrchestrator(session, adapter).dispatch_due(case_id)
        return len(case_ids)


async def run_forever(interval_seconds: int = 10) -> None:
    while True:
        try:
            count = await run_once()
            if count:
                logger.info("Processed due Hawlak delivery cases count=%s", count)
        except Exception:
            logger.exception("Hawlak delivery worker cycle failed")
        await asyncio.sleep(interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
