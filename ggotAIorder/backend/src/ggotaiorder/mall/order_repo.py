"""쇼핑몰 주문 DB 접근: 중복검증·INSERT·발주확인 대상 조회/마킹."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import SMARTSTORE_CHANNEL, ConfirmTarget

logger = logging.getLogger(__name__)


@runtime_checkable
class MallOrderRepository(Protocol):
    """collector·confirm_scanner 가 필요로 하는 주문 DB 연산 계약."""

    def order_exists(self, shop_key: int, product_order_id: str) -> bool: ...

    def insert_call_history(self, record: dict) -> int: ...

    def insert_order_details(self, payload: dict) -> int: ...

    def list_confirmable(self, provider_marker: str) -> list[ConfirmTarget]: ...

    def mark_ack(self, order_id: int, status: str) -> None: ...

    def increment_ack_attempts(self, order_id: int) -> int: ...


class SupabaseMallOrderRepository:
    """Supabase 기반 MallOrderRepository 구현."""

    def order_exists(self, shop_key: int, product_order_id: str) -> bool:
        res = (
            get_client()
            .table("server_call_history")
            .select("id")
            .eq("shop_key", shop_key)
            .eq("channel_order", SMARTSTORE_CHANNEL)
            .eq("channel_classification", product_order_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def insert_call_history(self, record: dict) -> int:
        res = get_client().table("server_call_history").insert(record).execute()
        if not res.data:
            raise RuntimeError("server_call_history INSERT가 행을 반환하지 않았습니다.")
        return res.data[0]["id"]

    def insert_order_details(self, payload: dict) -> int:
        res = get_client().table("order_details").insert(payload).execute()
        if not res.data:
            raise RuntimeError("order_details INSERT가 행을 반환하지 않았습니다.")
        return res.data[0]["id"]

    def list_confirmable(self, provider_marker: str) -> list[ConfirmTarget]:
        """rpa_status='success' && mall_ack_status='pending' 이고, 연결된
        server_call_history.audio_file_name == provider_marker 인 대상 목록."""
        client = get_client()
        rows = (
            client.table("order_details")
            .select("id, shop_key, call_history_id, mall_ack_attempts")
            .eq("rpa_status", "success")
            .eq("mall_ack_status", "pending")
            .execute()
        )
        targets: list[ConfirmTarget] = []
        for row in rows.data or []:
            ch = (
                client.table("server_call_history")
                .select("channel_classification, audio_file_name")
                .eq("id", row["call_history_id"])
                .limit(1)
                .execute()
            )
            if not ch.data:
                continue
            c = ch.data[0]
            if c.get("audio_file_name") != provider_marker:
                continue
            targets.append(
                ConfirmTarget(
                    order_id=row["id"],
                    shop_key=row["shop_key"],
                    product_order_id=c.get("channel_classification") or "",
                    ack_attempts=row.get("mall_ack_attempts") or 0,
                )
            )
        return targets

    def mark_ack(self, order_id: int, status: str) -> None:
        (
            get_client()
            .table("order_details")
            .update({"mall_ack_status": status})
            .eq("id", order_id)
            .execute()
        )

    def increment_ack_attempts(self, order_id: int) -> int:
        """mall_ack_attempts 를 1 증가(읽기-수정-쓰기)하고 새 값을 반환한다."""
        client = get_client()
        cur = (
            client.table("order_details")
            .select("mall_ack_attempts")
            .eq("id", order_id)
            .limit(1)
            .execute()
        )
        attempts = 0
        if cur.data:
            attempts = cur.data[0].get("mall_ack_attempts") or 0
        new_value = attempts + 1
        client.table("order_details").update({"mall_ack_attempts": new_value}).eq(
            "id", order_id
        ).execute()
        return new_value
