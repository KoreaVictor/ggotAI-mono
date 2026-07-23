"""Supabase postgrest 세션 HTTP/1.1 강제 전환 테스트.

WinError 10035(WSAEWOULDBLOCK)는 httpcore HTTP/2 동기 백엔드의 Windows read
레이스에서 나고, http2 단일 공유 소켓이 저장된 read 예외를 이후 요청에 재전파해
같은 순간 여러 요청을 동시 실패시킨다(증폭). http2 를 끄면 요청별 h1 커넥션으로
바뀌어 두 문제가 함께 사라진다. 전송 계층만 바꾸고 Client 레벨 상태(헤더·인증·
base_url)는 보존한다.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from ggotaiorder.core import supabase_client as mod
from ggotaiorder.core.supabase_client import _force_http1


def test_force_http1_disables_http2():
    client = httpx.Client(http2=True)
    try:
        assert client._transport._pool._http2 is True  # 전제 확인
        _force_http1(client)
        assert client._transport._pool._http2 is False
    finally:
        client.close()


def test_force_http1_preserves_client_config():
    """전송만 바꾸고 인증 헤더·base_url 은 그대로여야 한다(안 그러면 401)."""
    client = httpx.Client(
        http2=True,
        base_url="https://x.example",
        headers={"apikey": "secret-key"},
    )
    try:
        _force_http1(client)
        assert str(client.base_url) == "https://x.example"
        assert client.headers["apikey"] == "secret-key"
    finally:
        client.close()


def test_get_client_forces_http1_on_postgrest(monkeypatch):
    """싱글턴 생성 시 postgrest 세션이 HTTP/1.1 로 전환돼야 한다."""
    fake_session = httpx.Client(http2=True)

    fake_client = SimpleNamespace(postgrest=SimpleNamespace(session=fake_session))
    monkeypatch.setattr(mod, "create_client", lambda url, key: fake_client)
    monkeypatch.setattr(
        mod,
        "load_config",
        lambda: SimpleNamespace(
            supabase_url="https://x.example",
            supabase_service_role_key="k",
        ),
    )
    mod.reset_client()
    try:
        c = mod.get_client()
        assert c.postgrest.session._transport._pool._http2 is False
    finally:
        mod.reset_client()
        fake_session.close()
