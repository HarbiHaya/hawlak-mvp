from app.services.meta_signature import verify_meta_signature

SECRET = "test-app-secret"


def test_accepts_an_authentic_payload(sign):
    body = b'{"object":"whatsapp_business_account"}'

    assert verify_meta_signature(body, sign(body, SECRET), SECRET) is True


def test_rejects_a_changed_payload(sign):
    header = sign(b'{"ok":true}', SECRET)

    assert verify_meta_signature(b'{"ok":false}', header, SECRET) is False


def test_rejects_a_missing_signature_header():
    assert verify_meta_signature(b"{}", None, SECRET) is False


def test_rejects_a_signature_without_the_sha256_prefix(sign):
    bare_digest = sign(b"{}", SECRET).removeprefix("sha256=")

    assert verify_meta_signature(b"{}", bare_digest, SECRET) is False
