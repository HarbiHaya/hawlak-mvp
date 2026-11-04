from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import SettingsDep
from app.services.whatsapp_client import WhatsAppClient

router = APIRouter()

DEMO_TEXT = "أهلًا من حولك. هذا اختبار الاتصال عبر واتساب."


def get_whatsapp_client(settings: SettingsDep) -> WhatsAppClient:
    return WhatsAppClient(
        settings.meta_graph_api_version,
        settings.whatsapp_phone_number_id,
        settings.whatsapp_access_token,
    )


@router.post("/demo/send-text", status_code=202)
async def send_demo_text(
    settings: SettingsDep,
    whatsapp: Annotated[WhatsAppClient, Depends(get_whatsapp_client)],
) -> dict[str, str]:
    message_id = await whatsapp.send_text(settings.whatsapp_test_recipient, DEMO_TEXT)
    return {"messageId": message_id}
