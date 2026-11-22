from hashlib import sha256


def log_id(wa_message_id: str | None) -> str:
    """Meta message IDs embed the recipient's phone number, so logs carry a short hash."""
    return sha256((wa_message_id or "").encode()).hexdigest()[:12]
