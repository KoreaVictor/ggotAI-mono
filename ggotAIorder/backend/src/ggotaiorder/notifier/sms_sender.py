"""개인화 알림 발송.

PRD 6-6: setting_info.use_notification 확인 → 수신번호 결정
(notification_phone_number ?? member_info.mobile_number) → 템플릿
({channel}/{count} 치환) → 제공사 추상화로 발송. 결과는 로그로 기록.
"""

from __future__ import annotations

import asyncio
import logging
import os

from ggotaiorder.notifier.provider import NotificationProvider, make_provider
from ggotaiorder.notifier.repository import NotifierRepository, SupabaseNotifierRepository

logger = logging.getLogger(__name__)


def render_template(template: str, channel: str, count: int) -> str:
    """템플릿의 {channel}/{count} 변수를 실제 값으로 치환한다."""
    return template.replace("{channel}", channel).replace("{count}", str(count))


def _mask(phone: str) -> str:
    """로그용 전화번호 마스킹(뒤 4자리만 노출)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


# RPA 처리 결과 → 알림 문구 매핑. 알 수 없는 값은 보수적으로 실패 문구로 폴백.
_OUTCOME_SUCCESS = "success"
_OUTCOME_MANUAL = "manual"
_OUTCOME_FAIL = "fail"


def _template_for(settings: "object", outcome: str) -> str:
    """outcome(success/manual/fail)에 해당하는 알림 문구를 고른다."""
    if outcome == _OUTCOME_SUCCESS:
        return settings.rpa_success_message
    if outcome == _OUTCOME_MANUAL:
        return settings.rpa_manual_message
    return settings.rpa_fail_message


# outcome → 알림톡 템플릿 코드 env 이름(우선순위 순).
# provider 중립 NOTIFY_TEMPLATE_CODE_* 를 우선 쓰고, 기존 IWINV_TEMPLATE_CODE_* 는
# 하위호환 폴백으로 유지한다.
_TEMPLATE_CODE_ENV = {
    _OUTCOME_SUCCESS: ("NOTIFY_TEMPLATE_CODE_SUCCESS", "IWINV_TEMPLATE_CODE_SUCCESS"),
    _OUTCOME_MANUAL: ("NOTIFY_TEMPLATE_CODE_MANUAL", "IWINV_TEMPLATE_CODE_MANUAL"),
    _OUTCOME_FAIL: ("NOTIFY_TEMPLATE_CODE_FAIL", "IWINV_TEMPLATE_CODE_FAIL"),
}


def _template_code_for(outcome: str) -> str | None:
    """outcome에 해당하는 승인된 알림톡 templateCode(env)를 읽는다."""
    for env_name in _TEMPLATE_CODE_ENV.get(outcome, ()):
        value = os.getenv(env_name)
        if value:
            return value
    return None


async def send(
    shop_key: int,
    channel: str,
    count: int,
    outcome: str,
    *,
    repo: NotifierRepository | None = None,
    provider: NotificationProvider | None = None,
) -> bool:
    """RPA 결과 알림을 발송한다.

    outcome: 'success'(자동입력 성공) / 'manual'(백업 생성, 수동입력 필요) /
    'fail'(자동입력 실패). 각각 rpa_success/manual/fail_message 로 발송한다.
    실제 발송 시 True, 스킵/실패 시 False.
    """
    repo = repo or SupabaseNotifierRepository()
    provider = provider or make_provider()

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

    template = _template_for(settings, outcome)
    text = render_template(template, channel, count)
    if not text.strip():
        logger.warning("빈 메시지 — 발송 스킵 shop_key=%s", shop_key)
        return False

    template_code = _template_code_for(outcome)
    variables = {"건수": str(count)}
    if getattr(provider, "requires_template_code", False) and not template_code:
        logger.info(
            "알림톡 templateCode 없음(outcome=%s) — 발송 스킵 shop_key=%s",
            outcome,
            shop_key,
        )
        return False

    try:
        await asyncio.to_thread(
            provider.send_message,
            recipient,
            text,
            template_code=template_code,
            variables=variables,
        )
    except Exception:
        logger.exception("알림 발송 실패 shop_key=%s to=%s", shop_key, _mask(recipient))
        return False

    logger.info(
        "알림 발송 성공 shop_key=%s to=%s outcome=%s", shop_key, _mask(recipient), outcome
    )
    return True
