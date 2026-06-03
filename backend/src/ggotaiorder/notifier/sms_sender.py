"""개인화 알림 발송.

PRD 6-6: setting_info.use_notification 확인 → 수신번호 결정
(notification_phone_number ?? member_info.mobile_number) → 템플릿
({channel}/{count} 치환) → 제공사 추상화로 발송. 결과는 로그로 기록.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.notifier.provider import HttpNotificationProvider, NotificationProvider
from ggotaiorder.notifier.repository import NotifierRepository, SupabaseNotifierRepository

logger = logging.getLogger(__name__)


def render_template(template: str, channel: str, count: int) -> str:
    """템플릿의 {channel}/{count} 변수를 실제 값으로 치환한다."""
    return template.replace("{channel}", channel).replace("{count}", str(count))


def _mask(phone: str) -> str:
    """로그용 전화번호 마스킹(뒤 4자리만 노출)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


async def send(
    shop_key: int,
    channel: str,
    count: int,
    success: bool,
    *,
    repo: NotifierRepository | None = None,
    provider: NotificationProvider | None = None,
) -> bool:
    """RPA 결과 알림을 발송한다. 실제 발송 시 True, 스킵/실패 시 False."""
    repo = repo or SupabaseNotifierRepository()
    provider = provider or HttpNotificationProvider()

    settings = await asyncio.to_thread(repo.get_settings, shop_key)
    if settings is None:
        logger.warning("알림 설정 없음 — 발송 스킵 shop_key=%s", shop_key)
        return False

    if settings.use_notification != "Y":
        logger.info("알림 비활성(use_notification=N) — 스킵 shop_key=%s", shop_key)
        return False

    recipient = settings.notification_phone_number or settings.fallback_mobile
    if not recipient:
        logger.warning("수신번호 없음 — 발송 스킵 shop_key=%s", shop_key)
        return False

    template = settings.rpa_success_message if success else settings.rpa_fail_message
    text = render_template(template, channel, count)

    try:
        await asyncio.to_thread(provider.send_message, recipient, text)
    except Exception:
        logger.exception("알림 발송 실패 shop_key=%s to=%s", shop_key, _mask(recipient))
        return False

    logger.info(
        "알림 발송 성공 shop_key=%s to=%s success=%s", shop_key, _mask(recipient), success
    )
    return True
