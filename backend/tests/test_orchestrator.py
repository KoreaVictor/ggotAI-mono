import asyncio

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
