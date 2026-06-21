"""setting_info → RpaProgramSettings 로딩(비밀번호 복호는 백엔드 내부에서만)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ggotaiorder.core.crypto import decrypt
from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RpaProgramSettings:
    program_type: str          # 'flowernt' | 'roseweb' | 'etc' | ''
    url: str | None
    login_id: str | None
    login_password: str | None  # 복호된 평문(백엔드 내부)
    enabled: bool
    auto_submit: bool


def parse_settings_row(row: dict | None, aes_key: str) -> RpaProgramSettings | None:
    if not row:
        return None
    pw_blob = row.get("rpa_login_password")
    login_password = None
    if pw_blob:
        try:
            login_password = decrypt(pw_blob, aes_key)
        except Exception as exc:
            logger.warning(
                "rpa_login_password 복호 실패(%s) — 자격증명 없음으로 처리",
                type(exc).__name__,
            )
            login_password = None
    return RpaProgramSettings(
        program_type=(row.get("rpa_program_type") or "").strip(),
        url=row.get("rpa_program_url") or None,
        login_id=row.get("rpa_login_id") or None,
        login_password=login_password,
        enabled=(row.get("rpa_enabled") or "N") == "Y",
        # 자동등록은 가장 공격적 동작 — 미설정/NULL이면 안전하게 끈다(DB 기본값 'Y'가 실제 기본).
        auto_submit=(row.get("rpa_auto_submit") or "N") == "Y",
    )


def load_program_settings(shop_key: int, aes_key: str) -> RpaProgramSettings | None:
    """setting_info 한 행을 읽어 RpaProgramSettings로 변환."""
    res = (
        get_client()
        .table("setting_info")
        .select(
            "rpa_program_type, rpa_program_url, rpa_login_id, "
            "rpa_login_password, rpa_enabled, rpa_auto_submit"
        )
        .eq("shop_key", shop_key)
        .limit(1)
        .execute()
    )
    row = res.data[0] if res.data else None
    return parse_settings_row(row, aes_key)
