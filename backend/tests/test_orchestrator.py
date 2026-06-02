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
