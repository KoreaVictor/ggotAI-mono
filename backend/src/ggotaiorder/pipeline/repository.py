"""주문 파이프라인 DB 접근 추상화.

OrderRepository(Protocol)로 계약을 고정하고, 실제 구현은 Supabase를 사용한다.
테스트는 FakeOrderRepository(tests)로 대체해 결정적으로 검증한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.pipeline.models import CallHistory

logger = logging.getLogger(__name__)


class OrderRepository(Protocol):
    """파이프라인이 필요로 하는 DB 연산 계약."""

    def get_call_history(self, call_history_id: int) -> CallHistory: ...

    def update_stt_text(self, call_history_id: int, text: str) -> None: ...

    def mark_processed(self, call_history_id: int, is_order: str) -> None: ...

    def increment_attempts(self, call_history_id: int) -> None: ...

    def list_pending_call_ids(
        self, channels: set[str], max_attempts: int
    ) -> list[int]: ...

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

    def mark_processed(self, call_history_id: int, is_order: str) -> None:
        get_client().table("server_call_history").update(
            {
                "is_order": is_order,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", call_history_id).execute()

    def increment_attempts(self, call_history_id: int) -> None:
        # PostgREST에 원자적 increment가 없어 read-modify-write 한다.
        # in-flight 가드가 동일 id 동시 처리를 막으므로 경합 없음(단일 PC).
        # (멀티 인스턴스로 확장 시엔 원자적 increment RPC가 필요 — 현재 단일 PC 전제.)
        res = (
            get_client()
            .table("server_call_history")
            .select("process_attempts")
            .eq("id", call_history_id)
            .single()
            .execute()
        )
        current = res.data.get("process_attempts") or 0
        get_client().table("server_call_history").update(
            {"process_attempts": current + 1}
        ).eq("id", call_history_id).execute()

    def list_pending_call_ids(
        self, channels: set[str], max_attempts: int
    ) -> list[int]:
        res = (
            get_client()
            .table("server_call_history")
            .select("id")
            .in_("channel_order", list(channels))
            .is_("processed_at", "null")
            .lt("process_attempts", max_attempts)
            .order("id")
            .execute()
        )
        return [r["id"] for r in res.data]

    def insert_order_details(self, payload: dict) -> int:
        res = get_client().table("order_details").insert(payload).execute()
        return res.data[0]["id"]

    def delete_audio(self, audio_file_name: Optional[str]) -> None:
        if not audio_file_name:
            return
        # TODO(다음 증분): Supabase Storage 버킷에서 실제 파일 삭제.
        logger.warning("[부분구현] delete_audio 미연동(no-op): %s", audio_file_name)
