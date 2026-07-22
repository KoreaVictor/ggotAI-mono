"""supabase-py 클라이언트 (프로세스 내 싱글턴).

서비스 롤 키를 사용한다(백엔드 전용). create_client 자체는 네트워크를
발생시키지 않으며, 실제 쿼리 시점에 연결된다.
"""

from __future__ import annotations

import functools
import logging
import threading
import time

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


def get_client(cfg: Config | None = None) -> Client:
    """싱글턴 Supabase 클라이언트를 반환한다."""
    global _client
    if _client is None:
        cfg = cfg or load_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        # postgrest 세션은 지연 생성이라 여기서 한 번 건드려 만든 뒤 계측한다.
        _instrument(_client.postgrest.session)
    return _client


def reset_client() -> None:
    """테스트 격리를 위해 싱글턴을 초기화한다."""
    global _client
    _client = None
