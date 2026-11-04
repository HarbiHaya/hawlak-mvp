import json

import httpx
import pytest

from app.services.whatsapp_client import (
    MAX_IMAGE_BYTES,
    MetaApiError,
    MetaMediaPermanentError,
    MetaMediaRetryableError,
    WhatsAppClient,
)

pytestmark = pytest.mark.anyio

RECIPIENT = "+966500000000"


async def test_send_text_posts_a_text_message_and_returns_its_id(fake_meta):
    whatsapp, seen = fake_meta(httpx.Response(200, json={"messages": [{"id": "wamid.1"}]}))

    message_id = await whatsapp.send_text(RECIPIENT, "مرحبا")

    assert message_id == "wamid.1"
    request = seen[0]
    assert str(request.url) == "https://graph.facebook.com/v-test/phone-id/messages"
    assert request.headers["authorization"] == "Bearer test-token"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": RECIPIENT,
        "type": "text",
        "text": {"preview_url": False, "body": "مرحبا"},
    }


async def test_upload_audio_sends_the_ogg_file_as_multipart_and_returns_the_media_id(fake_meta):
    whatsapp, seen = fake_meta(httpx.Response(200, json={"id": "media-1"}))

    media_id = await whatsapp.upload_audio(b"OggS-fake-audio", "note.ogg")

    assert media_id == "media-1"
    request = seen[0]
    assert str(request.url) == "https://graph.facebook.com/v-test/phone-id/media"
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["content-type"].startswith("multipart/form-data")
    for part in (
        b'name="messaging_product"',
        b"whatsapp",
        b'name="type"',
        b"audio/ogg",
        b'filename="note.ogg"',
        b"OggS-fake-audio",
    ):
        assert part in request.content


async def test_send_audio_posts_an_audio_message_that_references_the_media_id(fake_meta):
    whatsapp, seen = fake_meta(httpx.Response(200, json={"messages": [{"id": "wamid.2"}]}))

    message_id = await whatsapp.send_audio(RECIPIENT, "media-1")

    assert message_id == "wamid.2"
    assert json.loads(seen[0].content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": RECIPIENT,
        "type": "audio",
        "audio": {"id": "media-1"},
    }


async def test_raises_with_metas_message_when_the_api_rejects_a_request(fake_meta):
    error = {"error": {"message": "Recipient not in allowed list", "code": 131030}}
    whatsapp, _ = fake_meta(httpx.Response(400, json=error))

    with pytest.raises(MetaApiError, match="Meta API 400: Recipient not in allowed list"):
        await whatsapp.send_text(RECIPIENT, "hi")


async def test_raises_unknown_error_when_a_failure_body_is_not_json(fake_meta):
    whatsapp, _ = fake_meta(httpx.Response(502, text="<html>Bad Gateway</html>"))

    with pytest.raises(MetaApiError, match="Meta API 502: unknown error"):
        await whatsapp.send_text(RECIPIENT, "hi")


async def test_raises_when_meta_accepts_a_message_without_an_id(fake_meta):
    whatsapp, _ = fake_meta(httpx.Response(200, json={}))

    with pytest.raises(MetaApiError, match="without returning a message ID"):
        await whatsapp.send_text(RECIPIENT, "hi")


async def test_raises_when_meta_accepts_an_upload_without_a_media_id(fake_meta):
    whatsapp, _ = fake_meta(httpx.Response(200, json={}))

    with pytest.raises(MetaApiError, match="without returning a media ID"):
        await whatsapp.upload_audio(b"OggS-fake-audio", "note.ogg")


def media_client(handler) -> WhatsAppClient:
    return WhatsAppClient(
        "v-test",
        "phone-id",
        "test-token",
        transport=httpx.MockTransport(handler),
    )


async def test_download_image_fetches_metadata_then_bounded_https_bytes():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == "https://graph.facebook.com/v-test/media-1":
            return httpx.Response(
                200,
                json={"url": "https://lookaside.test/media-1", "mime_type": "image/jpeg"},
            )
        return httpx.Response(
            200, content=b"synthetic-photo", headers={"content-type": "image/jpeg"}
        )

    downloaded = await media_client(handler).download_image("media-1")

    assert downloaded.content == b"synthetic-photo"
    assert downloaded.mime_type == "image/jpeg"
    assert [str(request.url) for request in seen] == [
        "https://graph.facebook.com/v-test/media-1",
        "https://lookaside.test/media-1",
    ]
    assert all(request.headers["authorization"] == "Bearer test-token" for request in seen)


@pytest.mark.parametrize(
    ("metadata", "error"),
    [
        ({"url": "http://lookaside.test/media-1", "mime_type": "image/jpeg"}, "HTTPS"),
        ({"url": "https://lookaside.test/media-1", "mime_type": "application/pdf"}, "type"),
    ],
)
async def test_download_image_rejects_unsafe_metadata(metadata, error):
    client = media_client(lambda request: httpx.Response(200, json=metadata, request=request))

    with pytest.raises(MetaMediaPermanentError, match=error):
        await client.download_image("media-1")


async def test_download_image_redacts_provider_error_bodies():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "secret provider detail"}}, request=request
        )

    with pytest.raises(MetaMediaPermanentError) as caught:
        await media_client(handler).download_image("media-1")

    assert "secret provider detail" not in str(caught.value)


@pytest.mark.parametrize(
    "content",
    [b"", b"x" * (MAX_IMAGE_BYTES + 1)],
    ids=["empty", "oversized"],
)
async def test_download_image_rejects_empty_or_oversized_content(content):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={"url": "https://lookaside.test/media-1", "mime_type": "image/jpeg"},
                request=request,
            )
        return httpx.Response(
            200, content=content, headers={"content-type": "image/jpeg"}, request=request
        )

    with pytest.raises(MetaMediaPermanentError):
        await media_client(handler).download_image("media-1")


async def test_download_image_converts_timeouts_to_retryable_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(MetaMediaRetryableError):
        await media_client(handler).download_image("media-1")
