from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from .conversation import CallPlan


class PlanFetchError(RuntimeError):
    pass


class ApprovedPlanClient:
    """Fetches one approved plan without exposing transport details to the worker."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("HAWLAK_API_BASE_URL must be an HTTP origin")
        if not token:
            raise ValueError("HAWLAK_INTERNAL_API_TOKEN is required")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def fetch(self, plan_id: str) -> CallPlan:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,127}", plan_id):
            raise ValueError("invalid call plan id")
        request = Request(
            f"{self._base_url}/internal/call-plans/{plan_id}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
            return CallPlan.model_validate(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValidationError) as exc:
            raise PlanFetchError("call plan is unavailable") from exc
