"""가게전화 업로드 인입 오케스트레이션: 샵 판별 → Storage 적재 → call_history INSERT."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ggotaiorder.api.repository import IngestRepository
from ggotaiorder.api.storage import AudioStorage

logger = logging.getLogger(__name__)


async def ingest_gate_phone(
    *,
    file_bytes: bytes,
    filename: str,
    caller_number: str,
    call_duration: int,
    user_phone_number: str,
    repo: IngestRepository,
    storage: AudioStorage,
) -> Optional[int]:
    """가게전화 1건을 인입한다.

    샵을 판별하지 못하면 None(라우트가 400). 성공 시 새 call_history_id.
    """
    shop = repo.find_shop_by_phone(user_phone_number)
    if shop is None:
        logger.warning("샵 판별 실패 — user_phone_number=%s", user_phone_number)
        return None

    object_name = storage.upload_audio(file_bytes, shop.shop_key, filename)
    now = datetime.now()
    record = {
        "channel_order": "가게전화",
        "channel_classification": user_phone_number,
        "customer_phone_number": caller_number,
        "shop_key": shop.shop_key,
        "shop_name": shop.shop_name,
        "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"),
        "duration_seconds": call_duration,
        "audio_file_name": object_name,
        "is_order": "N",
    }
    return repo.insert_call_history(record)
