"""싱글턴 순차 RPA 제어.

PRD 6-5/8-4: asyncio.Lock()으로 단 하나의 RPA만 순차 실행. 관리 프로그램 창을
찾으면 GUI 입력, 못 찾으면 엑셀(.xlsx)+텍스트 영수증 백업을 생성한다. 완료 후
rpa_status를 'success'(자동입력)/'manual'(미구동→백업, 수동입력 필요)/'fail'(구동
중 입력 실패)로 마킹하고, 동일 outcome으로 주문별 알림을 발송한다. 실제 GUI 입력은
ProgramAutomator(Protocol) 뒤로 추상화한다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from ggotaiorder.config import load_config
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.rpa.automator import ProgramAutomator
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.program_settings import load_program_settings
from ggotaiorder.rpa.backup import BackupWriter
from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.repository import RpaRepository, SupabaseRpaRepository

logger = logging.getLogger(__name__)

# 다중 채널 충돌 방지용 싱글턴 락 (PRD 8-4)
_rpa_lock = asyncio.Lock()


# RPA 처리 결과(=rpa_status & 알림 outcome)
OUTCOME_SUCCESS = "success"  # 관리 프로그램에 자동입력 완료
OUTCOME_MANUAL = "manual"    # 프로그램 미구동 → 백업 생성, 사장님 수동입력 필요
OUTCOME_FAIL = "fail"        # 프로그램 구동 중이나 입력 실패 → 백업 생성(진짜 오류)


async def _default_notify(order: RpaOrder, outcome: str) -> None:
    """기본 알림: notifier로 주문별(count=1) 결과 발송."""
    await notifier_send(order.shop_key, channel=order.channel, count=1, outcome=outcome)


async def enqueue(
    order_detail_id: int,
    *,
    repo: RpaRepository | None = None,
    automator: ProgramAutomator | None = None,
    backup: BackupWriter | None = None,
    notify: Callable[[RpaOrder, str], Awaitable[None]] | None = None,
) -> None:
    """order_details 1건을 전산 프로그램에 입력한다 (락 순차).

    - 프로그램 구동 + 입력 성공 → 'success'
    - 프로그램 미구동 → 백업 생성 → 'manual'(수동입력 필요, 오류 아님)
    - 프로그램 구동 중 입력 예외 → 백업 생성 → 'fail'(진짜 오류)
    완료 후 rpa_status 마킹 + 주문별 알림. 호출자 보호를 위해 전체를 try/except.
    """
    cfg = load_config()
    repo = repo or SupabaseRpaRepository()
    if automator is None:
        settings = await asyncio.to_thread(
            load_program_settings, cfg.shop_key, cfg.aes_encryption_key
        )
        automator = build_automator(
            settings,
            debug_port=cfg.flowernt_debug_port,
            profile_dir=str(cfg.rpa_profile_dir),
            chrome_path=str(cfg.rpa_chrome_path),
        )
    backup = backup or BackupWriter(cfg.rpa_backup_dir)
    notify = notify or _default_notify

    try:
        async with _rpa_lock:
            order = await asyncio.to_thread(repo.get_order, order_detail_id)
            if order is None:
                logger.warning("RPA 대상 주문 없음 id=%s", order_detail_id)
                return

            if await asyncio.to_thread(automator.is_program_running):
                try:
                    await asyncio.to_thread(automator.input_order, order)
                    outcome = OUTCOME_SUCCESS
                except Exception:
                    logger.exception("관리 프로그램 입력 실패 id=%s", order_detail_id)
                    await asyncio.to_thread(backup.write, order)
                    outcome = OUTCOME_FAIL
            else:
                logger.info("관리 프로그램 미구동 — 백업 생성(수동입력) id=%s", order_detail_id)
                await asyncio.to_thread(backup.write, order)
                outcome = OUTCOME_MANUAL

            await asyncio.to_thread(repo.set_rpa_status, order_detail_id, outcome)
            await notify(order, outcome)
    except Exception:
        logger.exception("RPA enqueue 처리 실패 id=%s", order_detail_id)
