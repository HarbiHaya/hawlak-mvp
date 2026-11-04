from hashlib import sha256
from io import BytesIO

import pytest

from app.services.object_storage import ObjectStorage


class FakeS3Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, **kwargs):
        self.calls.append(("head_bucket", kwargs))

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
        return {"ETag": '"fake-etag"'}

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        return {"Body": BytesIO(self.objects[(kwargs["Bucket"], kwargs["Key"])])}

    def generate_presigned_url(self, operation, **kwargs):
        self.calls.append(("generate_presigned_url", {"operation": operation, **kwargs}))
        return f"http://storage.test/{kwargs['Params']['Key']}"


@pytest.fixture
def fake_s3():
    return FakeS3Client()


@pytest.fixture
def storage(settings, fake_s3):
    return ObjectStorage(settings, client=fake_s3, object_id_factory=lambda: "object-123")


def test_checks_the_configured_bucket(storage, fake_s3):
    storage.ensure_bucket()

    assert fake_s3.calls == [("head_bucket", {"Bucket": "hawlak-mvp"})]


def test_stores_case_media_without_interpreting_it(storage, fake_s3):
    content = b"synthetic medicine-box photo"

    stored = storage.store_case_media(
        case_id="case-123",
        content=content,
        content_type="image/jpeg",
        source_media_id="meta-media-456",
    )

    assert stored.key == "cases/case-123/media/object-123.jpg"
    assert stored.size == len(content)
    assert stored.sha256 == sha256(content).hexdigest()
    assert stored.etag == "fake-etag"
    _, request = fake_s3.calls[-1]
    assert request["Bucket"] == "hawlak-mvp"
    assert request["Body"] == content
    assert request["ContentType"] == "image/jpeg"
    assert request["Metadata"] == {
        "sha256": sha256(content).hexdigest(),
        "source-media-id": "meta-media-456",
    }


def test_rejects_an_unsafe_case_id(storage):
    with pytest.raises(ValueError, match="case_id"):
        storage.store_case_media(
            case_id="../../lucidya",
            content=b"photo",
            content_type="image/jpeg",
            source_media_id="media-id",
        )


def test_rejects_empty_content(storage):
    with pytest.raises(ValueError, match="empty"):
        storage.store_case_media(
            case_id="case-123",
            content=b"",
            content_type="image/jpeg",
            source_media_id="media-id",
        )


def test_downloads_the_exact_stored_bytes(storage):
    stored = storage.store_case_media(
        case_id="case-123",
        content=b"exact bytes",
        content_type="image/png",
        source_media_id="media-id",
    )

    assert storage.get_bytes(stored.key) == b"exact bytes"


def test_creates_a_short_lived_download_url(storage, fake_s3):
    url = storage.create_download_url("cases/case-123/media/object-123.jpg", expires_in=120)

    assert url == "http://storage.test/cases/case-123/media/object-123.jpg"
    _, request = fake_s3.calls[-1]
    assert request == {
        "operation": "get_object",
        "Params": {
            "Bucket": "hawlak-mvp",
            "Key": "cases/case-123/media/object-123.jpg",
        },
        "ExpiresIn": 120,
    }
