from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

GRAPH_API_URL = "https://graph.facebook.com"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
MEDIA_TIMEOUT = httpx.Timeout(connect=5, read=30, write=10, pool=5)


class WhatsAppApiError(RuntimeError):
    """A WhatsApp transport rejected an outbound request."""


class WhatsAppMediaError(RuntimeError):
    """A WhatsApp transport rejected or could not retrieve inbound media."""


class MetaApiError(WhatsAppApiError):
    """Meta's Graph API rejected a request, or accepted it without the ID we need."""


class MetaMediaError(WhatsAppMediaError):
    """Meta media retrieval failed without exposing provider response content."""


class MetaMediaRetryableError(MetaMediaError):
    """A transient provider/network failure may succeed on retry."""


class MetaMediaPermanentError(MetaMediaError):
    """The media request is invalid or violates Hawlak's safe media boundary."""


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    content: bytes
    mime_type: str


class WhatsAppClient:
    def __init__(
        self,
        graph_api_version: str,
        phone_number_id: str,
        access_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._graph_api_version = graph_api_version
        self._base_url = f"{GRAPH_API_URL}/{graph_api_version}/{phone_number_id}"
        self._access_token = access_token
        self._transport = transport  # tests pass httpx.MockTransport here

    async def send_text(self, to: str, text: str) -> str:
        body = await self._post(
            "messages", json=_message(to, "text", {"preview_url": False, "body": text})
        )
        return _message_id(body)

    async def send_template(self, to: str, name: str, language: str, values: list[str]) -> str:
        """An approved template is the only message Meta delivers outside the 24-hour window."""
        template = {
            "name": name,
            "language": {"code": language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}
            ],
        }
        body = await self._post("messages", json=_message(to, "template", template))
        return _message_id(body)

    async def upload_audio(self, audio: bytes, filename: str) -> str:
        return await self._upload_media(audio, filename, "audio/ogg")

    async def upload_image(self, image: bytes, filename: str, content_type: str) -> str:
        if content_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise MetaMediaPermanentError("Meta upload is not an allowed image")
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise MetaMediaPermanentError("Meta upload image size is invalid")
        return await self._upload_media(image, filename, content_type)

    async def _upload_media(self, content: bytes, filename: str, content_type: str) -> str:
        body = await self._post(
            "media",
            data={"messaging_product": "whatsapp", "type": content_type},
            files={"file": (filename, content, content_type)},
        )
        if not body.get("id"):
            raise MetaApiError("Meta accepted the media upload without returning a media ID")
        return body["id"]

    async def send_audio(self, to: str, media_id: str) -> str:
        body = await self._post("messages", json=_message(to, "audio", {"id": media_id}))
        return _message_id(body)

    async def send_photo_reminder(self, to: str, media_id: str) -> str:
        interactive = {
            "type": "button",
            "header": {"type": "image", "image": {"id": media_id}},
            "body": {"text": "اضغط 1 إذا أخذت الجرعة، أو 2 إذا لم تأخذها بعد."},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "taken", "title": "1"}},
                    {"type": "reply", "reply": {"id": "not_yet", "title": "2"}},
                ]
            },
        }
        body = await self._post("messages", json=_message(to, "interactive", interactive))
        return _message_id(body)

    async def download_image(self, media_id: str) -> DownloadedMedia:
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=MEDIA_TIMEOUT,
                follow_redirects=False,
            ) as http:
                metadata_response = await http.get(
                    f"{GRAPH_API_URL}/{self._graph_api_version}/{media_id}",
                    headers=headers,
                )
                self._raise_for_media_status(metadata_response)
                metadata = metadata_response.json()
                url = metadata.get("url")
                mime_type = str(metadata.get("mime_type", "")).lower()
                if not isinstance(url, str) or urlsplit(url).scheme != "https":
                    raise MetaMediaPermanentError("Meta media URL must use HTTPS")
                if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
                    raise MetaMediaPermanentError("Meta media type is not an allowed image")

                async with http.stream("GET", url, headers=headers) as media_response:
                    self._raise_for_media_status(media_response)
                    response_type = media_response.headers.get("content-type", mime_type)
                    response_type = response_type.split(";", 1)[0].strip().lower()
                    if response_type not in ALLOWED_IMAGE_MIME_TYPES:
                        raise MetaMediaPermanentError(
                            "Downloaded media type is not an allowed image"
                        )
                    content_length = media_response.headers.get("content-length")
                    if content_length and int(content_length) > MAX_IMAGE_BYTES:
                        raise MetaMediaPermanentError("Downloaded media exceeds the size limit")
                    content = bytearray()
                    async for chunk in media_response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_IMAGE_BYTES:
                            raise MetaMediaPermanentError("Downloaded media exceeds the size limit")
        except MetaMediaError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise MetaMediaRetryableError("Meta media request failed transiently") from exc
        except (ValueError, TypeError) as exc:
            raise MetaMediaPermanentError("Meta media response was invalid") from exc

        if not content:
            raise MetaMediaPermanentError("Downloaded media is empty")
        return DownloadedMedia(bytes(content), mime_type)

    @staticmethod
    def _raise_for_media_status(response: httpx.Response) -> None:
        if response.status_code == 429 or response.status_code >= 500:
            raise MetaMediaRetryableError("Meta media provider is temporarily unavailable")
        if response.is_error or response.is_redirect:
            raise MetaMediaPermanentError("Meta media request was rejected")

    async def _post(self, path: str, **request_args) -> dict:
        async with httpx.AsyncClient(transport=self._transport, timeout=30) as http:
            response = await http.post(
                f"{self._base_url}/{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                **request_args,
            )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.is_error:
            message = body.get("error", {}).get("message", "unknown error")
            raise MetaApiError(f"Meta API {response.status_code}: {message}")
        return body


def _message(to: str, kind: str, content: dict) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.removeprefix("+"),
        "type": kind,
        kind: content,
    }


def _message_id(body: dict) -> str:
    messages = body.get("messages") or []
    if not messages or not messages[0].get("id"):
        raise MetaApiError("Meta accepted the request without returning a message ID")
    return messages[0]["id"]
