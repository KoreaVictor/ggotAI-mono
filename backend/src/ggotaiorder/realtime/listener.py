"""Supabase Realtime 감시 (스텁).

PRD 6-2: public.server_call_history 의 INSERT 이벤트를 24시간 구독하여
신규 행 발생 시 pipeline.process(call_history_id) 를 호출한다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RealtimeListener:
    """server_call_history INSERT 구독 리스너."""

    async def start(self) -> None:
        """[스텁] Realtime 채널 구독을 시작한다.

        TODO(후속): supabase.channel(...).on_postgres_changes(INSERT,
        table='server_call_history', callback=self._on_new_call) 구독.
        """
        logger.warning("[STUB] RealtimeListener.start() — 구독 미구현")

    async def stop(self) -> None:
        """[스텁] 구독을 해제한다."""
        logger.warning("[STUB] RealtimeListener.stop()")

    async def _on_new_call(self, payload: dict) -> None:
        """[스텁] 신규 행 콜백. payload에서 id를 추출해 파이프라인 호출.

        TODO(후속): call_history_id = payload['new']['id'];
        await pipeline.process(call_history_id)
        """
        logger.warning("[STUB] on_new_call_received: %s", payload)
