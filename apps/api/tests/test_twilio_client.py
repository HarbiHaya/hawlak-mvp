from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.services.object_storage import StoredObject
from app.services.twilio_client import TwilioApiError, TwilioWhatsAppClient
from app.services.twilio_media import resolve_twilio_media_token

pytestmark = pytest.mark.anyio


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        key = f"cases/{case_id}/media/audio.ogg"
        self.objects[key] = content
        return StoredObject(
            key=key,
            size=len(content),
            sha256="a" * 64,
            etag="fake",
            content_type=content_type,
        )


def client(response, *, storage=None):
    seen = []

    def handler(request):
        seen.append(request)
        return response(request) if callable(response) else response

    return (
        TwilioWhatsAppClient(
            account_sid="AC" + "1" * 32,
            auth_token="twilio-test-auth-token-long-enough",
            from_number="+14155238886",
            public_base_url="https://hawlak-tunnel.example",
            storage=storage or FakeStorage(),
            transport=httpx.MockTransport(handler),
        ),
        seen,
    )


async def test_send_text_posts_whatsapp_form_and_status_callback():
    whatsapp, seen = client(httpx.Response(201, json={"sid": "SM-text"}))

    message_id = await whatsapp.send_text("+966500000000", "مرحبا")

    assert message_id == "SM-text"
    request = seen[0]
    assert str(request.url).endswith("/Accounts/AC11111111111111111111111111111111/Messages.json")
    assert request.headers["authorization"].startswith("Basic ")
    form = parse_qs(request.content.decode())
    assert form == {
        "From": ["whatsapp:+14155238886"],
        "To": ["whatsapp:+966500000000"],
        "Body": ["مرحبا"],
        "StatusCallback": ["https://hawlak-tunnel.example/webhooks/twilio"],
    }


async def test_audio_is_published_as_a_signed_url_then_sent():
    storage = FakeStorage()
    whatsapp, seen = client(httpx.Response(201, json={"sid": "SM-audio"}), storage=storage)

    media_url = await whatsapp.upload_audio(b"OggS-audio", "hawlak.ogg")
    message_id = await whatsapp.send_audio("+966500000000", media_url)

    assert message_id == "SM-audio"
    parsed = urlsplit(media_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "hawlak-tunnel.example"
    token = parsed.path.rsplit("/", 1)[-1]
    media = resolve_twilio_media_token(
        token,
        "twilio-test-auth-token-long-enough",
    )
    assert media.object_key == "cases/twilio-outbound/media/audio.ogg"
    assert media.content_type == "audio/ogg"
    form = parse_qs(seen[0].content.decode())
    assert form["MediaUrl"] == [media_url]
    assert "Body" not in form


async def test_download_image_uses_twilio_auth_and_enforces_image_type():
    def response(request):
        return httpx.Response(
            200,
            content=b"synthetic-image",
            headers={"content-type": "image/jpeg"},
            request=request,
        )

    whatsapp, seen = client(response)
    downloaded = await whatsapp.download_image(
        "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/SM1/Media/ME1"
    )

    assert downloaded.content == b"synthetic-image"
    assert downloaded.mime_type == "image/jpeg"
    assert seen[0].headers["authorization"].startswith("Basic ")


async def test_twilio_errors_do_not_expose_provider_response_body():
    whatsapp, _ = client(httpx.Response(401, json={"message": "secret provider detail"}))

    with pytest.raises(TwilioApiError) as caught:
        await whatsapp.send_text("+966500000000", "hi")

    assert "secret provider detail" not in str(caught.value)


async def test_photo_reminder_creates_card_with_quick_replies_and_sends_it():
    responses = iter(
        [
            httpx.Response(201, json={"sid": "HX-reminder"}),
            httpx.Response(201, json={"sid": "MM-reminder"}),
        ]
    )
    whatsapp, seen = client(lambda request: next(responses))

    message_id = await whatsapp.send_photo_reminder(
        "+966500000000",
        object_key="cases/case_01/media/photo.jpg",
        content_type="image/jpeg",
    )

    assert message_id == "MM-reminder"
    assert str(seen[0].url) == "https://content.twilio.com/v1/Content"
    content = __import__("json").loads(seen[0].content)
    card = content["types"]["twilio/card"]
    assert card["media"][0].startswith("https://hawlak-tunnel.example/webhooks/twilio/media/")
    assert card["media"][0].endswith("/hawlak-media.jpg")
    assert card["title"] == "١ / ٢"
    assert [action["title"] for action in card["actions"]] == ["١", "٢"]
    assert [action["id"] for action in card["actions"]] == ["taken", "not_yet"]
    form = parse_qs(seen[1].content.decode())
    assert form["ContentSid"] == ["HX-reminder"]
