import base64
import hashlib
import hmac


def verify_twilio_signature(
    url: str,
    parameters: dict[str, str],
    supplied_signature: str | None,
    auth_token: str,
) -> bool:
    if not supplied_signature:
        return False
    signed = url + "".join(key + parameters[key] for key in sorted(parameters))
    digest = hmac.new(auth_token.encode(), signed.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(supplied_signature, expected)
