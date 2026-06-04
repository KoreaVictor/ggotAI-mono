"""인트라넷 크롤러 DB 접근: 설정 목록·중복검증·INSERT."""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.scraper.models import IntranetShop

logger = logging.getLogger(__name__)


class IntranetRepository(Protocol):
    """인트라넷 크롤러가 필요로 하는 DB 연산 계약."""

    def list_intranet_shops(self) -> list[IntranetShop]: ...

    def order_exists(self, shop_key: int, order_no: str) -> bool: ...

    def insert_call_history(self, record: dict) -> int: ...

    def insert_order_details(self, payload: dict) -> int: ...


class SupabaseIntranetRepository:
    """Supabase 기반 IntranetRepository 구현."""

    def list_intranet_shops(self) -> list[IntranetShop]:
        client = get_client()
        settings = (
            client.table("setting_info")
            .select("shop_key, intranet_url, intranet_id, intranet_password")
            .not_.is_("intranet_url", "null")
            .execute()
        )
        shops: list[IntranetShop] = []
        for row in settings.data or []:
            member = (
                client.table("member_info")
                .select("shop_name")
                .eq("id", row["shop_key"])
                .limit(1)
                .execute()
            )
            shop_name = member.data[0]["shop_name"] if member.data else ""
            shops.append(
                IntranetShop(
                    shop_key=row["shop_key"],
                    shop_name=shop_name,
                    url=row["intranet_url"],
                    username=row.get("intranet_id") or "",
                    enc_password=row.get("intranet_password") or "",
                )
            )
        return shops

    def order_exists(self, shop_key: int, order_no: str) -> bool:
        res = (
            get_client()
            .table("server_call_history")
            .select("id")
            .eq("shop_key", shop_key)
            .eq("channel_order", "인터라넷")
            .eq("channel_classification", order_no)
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
