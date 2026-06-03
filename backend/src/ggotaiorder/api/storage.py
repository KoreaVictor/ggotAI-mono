"""가게전화 음성 파일 Storage 적재 추상화."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Protocol
from uuid import uuid4

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)

AUDIO_BUCKET = "call-audio"


class AudioStorage(Protocol):
    """음성 파일 저장 계약."""

    def upload_audio(self, data: bytes, shop_key: int, filename: str) -> str: ...


class SupabaseAudioStorage:
    """Supabase Storage 기반 구현. 객체 경로 `{shop_key}/{uuid}{ext}` 반환."""

    def upload_audio(self, data: bytes, shop_key: int, filename: str) -> str:
        ext = PurePosixPath(filename).suffix or ".bin"
        object_name = f"{shop_key}/{uuid4().hex}{ext}"
        get_client().storage.from_(AUDIO_BUCKET).upload(object_name, data)
        return object_name
