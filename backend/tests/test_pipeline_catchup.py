"""CatchupScanner 단위 테스트.

scan_once() 는 _REALTIME_CHANNELS 집합과 MAX_ATTEMPTS 상한을 engine 에서 가져와
미처리(is_processed=NULL) 행을 repo.list_pending_call_ids 로 조회한 뒤
각 id 에 대해 process() 를 호출한다.
"""

from __future__ import annotations

import asyncio

import pytest

from ggotaiorder.pipeline import catchup as catchup_mod
from ggotaiorder.pipeline.catchup import CatchupScanner
from ggotaiorder.pipeline.engine import MAX_ATTEMPTS, _REALTIME_CHANNELS


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakeRepo:
    def __init__(self, pending: list[int] | None = None):
        self._pending = pending or []
        self.list_calls: list[tuple] = []

    def list_pending_call_ids(self, channels: set[str], max_attempts: int) -> list[int]:
        self.list_calls.append((channels, max_attempts))
        return self._pending


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_scanner(repo: FakeRepo, monkeypatch) -> tuple[CatchupScanner, list[int]]:
    """CatchupScanner 를 fake repo 와 process 스파이로 초기화한다."""
    processed: list[int] = []

    async def spy_process(call_history_id: int, **_kw) -> None:
        processed.append(call_history_id)

    monkeypatch.setattr(catchup_mod, "process", spy_process)
    scanner = CatchupScanner(repo=repo)
    return scanner, processed


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

async def test_scan_once_calls_process_for_each_pending(monkeypatch):
    """미처리 행이 있으면 각 id 에 대해 process() 가 정확히 한 번씩 호출된다."""
    repo = FakeRepo(pending=[1, 2, 3])
    scanner, processed = _make_scanner(repo, monkeypatch)

    await scanner.scan_once()

    assert sorted(processed) == [1, 2, 3]


async def test_scan_once_passes_correct_channels_and_max_attempts(monkeypatch):
    """list_pending_call_ids 에 _REALTIME_CHANNELS 와 MAX_ATTEMPTS 가 전달된다."""
    repo = FakeRepo(pending=[])
    scanner, _ = _make_scanner(repo, monkeypatch)

    await scanner.scan_once()

    assert len(repo.list_calls) == 1
    channels_arg, max_attempts_arg = repo.list_calls[0]
    assert channels_arg == _REALTIME_CHANNELS
    assert max_attempts_arg == MAX_ATTEMPTS


async def test_scan_once_no_pending_does_nothing(monkeypatch):
    """미처리 행이 없으면 process() 는 호출되지 않는다."""
    repo = FakeRepo(pending=[])
    scanner, processed = _make_scanner(repo, monkeypatch)

    await scanner.scan_once()

    assert processed == []


async def test_scan_once_process_exception_does_not_abort_remaining(monkeypatch):
    """한 id 처리가 예외를 던져도 나머지 id 는 계속 처리된다."""
    repo = FakeRepo(pending=[10, 20, 30])
    processed: list[int] = []

    async def flaky_process(call_history_id: int, **_kw) -> None:
        if call_history_id == 20:
            raise RuntimeError("boom")
        processed.append(call_history_id)

    monkeypatch.setattr(catchup_mod, "process", flaky_process)
    scanner = CatchupScanner(repo=repo)

    await scanner.scan_once()  # 예외가 scan_once 밖으로 전파되지 않아야 한다

    assert sorted(processed) == [10, 30]


async def test_scan_once_repo_exception_propagates(monkeypatch):
    """list_pending_call_ids 자체가 실패하면 예외가 호출자에게 전파된다."""
    processed: list[int] = []

    async def spy_process(call_history_id: int, **_kw) -> None:  # pragma: no cover
        processed.append(call_history_id)

    monkeypatch.setattr(catchup_mod, "process", spy_process)

    class BoomRepo:
        def list_pending_call_ids(self, channels, max_attempts):
            raise RuntimeError("db down")

    scanner = CatchupScanner(repo=BoomRepo())

    with pytest.raises(RuntimeError, match="db down"):
        await scanner.scan_once()

    assert processed == []
