"""알림 발송 설정 조회: setting_info + member_info(폴백 번호)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class NotificationSettings:
    use_notification: str
    notification_phone_number: Optional[str]
    rpa_success_message: str
    rpa_fail_message: str
    fallback_mobile: Optional[str]


class NotifierRepository(Protocol):
    """알림 발송이 필요로 하는 설정 조회 계약."""

    def get_settings(self, shop_key: int) -> Optional[NotificationSettings]: ...


class SupabaseNotifierRepository:
    """Supabase 기반 NotifierRepository 구현."""

    def get_settings(self, shop_key: int) -> Optional[NotificationSettings]:
        client = get_client()
        setting = (
            client.table("setting_info")
            .select(
                "use_notification, notification_phone_number, "
                "rpa_success_message, rpa_fail_message"
            )
            .eq("shop_key", shop_key)
            .limit(1)
            .execute()
        )
        if not setting.data:
            return None
        row = setting.data[0]

        member = (
            client.table("member_info")
            .select("mobile_number")
            .eq("id", shop_key)
            .limit(1)
            .execute()
        )
        fallback_mobile = member.data[0]["mobile_number"] if member.data else None

        return NotificationSettings(
            use_notification=row.get("use_notification") or "N",
            notification_phone_number=row.get("notification_phone_number"),
            rpa_success_message=row.get("rpa_success_message") or "",
            rpa_fail_message=row.get("rpa_fail_message") or "",
            fallback_mobile=fallback_mobile,
        )
