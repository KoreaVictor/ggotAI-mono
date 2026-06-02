"""주문 파이프라인 DB 접근 추상화.

OrderRepository(Protocol)로 계약을 고정하고, 실제 구현은 Supabase를 사용한다.
테스트는 FakeOrderRepository(tests)로 대체해 결정적으로 검증한다.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.pipeline.models import CallHistory

logger = logging.getLogger(__name__)


class OrderRepository(Protocol):
    """파이프라인이 필요로 하는 DB 연산 계약."""

    def get_call_history(self, call_history_id: int) -> CallHistory: ...

    def update_stt_text(self, call_history_id: int, text: str) -> None: ...

    def set_is_order(self, call_history_id: int, value: str) -> None: ...

    def insert_order_details(self, payload: dict) -> int: ...

    def delete_audio(self, audio_file_name: Optional[str]) -> None: ...


class SupabaseOrderRepository:
    """Supabase 기반 OrderRepository 구현."""

    def get_call_history(self, call_history_id: int) -> CallHistory:
        res = (
            get_client()
            .table("server_call_history")
            .select("*")
            .eq("id", call_history_id)
            .single()
            .execute()
        )
        row = res.data
        return CallHistory(
            id=row["id"],
            shop_key=row["shop_key"],
            shop_name=row["shop_name"],
            customer_name=row.get("customer_name"),
            customer_phone_number=row.get("customer_phone_number"),
            stt_text=row.get("stt_text"),
            audio_file_name=row.get("audio_file_name"),
            channel_order=row.get("channel_order", "기타"),
        )

    def update_stt_text(self, call_history_id: int, text: str) -> None:
        get_client().table("server_call_history").update(
            {"stt_text": text}
        ).eq("id", call_history_id).execute()

    def set_is_order(self, call_history_id: int, value: str) -> None:
        get_client().table("server_call_history").update(
            {"is_order": value}
        ).eq("id", call_history_id).execute()

    def insert_order_details(self, payload: dict) -> int:
        res = get_client().table("order_details").insert(payload).execute()
        return res.data[0]["id"]

    def delete_audio(self, audio_file_name: Optional[str]) -> None:
        if not audio_file_name:
            return
        # TODO(다음 증분): Supabase Storage 버킷에서 실제 파일 삭제.
        logger.warning("[부분구현] delete_audio 미연동(no-op): %s", audio_file_name)
