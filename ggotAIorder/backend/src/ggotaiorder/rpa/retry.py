"""manual(미구동) RPA 주문 자동 재시도 스캔.

'manual'은 RPA 입력 시점에 관리 프로그램(전용 Chrome)이 미구동이라 백업만
남고 등록이 안 된 상태다(프로그램 미구동 = 제출 자체가 없었으므로 중복등록
위험 없음 → 재시도 안전). 'fail'(구동 중 입력 예외)은 부분등록 가능성이 있어
자동재시도 대상이 아니다.

주기적으로 'manual' 주문을 다시 enqueue 한다. 무한재시도를 막기 위해 재시도
전에 rpa_attempts 를 올리고, 상한(RPA_MAX_ATTEMPTS)에 도달하면 더는 집지 않는다
(상한 초과분은 사장님 수동입력 대상으로 남는다).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from ggotaiorder.rpa.repository import RpaRepository, SupabaseRpaRepository
from ggotaiorder.rpa.singleton_macro import enqueue as default_enqueue

logger = logging.getLogger(__name__)

# manual 주문 최대 자동재시도 횟수(5분 주기 × 5회 ≈ 25분). 초과 시 수동입력으로 남김.
RPA_MAX_ATTEMPTS = 5


class RpaRetryScanner:
    """rpa_status='manual' 주문을 한 번 스캔해 다시 RPA 입력을 시도한다.

    repo/enqueue 미지정 시 실제 구현을 쓴다(테스트는 fake 주입).
    """

    def __init__(
        self,
        enqueue_fn: Callable[[int], Awaitable[None]] | None = None,
        repo: RpaRepository | None = None,
        shop_key: int | None = None,
    ) -> None:
        self._repo = repo or SupabaseRpaRepository()
        self._enqueue = enqueue_fn or default_enqueue
        # None 이면 첫 scan_once() 에서 config 로부터 해석/캐시한다(테스트는 명시 주입).
        self._shop_key = shop_key

    async def scan_once(self) -> int:
        """manual && rpa_attempts < 상한 인 내 가게 주문을 모두 재시도한다.

        시도 전 rpa_attempts 를 올린다(상한 적용). 개별 enqueue 예외는 흡수하고
        나머지를 계속 처리한다. 시도한 건수를 반환한다(미대상이면 0).
        """
        if self._shop_key is None:
            from ggotaiorder.config import load_config

            self._shop_key = load_config().shop_key

        ids = await asyncio.to_thread(
            self._repo.list_manual_order_ids, RPA_MAX_ATTEMPTS, self._shop_key
        )
        if not ids:
            return 0

        logger.info("RPA 재시도 스캔: manual %s건 재시도 시작", len(ids))
        for order_detail_id in ids:
            try:
                await asyncio.to_thread(
                    self._repo.increment_rpa_attempts, order_detail_id
                )
                await self._enqueue(order_detail_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "RPA 재시도 실패 id=%s — 계속 진행", order_detail_id
                )
        logger.info("RPA 재시도 스캔 완료: %s건", len(ids))
        return len(ids)
