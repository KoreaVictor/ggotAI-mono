"""CatchupScanner 단위 테스트.

scan_once() 는 REALTIME_CHANNELS 집합과 MAX_ATTEMPTS 상한을 engine 에서 가져와
미처리(processed_at=NULL) 행을 repo.list_pending_call_ids 로 조회한 뒤
각 id 에 대해 process(call_history_id, repo=self._repo) 를 호출하고
처리 건수(int) 를 반환한다.
"""

from __future__ import annotations

import pytest

from ggotaiorder.pipeline import catchup
from ggotaiorder.pipeline import engine
from ggotaiorder.pipeline.catchup import CatchupScanner


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakeScanRepo:
    """list_pending_call_ids 를 흉내 내는 가짜 repo."""

    def __init__(self, pending: list[int]):
        self._pending = pending
        self.queried: list[tuple] = []

    def list_pending_call_ids(self, channels, max_attempts) -> list[int]:
        self.queried.append((channels, max_attempts))
        return list(self._pending)


# ---------------------------------------------------------------------------
# 스펙 필수 테스트
# ---------------------------------------------------------------------------

async def test_scan_once_processes_each_pending(monkeypatch):
    """미처리 행마다 process 가 한 번씩 호출되고, 반환값은 처리 건수이다.
    process 에 주입된 repo 가 실제로 전달되는지도 확인한다."""
    repo = FakeScanRepo([10, 11, 12])
    processed: list[int] = []
    repos_seen: list = []

    async def fake_process(call_history_id, repo=None):
        processed.append(call_history_id)
        repos_seen.append(repo)

    monkeypatch.setattr(catchup, "process", fake_process)

    scanner = CatchupScanner(repo=repo)
    count = await scanner.scan_once()

    assert processed == [10, 11, 12]
    assert count == 3
    channels, max_attempts = repo.queried[0]
    assert channels == engine.REALTIME_CHANNELS
    assert max_attempts == engine.MAX_ATTEMPTS

    # 주입한 repo 가 process 로 전달되는지 확인
    assert all(r is repo for r in repos_seen), "process 가 scanner 의 repo 를 받지 않았다"


async def test_scan_once_empty_returns_zero(monkeypatch):
    """미처리 행이 없으면 process 가 호출되지 않고 0 을 반환한다."""
    repo = FakeScanRepo([])

    async def fake_process(call_history_id, repo=None):
        raise AssertionError("미처리 행이 없으면 process가 호출되면 안 된다")

    monkeypatch.setattr(catchup, "process", fake_process)

    scanner = CatchupScanner(repo=repo)
    assert await scanner.scan_once() == 0


# ---------------------------------------------------------------------------
# 추가 테스트 — 예외 격리 및 repo 예외 전파
# ---------------------------------------------------------------------------

async def test_scan_once_process_exception_does_not_abort_remaining(monkeypatch):
    """한 id 처리가 예외를 던져도 나머지 id 는 계속 처리된다."""
    repo = FakeScanRepo([10, 20, 30])
    processed: list[int] = []

    async def flaky_process(call_history_id, repo=None):
        if call_history_id == 20:
            raise RuntimeError("boom")
        processed.append(call_history_id)

    monkeypatch.setattr(catchup, "process", flaky_process)
    scanner = CatchupScanner(repo=repo)

    count = await scanner.scan_once()  # 예외가 scan_once 밖으로 전파되지 않아야 한다

    assert sorted(processed) == [10, 30]
    assert count == 3  # 예외가 난 id 포함, 시도한 전체 건수를 반환


async def test_scan_once_repo_exception_propagates(monkeypatch):
    """list_pending_call_ids 자체가 실패하면 예외가 호출자에게 전파된다."""
    processed: list[int] = []

    async def spy_process(call_history_id, repo=None):  # pragma: no cover
        processed.append(call_history_id)

    monkeypatch.setattr(catchup, "process", spy_process)

    class BoomRepo:
        def list_pending_call_ids(self, channels, max_attempts):
            raise RuntimeError("db down")

    scanner = CatchupScanner(repo=BoomRepo())

    with pytest.raises(RuntimeError, match="db down"):
        await scanner.scan_once()

    assert processed == []
