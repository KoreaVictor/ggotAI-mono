"""싱글턴 순차 RPA 제어 (스텁).

PRD 6-5: asyncio.Lock()으로 단 하나의 RPA만 순차 실행. 관리 프로그램 창을
찾지 못하면 엑셀(.xlsx)+텍스트 영수증 백업 생성. 완료 후 rpa_status를
'success'/'fail'로 마킹하고 notifier.send 호출.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 다중 채널 충돌 방지용 싱글턴 락 (PRD 8-4)
_rpa_lock = asyncio.Lock()


async def enqueue(order_detail_id: int) -> None:
    """[스텁] order_details 1건을 전산 프로그램에 입력한다 (락 순차).

    TODO(후속):
      - 관리 프로그램 창 탐색(pygetwindow)
      - 있으면 클립보드(pyperclip)+Tab 매크로 입력 → rpa_status='success'/'fail'
      - 없으면 엑셀(openpyxl)+텍스트 영수증 백업 생성
      - 완료 후 await notifier.send(channel, count, success)
    """
    async with _rpa_lock:
        logger.warning("[STUB] rpa.enqueue(order_detail_id=%s)", order_detail_id)
