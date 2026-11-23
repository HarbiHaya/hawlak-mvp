from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .conversation import AnswerKind


class ClassificationError(RuntimeError):
    pass


class AnswerClassifier(Protocol):
    async def classify(self, transcript: str, *, question: str | None = None) -> AnswerKind: ...


class OpenAIAnswerClassifier:
    """Classifies intent only; it never generates patient-facing language."""

    _SYSTEM_PROMPT = (
        "Classify the caller's latest reply to the question the agent just asked. Read "
        "the reply as an answer to that question: a short yes or no takes its meaning "
        "from the question. Return red_flag when the caller reports or confirms "
        "a symptom, warning sign, deterioration, or urgent concern. Return question when "
        "the caller asks something or does not understand, unless the reply also reports a "
        "warning sign. Return uncertain "
        "when meaning is unclear or confidence is low. Return transfer_request when the "
        "caller asks for a human. Return clear only when none of those conditions apply."
    )

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("OPENAI_BASE_URL must be an HTTP origin")
        if not api_key or not model:
            raise ValueError("classifier API key and model are required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    async def classify(self, transcript: str, *, question: str | None = None) -> AnswerKind:
        if not transcript.strip():
            raise ClassificationError("caller reply could not be classified")
        return await asyncio.to_thread(self._classify_sync, transcript, question)

    def _classify_sync(self, transcript: str, question: str | None) -> AnswerKind:
        # The question is an approved script, so it carries no patient identifier.
        reply = transcript
        if question:
            reply = f"Question asked: {question}\nCaller reply: {transcript}"
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {
                    "type": "string",
                    "enum": [member.value for member in AnswerKind],
                }
            },
            "required": ["answer"],
        }
        body = {
            "model": self._model,
            "input": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": reply},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer_classification",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        request = Request(
            f"{self._base_url}/responses",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                result = json.loads(response.read())
            for output in result.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        parsed = json.loads(content["text"])
                        return AnswerKind(parsed["answer"])
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as exc:
            raise ClassificationError("caller reply could not be classified") from exc
        raise ClassificationError("caller reply could not be classified")
