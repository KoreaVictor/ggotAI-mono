"""개인화 알림 발송 (스텁).

PRD 6-6: setting_info.use_notification 확인 → 수신번호 결정
(notification_phone_number ?? member_info.mobile_number) → 템플릿
({channel}/{count} 치환) → 카카오 알림톡/문자 발송 + 이력 기록.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def render_template(template: str, channel: str, count: int) -> str:
    """템플릿의 {channel}/{count} 변수를 실제 값으로 치환한다."""
    return template.replace("{channel}", channel).replace("{count}", str(count))


async def send(channel: str, count: int, success: bool) -> None:
    """[스텁] RPA 결과 알림을 발송한다.

    TODO(후속):
      1. setting_info 조회 (use_notification 'N'이면 종료)
      2. 수신번호 결정(notification_phone_number ?? member_info.mobile_number)
      3. rpa_success_message / rpa_fail_message 선택 후 render_template
      4. 카카오 알림톡/문자 API(httpx) 발송 + 이력 기록
    """
    logger.warning(
        "[STUB] notifier.send(channel=%s, count=%s, success=%s)",
        channel, count, success,
    )
