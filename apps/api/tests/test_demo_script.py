import pytest

from scripts.demo import (
    PreflightCheck,
    PreflightFailed,
    build_parser,
    load_case,
    require_preflight,
    run_mock,
)


@pytest.mark.anyio
async def test_mock_demo_completes_with_no_keys_or_network():
    result = await run_mock(load_case("abu-mohammed"), approve=lambda _: True)

    assert result["mode"] == "mock"
    assert result["synthetic"] is True
    assert result["factGuardPassed"] is True
    assert len(result["messageIds"]) == 3
    assert result["storedObjectCount"] == 4
    assert result["reviewEvent"]["eventType"] == "pharmacist_review_requested"
    assert result["outcomeReplayCreated"] is False


def test_failed_preflight_stops_before_live_work():
    with pytest.raises(PreflightFailed, match="Meta test number"):
        require_preflight(
            [
                PreflightCheck("API health", True, "HTTP 200"),
                PreflightCheck("Meta test number", False, "HTTP 401"),
            ]
        )


def test_demo_help_does_not_load_settings_or_contact_network(capsys):
    with pytest.raises(SystemExit) as stopped:
        build_parser().parse_args(["--help"])
    assert stopped.value.code == 0
    assert "--mock" in capsys.readouterr().out
