import asyncio
import json
from types import SimpleNamespace

from hawlak_agent.dispatch import LiveKitCallDispatcher


class FakeDispatchService:
    def __init__(self):
        self.requests = []

    async def create_dispatch(self, request):
        self.requests.append(request)
        return SimpleNamespace(id="dispatch-live-001")


class FakeLiveKitApi:
    def __init__(self, dispatch_service):
        self.agent_dispatch = dispatch_service

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def test_live_dispatch_metadata_contains_only_call_plan_id() -> None:
    service = FakeDispatchService()
    dispatcher = LiveKitCallDispatcher(
        agent_name="hawlak-follow-up",
        api_factory=lambda: FakeLiveKitApi(service),
        request_factory=lambda **values: values,
    )

    receipt = asyncio.run(dispatcher.dispatch("plan-synthetic-001", "idem-secret-value"))

    assert receipt.mode == "live"
    assert receipt.dispatch_id == "dispatch-live-001"
    assert json.loads(service.requests[0]["metadata"]) == {"call_plan_id": "plan-synthetic-001"}
    assert service.requests[0]["agent_name"] == "hawlak-follow-up"
    assert "idem-secret-value" not in service.requests[0]["room"]
