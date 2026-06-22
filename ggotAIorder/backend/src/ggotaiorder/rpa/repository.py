"""RPA 엔진 DB 접근: 주문 조회(채널 조인)·상태 마킹."""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class RpaRepository(Protocol):
    """RPA 엔진이 필요로 하는 DB 연산 계약."""

    def get_order(self, order_detail_id: int) -> RpaOrder | None: ...

    def set_rpa_status(self, order_detail_id: int, status: str) -> None: ...

    def list_manual_order_ids(
        self, max_attempts: int, shop_key: int
    ) -> list[int]: ...

    def increment_rpa_attempts(self, order_detail_id: int) -> None: ...


class SupabaseRpaRepository:
    """Supabase 기반 RpaRepository 구현."""

    def get_order(self, order_detail_id: int) -> RpaOrder | None:
        client = get_client()
        res = (
            client.table("order_details")
            .select("*")
            .eq("id", order_detail_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]

        channel = ""
        ch = (
            client.table("server_call_history")
            .select("channel_order")
            .eq("id", row["call_history_id"])
            .limit(1)
            .execute()
        )
        if ch.data:
            channel = ch.data[0].get("channel_order") or ""

        quantity = row.get("quantity")
        price = row.get("price")
        return RpaOrder(
            order_detail_id=row["id"],
            shop_key=row["shop_key"],
            shop_name=row["shop_name"],
            channel=channel,
            customer_name=row.get("customer_name") or "",
            customer_phone_number=row.get("customer_phone_number") or "",
            product_name=row.get("product_name") or "",
            quantity=quantity if quantity is not None else 1,
            price=price if price is not None else 0,
            delivery_at=row.get("delivery_at"),
            delivery_place=row.get("delivery_place"),
            receiver_name=row.get("receiver_name"),
            receiver_phone_number=row.get("receiver_phone_number"),
            ribbon_sender=row.get("ribbon_sender"),
            ribbon_congratulations=row.get("ribbon_congratulations"),
            card_message=row.get("card_message"),
            delivery_at_text=row.get("delivery_at_text"),
            sang_divi=row.get("sang_divi"),
        )

    def set_rpa_status(self, order_detail_id: int, status: str) -> None:
        res = (
            get_client()
            .table("order_details")
            .update({"rpa_status": status})
            .eq("id", order_detail_id)
            .execute()
        )
        if not res.data:
            raise RuntimeError(
                f"order_details UPDATE(rpa_status) 응답이 없습니다 — id={order_detail_id}"
            )

    def list_manual_order_ids(self, max_attempts: int, shop_key: int) -> list[int]:
        """재시도 대상: rpa_status='manual' && rpa_attempts < 상한 인 내 가게 주문 id."""
        res = (
            get_client()
            .table("order_details")
            .select("id")
            .eq("shop_key", shop_key)
            .eq("rpa_status", "manual")
            .lt("rpa_attempts", max_attempts)
            .order("id")
            .execute()
        )
        return [row["id"] for row in (res.data or [])]

    def increment_rpa_attempts(self, order_detail_id: int) -> None:
        """rpa_attempts 를 1 증가(읽기-수정-쓰기). 단일 루프라 경합 위험 낮음."""
        client = get_client()
        cur = (
            client.table("order_details")
            .select("rpa_attempts")
            .eq("id", order_detail_id)
            .limit(1)
            .execute()
        )
        attempts = 0
        if cur.data:
            attempts = cur.data[0].get("rpa_attempts") or 0
        client.table("order_details").update({"rpa_attempts": attempts + 1}).eq(
            "id", order_detail_id
        ).execute()
