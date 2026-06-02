"""supabase-py 클라이언트 (프로세스 내 싱글턴).

서비스 롤 키를 사용한다(백엔드 전용). create_client 자체는 네트워크를
발생시키지 않으며, 실제 쿼리 시점에 연결된다.
"""

from __future__ import annotations

from supabase import Client, create_client

from ggotaiorder.config import Config, load_config

_client: Client | None = None


def get_client(cfg: Config | None = None) -> Client:
    """싱글턴 Supabase 클라이언트를 반환한다."""
    global _client
    if _client is None:
        cfg = cfg or load_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    return _client


def reset_client() -> None:
    """테스트 격리를 위해 싱글턴을 초기화한다."""
    global _client
    _client = None
