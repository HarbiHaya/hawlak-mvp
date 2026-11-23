from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .conversation import AnswerKind


class CallOutcomeReportError(RuntimeError):
    pass


class CallOutcomeClient:
    """Reports a minimal terminal call outcome to Hawlak's internal API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.1,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("HAWLAK_API_BASE_URL must be an HTTP origin")
        if not token:
            raise ValueError("HAWLAK_INTERNAL_API_TOKEN is required")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._opener = opener

    async def record_completed(self, run_id: str) -> None:
        await self._record(run_id, {"status": "completed"})

    async def record_transferred(
        self,
        run_id: str,
        *,
        question_id: str,
        answer_kind: AnswerKind,
    ) -> None:
        await self._record_escalation(
            "transferred",
            run_id,
            question_id=question_id,
            answer_kind=answer_kind,
        )

    async def record_failed(
        self,
        run_id: str,
        *,
        question_id: str,
        answer_kind: AnswerKind,
    ) -> None:
        await self._record_escalation(
            "failed",
            run_id,
            question_id=question_id,
            answer_kind=answer_kind,
        )

    async def _record_escalation(
        self,
        status: Literal["failed", "transferred"],
        run_id: str,
        *,
        question_id: str,
        answer_kind: AnswerKind,
    ) -> None:
        if answer_kind is AnswerKind.CLEAR:
            raise ValueError("a terminal escalation requires an escalation answer")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", question_id):
            raise ValueError("invalid approved question id")
        await self._record(
            run_id,
            {
                "status": status,
                "escalation": {
                    "questionId": question_id,
                    "answerKind": answer_kind.value,
                },
            },
        )

    async def record_turns(self, run_id: str, turns: list[dict[str, Any]]) -> None:
        """Store what was said, for the care team; the API deduplicates by turn number."""
        _check_run_id(run_id)
        await asyncio.to_thread(
            self._send, run_id, "call-turns", {"turns": turns}, f"call-turns:{run_id}"
        )

    async def _record(self, run_id: str, payload: dict[str, Any]) -> None:
        _check_run_id(run_id)
        key = f"call-outcome:{run_id}:{payload['status']}"
        await asyncio.to_thread(self._send, run_id, "call-outcome", payload, key)

    def _send(self, run_id: str, path: str, payload: dict[str, Any], key: str) -> None:
        request = Request(
            f"{self._base_url}/internal/delivery-runs/{run_id}/{path}",
            data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Idempotency-Key": key,
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                with self._opener(request, timeout=self._timeout_seconds):
                    return
            except HTTPError as exc:
                last_error = exc
                if not 500 <= exc.code <= 599:
                    break
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt + 1 < self._max_attempts:
                time.sleep(self._retry_delay_seconds)
        raise CallOutcomeReportError("call outcome could not be recorded") from last_error


def _check_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,127}", run_id):
        raise ValueError("invalid delivery run id")
