"""Supabase 세션 계측 테스트.

WinError 10035(httpx.ReadError)가 이틀에 39건 났는데 원인을 못 잡았다. 통제 실험
3회 중 1회만 재현됐고 HTTP/2 가설은 지지받지 못했다(유휴 30·60초 각각 무결).

그래서 실제 발생 순간의 정황을 남긴다 — 직전 성공 이후 경과 시간과 그 순간 동시
진행 중이던 요청 수. 이 둘이면 "유휴 때문인가 / 동시성 때문인가"가 다음 발생 한
번으로 갈린다. **동작은 절대 바꾸지 않는다**(관측 전용).
"""

from __future__ import annotations

import threading

import pytest

from ggotaiorder.core.supabase_client import _instrument


class FakeSession:
    """httpx.Client 대역 — send 만 흉내낸다."""

    def __init__(self, raises=None, result="RESP"):
        self.raises = raises
        self.result = result
        self.calls = 0

    def send(self, request, **kwargs):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.result


def test_success_returns_unchanged_and_logs_nothing(caplog):
    session = _instrument(FakeSession())

    with caplog.at_level("ERROR"):
        got = session.send("REQ")

    assert got == "RESP"           # 반환값 그대로
    assert caplog.text == ""       # 정상 경로는 조용해야 한다


def test_failure_reraises_same_exception(caplog):
    boom = OSError("[WinError 10035] 비동기 소켓 작업")
    session = _instrument(FakeSession(raises=boom))

    with caplog.at_level("ERROR"):
        with pytest.raises(OSError) as excinfo:
            session.send("REQ")

    assert excinfo.value is boom   # 삼키지도, 바꾸지도 않는다


def test_failure_logs_idle_gap_and_inflight(caplog):
    session = _instrument(FakeSession(raises=OSError("[WinError 10035]")))

    with caplog.at_level("ERROR"):
        with pytest.raises(OSError):
            session.send("REQ")

    assert "직전 성공" in caplog.text
    assert "동시 진행" in caplog.text
    assert "10035" in caplog.text


def test_inflight_counts_concurrent_requests(caplog):
    """동시 진행 수가 실제로 세어지는지 — 한 요청을 붙잡아 둔 채 다른 하나를 실패시킨다.

    이 값이 정확해야 다음 발생 때 "동시성 탓인가"를 판정할 수 있다.
    """
    started = threading.Event()
    release = threading.Event()

    class HoldingSession:
        def send(self, request, **kwargs):
            if request == "HOLD":
                started.set()
                release.wait(timeout=5)
                return "RESP"
            raise OSError("[WinError 10035]")

    session = _instrument(HoldingSession())
    holder = threading.Thread(target=lambda: session.send("HOLD"))
    holder.start()
    assert started.wait(timeout=5)

    try:
        with caplog.at_level("ERROR"):
            with pytest.raises(OSError):
                session.send("REQ")   # 붙잡힌 요청과 겹친 상태
    finally:
        release.set()
        holder.join(timeout=5)

    assert "동시 진행 2" in caplog.text


def test_inflight_decrements_after_failure(caplog):
    """실패해도 카운터가 새지 않아야 한다 — 연속 실패 2회의 동시 진행 수는 둘 다 1."""
    session = _instrument(FakeSession(raises=OSError("[WinError 10035]")))

    with caplog.at_level("ERROR"):
        for _ in range(2):
            with pytest.raises(OSError):
                session.send("REQ")

    assert caplog.text.count("동시 진행 1") == 2
