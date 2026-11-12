from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, frozen=True)

    call_plan_id: str = Field(alias="callPlanId", min_length=3, max_length=128)
    case_id: str = Field(alias="caseId", min_length=3, max_length=128)
    scheduled_at: datetime = Field(alias="scheduledAt")

    @field_validator("call_plan_id", "case_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        if not all(character.isalnum() or character in "-_" for character in value):
            raise ValueError("identifier contains unsupported characters")
        return value


class DispatchReceipt(BaseModel):
    model_config = ConfigDict(populate_by_name=True, frozen=True)

    dispatch_id: str = Field(alias="dispatchId")
    room_name: str = Field(alias="roomName")
    mode: Literal["mock", "live"]


class CallResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["accepted"] = "accepted"
    dispatch: DispatchReceipt


class CallDispatcher(Protocol):
    async def dispatch(self, call_plan_id: str, idempotency_key: str) -> DispatchReceipt: ...


class CallControl:
    """Idempotent command seam used by the backend when a call becomes due."""

    def __init__(self, dispatcher: CallDispatcher) -> None:
        self._dispatcher = dispatcher
        self._requests: dict[str, tuple[CallRequest, CallResult]] = {}

    async def request_call(self, request: CallRequest, idempotency_key: str) -> CallResult:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise ValueError("a valid idempotency key is required")
        previous = self._requests.get(idempotency_key)
        if previous:
            if previous[0] != request:
                raise ValueError("idempotency key was already used for another call")
            return previous[1]
        receipt = await self._dispatcher.dispatch(request.call_plan_id, idempotency_key)
        result = CallResult(dispatch=receipt)
        self._requests[idempotency_key] = (request, result)
        return result


class MockCallDispatcher:
    async def dispatch(self, call_plan_id: str, idempotency_key: str) -> DispatchReceipt:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        return DispatchReceipt(
            dispatchId=f"mock-{digest}",
            roomName=f"hawlak-{digest}",
            mode="mock",
        )
