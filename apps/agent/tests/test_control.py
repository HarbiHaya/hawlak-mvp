import asyncio

from hawlak_agent.control import CallControl, CallRequest, DispatchReceipt


class FakeDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, call_plan_id: str, idempotency_key: str) -> DispatchReceipt:
        self.calls.append((call_plan_id, idempotency_key))
        return DispatchReceipt(
            dispatch_id="dispatch-synthetic-001",
            room_name="hawlak-synthetic-room",
            mode="mock",
        )


def test_control_dispatches_without_accepting_a_phone_number() -> None:
    dispatcher = FakeDispatcher()
    control = CallControl(dispatcher)
    request = CallRequest(
        callPlanId="plan-synthetic-001",
        caseId="case-synthetic-001",
        scheduledAt="2026-11-12T09:30:00Z",
    )

    result = asyncio.run(control.request_call(request, "idem-synthetic-001"))

    assert result.status == "accepted"
    assert dispatcher.calls == [("plan-synthetic-001", "idem-synthetic-001")]


def test_control_replays_same_result_for_same_idempotency_key() -> None:
    dispatcher = FakeDispatcher()
    control = CallControl(dispatcher)
    request = CallRequest(
        callPlanId="plan-synthetic-001",
        caseId="case-synthetic-001",
        scheduledAt="2026-11-12T09:30:00Z",
    )

    first = asyncio.run(control.request_call(request, "idem-synthetic-001"))
    second = asyncio.run(control.request_call(request, "idem-synthetic-001"))

    assert second == first
    assert len(dispatcher.calls) == 1


def test_control_rejects_idempotency_key_reuse_for_another_plan() -> None:
    control = CallControl(FakeDispatcher())
    first = CallRequest(
        callPlanId="plan-synthetic-001",
        caseId="case-synthetic-001",
        scheduledAt="2026-11-12T09:30:00Z",
    )
    second = first.model_copy(update={"call_plan_id": "plan-synthetic-002"})
    asyncio.run(control.request_call(first, "same-key"))

    try:
        asyncio.run(control.request_call(second, "same-key"))
    except ValueError as exc:
        assert "idempotency key" in str(exc)
    else:
        raise AssertionError("reusing an idempotency key for another plan must fail")
