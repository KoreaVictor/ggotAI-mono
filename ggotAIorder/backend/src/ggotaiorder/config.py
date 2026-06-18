"""환경설정(.env) 로딩 및 검증."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

_REQUIRED_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AES_ENCRYPTION_KEY",
    "GEMINI_API_KEY",
    "SHOP_KEY",
)


class ConfigError(RuntimeError):
    """필수 환경설정 누락/오류."""


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    aes_encryption_key: str
    gemini_api_key: str
    shop_key: int
    rpa_backup_dir: Path
    rpa_profile_dir: Path
    flowernt_debug_port: int


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """환경설정을 로딩해 검증된 Config를 반환한다.

    env가 None이면 backend/.env를 os.environ에 로딩한 뒤 os.environ을 사용한다.
    필수 키 누락/공백 또는 AES 키가 32바이트가 아니면 ConfigError.
    """
    if env is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(env_path)
        env = os.environ

    missing = [k for k in _REQUIRED_KEYS if not env.get(k)]
    if missing:
        raise ConfigError(f"필수 환경변수 누락/공백: {', '.join(missing)}")

    aes_key = env["AES_ENCRYPTION_KEY"]
    try:
        aes_key_byte_len = len(bytes.fromhex(aes_key))
    except ValueError:
        raise ConfigError("AES_ENCRYPTION_KEY 는 16진수(hex) 문자열이어야 합니다.")
    if aes_key_byte_len != 32:
        raise ConfigError(
            "AES_ENCRYPTION_KEY 는 hex 디코딩 시 정확히 32바이트(64 hex chars)여야 합니다."
        )

    try:
        shop_key = int(env["SHOP_KEY"])
    except ValueError:
        raise ConfigError("SHOP_KEY 는 정수여야 합니다.")

    backup_dir = env.get("RPA_BACKUP_DIR")
    rpa_backup_dir = (
        Path(backup_dir) if backup_dir
        else Path(__file__).resolve().parents[2] / "backups"
    )

    profile_dir = env.get("RPA_PROFILE_DIR")
    # 단일 PC(Windows) 배포 기본값 — 가게마다 RPA 전용 Chrome 프로필을 이 경로에 둔다.
    rpa_profile_dir = (
        Path(profile_dir) if profile_dir else Path(r"C:\ggotAI\rpa_profile")
    )
    try:
        flowernt_debug_port = int(env.get("RPA_DEBUG_PORT") or 9222)
    except ValueError:
        raise ConfigError("RPA_DEBUG_PORT 는 정수여야 합니다.")

    return Config(
        supabase_url=env["SUPABASE_URL"],
        supabase_anon_key=env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=env["SUPABASE_SERVICE_ROLE_KEY"],
        aes_encryption_key=aes_key,
        gemini_api_key=env["GEMINI_API_KEY"],
        shop_key=shop_key,
        rpa_backup_dir=rpa_backup_dir,
        rpa_profile_dir=rpa_profile_dir,
        flowernt_debug_port=flowernt_debug_port,
    )
