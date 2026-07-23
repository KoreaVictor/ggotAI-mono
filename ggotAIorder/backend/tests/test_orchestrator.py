import ggotaiorder.orchestrator as orch_mod
from ggotaiorder.orchestrator import Orchestrator


def test_starts_unpaused():
    orch = Orchestrator()
    assert orch.paused is False


def test_pause_resume_toggles_state():
    orch = Orchestrator()
    orch.pause()
    assert orch.paused is True
    orch.resume()
    assert orch.paused is False


def test_catchup_interval_constant_is_30_min():
    assert orch_mod._CATCHUP_INTERVAL_MIN == 30


async def test_scheduled_catchup_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 0

    monkeypatch.setattr(orch._scanner, "scan_once", fake_scan)

    await orch._scheduled_catchup()

    assert called["scan"] is False


async def test_scheduled_catchup_runs_when_active(monkeypatch):
    orch = Orchestrator()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 2

    monkeypatch.setattr(orch._scanner, "scan_once", fake_scan)

    await orch._scheduled_catchup()

    assert called["scan"] is True


def test_smartstore_interval_constants():
    assert orch_mod._SMARTSTORE_INTERVAL_MIN == 10
    assert orch_mod._MALL_CONFIRM_INTERVAL_MIN == 5


async def test_scheduled_mall_poll_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"poll": False}

    async def fake_poll():
        called["poll"] = True

    monkeypatch.setattr(orch_mod, "mall_poll_once", fake_poll)
    await orch._scheduled_mall_poll()
    assert called["poll"] is False


async def test_scheduled_mall_poll_runs_when_active(monkeypatch):
    orch = Orchestrator()
    called = {"poll": False}

    async def fake_poll():
        called["poll"] = True

    monkeypatch.setattr(orch_mod, "mall_poll_once", fake_poll)
    await orch._scheduled_mall_poll()
    assert called["poll"] is True


async def test_scheduled_mall_confirm_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 0

    monkeypatch.setattr(orch._mall_confirm, "scan_once", fake_scan)
    await orch._scheduled_mall_confirm()
    assert called["scan"] is False
