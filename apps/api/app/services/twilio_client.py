from typing import Protocol
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from app.services.twilio_media import create_twilio_media_token
from app.services.whatsapp_client import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_BYTES,
    DownloadedMedia,
    WhatsAppApiError,
    WhatsAppMediaError,
)

TWILIO_API_URL = "https://api.twilio.com/2010-04-01"
TWILIO_CONTENT_URL = "https://content.twilio.com/v1/Content"
MEDIA_TIMEOUT = httpx.Timeout(connect=5, read=30, write=10, pool=5)


class TwilioApiError(WhatsAppApiError):
    """Twilio rejected a WhatsApp request without exposing provider details."""


class TwilioMediaError(WhatsAppMediaError):
    """Twilio media retrieval failed or crossed Hawlak's media boundary."""


class StorageLike(Protocol):
    def store_case_media(
        self, *, case_id: str, content: bytes, content_type: str, source_media_id: str
    ): ...


class TwilioWhatsAppClient:
    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        public_base_url: str,
        storage: StorageLike,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._public_base_url = public_base_url.rstrip("/")
        self._storage = storage
        self._transport = transport
        self._messages_url = f"{TWILIO_API_URL}/Accounts/{account_sid}/Messages.json"

    async def send_text(self, to: str, text: str) -> str:
        return await self._send_message({"Body": text, **self._addresses(to)})

    async def upload_audio(self, audio: bytes, filename: str) -> str:
        stored = self._storage.store_case_media(
            case_id="twilio-outbound",
            content=audio,
            content_type="audio/ogg",
            source_media_id=filename,
        )
        token = create_twilio_media_token(
            stored.key,
            "audio/ogg",
            self._auth_token,
            expires_in=900,
        )
        return f"{self._public_base_url}/webhooks/twilio/media/{quote(token, safe='')}"

    async def send_audio(self, to: str, media_id: str) -> str:
        return await self._send_message({"MediaUrl": media_id, **self._addresses(to)})

    async def send_photo_reminder(
        self,
        to: str,
        *,
        object_key: str,
        content_type: str,
    ) -> str:
        media_url = self._public_media_url(object_key, content_type)
        content = {
            "friendly_name": f"hawlak_reminder_{uuid4().hex[:16]}",
            "language": "ar",
            "types": {
                "twilio/card": {
                    "title": "١ / ٢",
                    "media": [media_url],
                    "actions": [
                        {"type": "QUICK_REPLY", "title": "١", "id": "taken"},
                        {"type": "QUICK_REPLY", "title": "٢", "id": "not_yet"},
                    ],
                }
            },
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30,
                auth=httpx.BasicAuth(self._account_sid, self._auth_token),
            ) as http:
                response = await http.post(TWILIO_CONTENT_URL, json=content)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TwilioApiError("Twilio Content API request failed") from exc
        if response.is_error:
            raise TwilioApiError(
                f"Twilio Content API {response.status_code}: request rejected"
                f" (code {_provider_error_code(response)})"
            )
        try:
            content_sid = response.json().get("sid")
        except ValueError:
            content_sid = None
        if not content_sid:
            raise TwilioApiError("Twilio created no Content SID")
        return await self._send_message({"ContentSid": str(content_sid), **self._addresses(to)})

    async def download_image(self, media_id: str) -> DownloadedMedia:
        parsed = urlsplit(media_id)
        if parsed.scheme != "https" or parsed.hostname != "api.twilio.com":
            raise TwilioMediaError("Twilio media URL is not allowed")
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=MEDIA_TIMEOUT,
                follow_redirects=True,
                auth=httpx.BasicAuth(self._account_sid, self._auth_token),
            ) as http:
                async with http.stream("GET", media_id) as response:
                    if response.is_error:
                        raise TwilioMediaError("Twilio media request was rejected")
                    mime_type = response.headers.get("content-type", "")
                    mime_type = mime_type.split(";", 1)[0].strip().lower()
                    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
                        raise TwilioMediaError("Twilio media is not an allowed image")
                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_IMAGE_BYTES:
                        raise TwilioMediaError("Twilio media exceeds the size limit")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_IMAGE_BYTES:
                            raise TwilioMediaError("Twilio media exceeds the size limit")
        except TwilioMediaError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
            raise TwilioMediaError("Twilio media retrieval failed") from exc
        if not content:
            raise TwilioMediaError("Twilio media is empty")
        return DownloadedMedia(bytes(content), mime_type)

    def _addresses(self, to: str) -> dict[str, str]:
        return {
            "From": f"whatsapp:{self._from_number}",
            "To": f"whatsapp:{to}",
            "StatusCallback": f"{self._public_base_url}/webhooks/twilio",
        }

    def _public_media_url(self, object_key: str, content_type: str) -> str:
        token = create_twilio_media_token(
            object_key,
            content_type,
            self._auth_token,
            expires_in=900,
        )
        extension = {"image/jpeg": "jpg", "image/png": "png", "audio/ogg": "ogg"}.get(
            content_type, "bin"
        )
        return (
            f"{self._public_base_url}/webhooks/twilio/media/"
            f"{quote(token, safe='')}/hawlak-media.{extension}"
        )

    async def _send_message(self, form: dict[str, str]) -> str:
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30,
                auth=httpx.BasicAuth(self._account_sid, self._auth_token),
            ) as http:
                response = await http.post(self._messages_url, data=form)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TwilioApiError("Twilio API request failed") from exc
        if response.is_error:
            raise TwilioApiError(
                f"Twilio API {response.status_code}: request rejected"
                f" (code {_provider_error_code(response)})"
            )
        try:
            sid = response.json().get("sid")
        except ValueError:
            sid = None
        if not sid:
            raise TwilioApiError("Twilio accepted the request without returning a message SID")
        return str(sid)


def _provider_error_code(response: httpx.Response) -> str:
    try:
        return str(response.json().get("code", "unknown"))
    except ValueError:
        return "unknown"
