"""싱글턴 순차 RPA 제어.

PRD 6-5/8-4: asyncio.Lock()으로 단 하나의 RPA만 순차 실행. 관리 프로그램 창을
찾으면 GUI 입력, 못 찾으면 엑셀(.xlsx)+텍스트 영수증 백업을 생성한다. 완료 후
rpa_status를 'success'/'fail'로 마킹하고 주문별 알림을 발송한다. 실제 GUI 입력은
ProgramAutomator(Protocol) 뒤로 추상화한다.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.config import load_config
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.rpa.automator import ProgramAutomator, WindowsProgramAutomator
from ggotaiorder.rpa.backup import BackupWriter
from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.repository import RpaRepository, SupabaseRpaRepository

logger = logging.getLogger(__name__)

# 다중 채널 충돌 방지용 싱글턴 락 (PRD 8-4)
_rpa_lock = asyncio.Lock()


async def _default_notify(order: RpaOrder, success: bool) -> None:
    """기본 알림: notifier로 주문별(count=1) 결과 발송."""
    await notifier_send(order.shop_key, channel=order.channel, count=1, success=success)


async def enqueue(
    order_detail_id: int,
    *,
    repo: RpaRepository | None = None,
    automator: ProgramAutomator | None = None,
    backup: BackupWriter | None = None,
    notify=None,
) -> None:
    """order_details 1건을 전산 프로그램에 입력한다 (락 순차).

    구동 중이면 GUI 입력 → success, 입력 실패/미구동이면 백업 → fail.
    완료 후 rpa_status 마킹 + 주문별 알림. 호출자 보호를 위해 전체를 try/except.
    """
    repo = repo or SupabaseRpaRepository()
    automator = automator or WindowsProgramAutomator()
    backup = backup or BackupWriter(load_config().rpa_backup_dir)
    notify = notify or _default_notify

    try:
        async with _rpa_lock:
            order = await asyncio.to_thread(repo.get_order, order_detail_id)
            if order is None:
                logger.warning("RPA 대상 주문 없음 id=%s", order_detail_id)
                return

            success = False
            if await asyncio.to_thread(automator.is_program_running):
                try:
                    await asyncio.to_thread(automator.input_order, order)
                    success = True
                except Exception:
                    logger.exception("관리 프로그램 입력 실패 id=%s", order_detail_id)
                    await asyncio.to_thread(backup.write, order)
            else:
                logger.info("관리 프로그램 미구동 — 백업 생성 id=%s", order_detail_id)
                await asyncio.to_thread(backup.write, order)

            status = "success" if success else "fail"
            await asyncio.to_thread(repo.set_rpa_status, order_detail_id, status)
            await notify(order, success)
    except Exception:
        logger.exception("RPA enqueue 처리 실패 id=%s", order_detail_id)
