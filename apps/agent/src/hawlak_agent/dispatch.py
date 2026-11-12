from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from .control import DispatchReceipt


def _livekit_api_factory() -> Any:
    from livekit import api

    return api.LiveKitAPI()


def _livekit_request_factory(**values: Any) -> Any:
    from livekit import api

    return api.CreateAgentDispatchRequest(**values)


class LiveKitCallDispatcher:
    """Starts one named worker; the worker fetches phone data from Hawlak."""

    def __init__(
        self,
        *,
        agent_name: str,
        api_factory: Callable[[], Any] = _livekit_api_factory,
        request_factory: Callable[..., Any] = _livekit_request_factory,
    ) -> None:
        if not agent_name:
            raise ValueError("HAWLAK_AGENT_NAME is required")
        self._agent_name = agent_name
        self._api_factory = api_factory
        self._request_factory = request_factory

    async def dispatch(self, call_plan_id: str, idempotency_key: str) -> DispatchReceipt:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]
        room_name = f"hawlak-call-{digest}"
        metadata = json.dumps({"call_plan_id": call_plan_id}, separators=(",", ":"))
        async with self._api_factory() as client:
            dispatched = await client.agent_dispatch.create_dispatch(
                self._request_factory(
                    agent_name=self._agent_name,
                    room=room_name,
                    metadata=metadata,
                )
            )
        return DispatchReceipt(
            dispatch_id=dispatched.id,
            room_name=room_name,
            mode="live",
        )
