"""supabase-py 클라이언트 (프로세스 내 싱글턴).

서비스 롤 키를 사용한다(백엔드 전용). create_client 자체는 네트워크를
발생시키지 않으며, 실제 쿼리 시점에 연결된다.
"""

from __future__ import annotations

import functools
import logging
import threading
import time

import httpx
from supabase import Client, create_client

from ggotaiorder.config import Config, load_config

logger = logging.getLogger(__name__)

_client: Client | None = None


def _instrument(session):
    """전송 실패 순간의 정황을 남긴다. **동작은 바꾸지 않는다**(관측 전용).

    ``httpx.ReadError: [WinError 10035]`` 가 이틀에 39건 났는데 원인을 못 잡았다.
    통제 실험 3회 중 재현은 1회뿐이었고, HTTP/2 공유 소켓 가설은 지지받지 못했다
    (유휴 30초·60초 각각 320요청 무결). 남은 후보는 "유휴 뒤 첫 요청"과 "동시성"
    인데, 로그에 그 둘을 가릴 정보가 없어 판정이 불가능했다.

    그래서 실패할 때만 두 값을 남긴다 — 직전 성공 이후 경과 시간, 그 순간 동시
    진행 중이던 요청 수. 다음 실제 발생 한 번이면 갈린다.
    """
    state = {"last_ok": time.monotonic(), "inflight": 0}
    lock = threading.Lock()
    original = session.send

    @functools.wraps(original)
    def send(request, **kwargs):
        with lock:
            state["inflight"] += 1
            inflight = state["inflight"]
            idle = time.monotonic() - state["last_ok"]
        try:
            response = original(request, **kwargs)
        except Exception as exc:
            logger.error(
                "Supabase 전송 실패 — 직전 성공 이후 %.1fs, 동시 진행 %d, %s: %s",
                idle, inflight, type(exc).__name__, exc,
            )
            raise
        else:
            with lock:
                state["last_ok"] = time.monotonic()
            return response
        finally:
            with lock:
                state["inflight"] -= 1

    session.send = send
    return session


def _force_http1(session: httpx.Client) -> None:
    """httpx 세션을 HTTP/1.1 전송으로 교체한다(WinError 10035 대책).

    WinError 10035(WSAEWOULDBLOCK)는 httpcore HTTP/2 동기 백엔드의 Windows read
    레이스에서 나고, http2 단일 공유 소켓이 저장된 read 예외를 이후 요청에 재전파해
    같은 순간 여러 요청을 동시 실패시킨다(증폭). http2 를 끄면 요청별 h1 커넥션 풀로
    바뀌어 두 문제가 함께 사라진다. 헤더·인증·base_url 은 Client 레벨 상태라 전송
    계층과 무관하므로, _transport 만 교체하면 인증을 깨지 않고 프로토콜만 바꾼다.
    """
    old = getattr(session, "_transport", None)
    session._transport = httpx.HTTPTransport(http2=False)
    if old is not None:
        try:
            old.close()
        except Exception:  # noqa: BLE001 - best-effort 정리
            logger.debug("이전 전송 close 중 예외(무시)", exc_info=True)


def get_client(cfg: Config | None = None) -> Client:
    """싱글턴 Supabase 클라이언트를 반환한다."""
    global _client
    if _client is None:
        cfg = cfg or load_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        # postgrest 세션은 지연 생성이라 여기서 한 번 건드려 만든 뒤 계측한다.
        _instrument(_client.postgrest.session)
        # http2 공유 소켓의 WinError 10035 회피 — h1 전송으로 교체.
        _force_http1(_client.postgrest.session)
    return _client


def reset_client() -> None:
    """테스트 격리를 위해 싱글턴을 초기화한다."""
    global _client
    _client = None
