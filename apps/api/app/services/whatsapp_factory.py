import httpx

from app.config import Settings
from app.services.object_storage import ObjectStorage
from app.services.twilio_client import TwilioWhatsAppClient
from app.services.whatsapp_client import WhatsAppClient


def build_whatsapp_client(
    settings: Settings,
    storage: ObjectStorage,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
):
    if settings.whatsapp_provider == "twilio":
        assert settings.twilio_account_sid is not None
        assert settings.twilio_auth_token is not None
        return TwilioWhatsAppClient(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token.get_secret_value(),
            from_number=settings.twilio_whatsapp_from,
            public_base_url=settings.public_base_url,
            storage=storage,
            transport=transport,
        )
    return WhatsAppClient(
        settings.meta_graph_api_version,
        settings.whatsapp_phone_number_id,
        settings.whatsapp_access_token,
        transport=transport,
    )
