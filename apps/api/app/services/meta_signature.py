import hashlib
import hmac

PREFIX = "sha256="


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Check Meta's X-Hub-Signature-256 header against the exact bytes that were received."""
    if not signature_header or not signature_header.startswith(PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix(PREFIX).encode(), expected.encode())
