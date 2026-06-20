"""수집엔진 생존 신호(heartbeat).

오케스트레이터가 주기적으로 engine_heartbeat 테이블에 last_seen 을 upsert 한다.
ggotAIya 상황판(get_dashboard RPC)이 최근 last_seen 으로 '가동중/중지됨'을 판정한다.
웹(브라우저)에서도 동작하도록, Electron 의존 없이 DB 신호로만 판단하게 하는 것이 목적.
"""

from __future__ import annotations

import logging

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


def record_heartbeat(shop_key: int, client=None) -> None:
    """engine_heartbeat 를 갱신한다.

    last_seen 은 RPC(record_engine_heartbeat) 안에서 DB 서버의 now() 로 기록한다.
    PC 시각을 보내면 PC-서버 시계차(관측상 수십 초) 때문에 상황판이 가동 중에도
    '중지됨'으로 오판할 수 있어, 쓰기·읽기 시각을 DB 서버 한쪽으로 통일한다.
    """
    c = client or get_client()
    c.rpc("record_engine_heartbeat", {"p_shop_key": shop_key}).execute()
