"""catch-up 스캔: 서버 재시작 또는 Realtime 누락으로 미처리된 행을 재처리.

Realtime 리스너가 INSERT 이벤트를 놓쳤거나 서버가 다운된 사이에 쌓인
is_processed=NULL 행을 주기적으로 조회해 pipeline.process 로 넘긴다.

채널 필터(``_REALTIME_CHANNELS``)와 최대 시도 횟수(``MAX_ATTEMPTS``)는
engine 에서 import — 단일 출처(single source of truth).
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.pipeline.engine import MAX_ATTEMPTS, _REALTIME_CHANNELS, process
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository

logger = logging.getLogger(__name__)


class CatchupScanner:
    """미처리 수집 이력 행을 한 번 스캔하여 처리 파이프라인에 투입한다.

    Parameters
    ----------
    repo:
        OrderRepository 구현체. 미지정 시 SupabaseOrderRepository 를 사용한다
        (테스트는 fake 주입).
    """

    def __init__(self, repo: OrderRepository | None = None) -> None:
        self._repo = repo or SupabaseOrderRepository()

    async def scan_once(self) -> int:
        """is_processed=NULL && attempts < MAX_ATTEMPTS 인 행을 모두 처리한다.

        list_pending_call_ids 가 예외를 던지면 그대로 전파한다.
        개별 process() 예외는 흡수하고 나머지 id 처리를 계속한다.
        처리한 id 수를 반환한다(미처리 행이 없으면 0).
        """
        ids = await asyncio.to_thread(
            self._repo.list_pending_call_ids, _REALTIME_CHANNELS, MAX_ATTEMPTS
        )
        if not ids:
            return 0

        logger.info("catch-up 스캔: 미처리 %s건 처리 시작", len(ids))
        for call_history_id in ids:
            try:
                await process(call_history_id, repo=self._repo)
            except Exception:  # noqa: BLE001
                logger.exception("catch-up 처리 실패 id=%s — 계속 진행", call_history_id)
        logger.info("catch-up 스캔 완료: %s건", len(ids))
        return len(ids)
