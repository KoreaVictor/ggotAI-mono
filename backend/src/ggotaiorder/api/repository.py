"""가게전화 인입용 DB 접근: 샵 판별 + server_call_history INSERT."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class Shop:
    shop_key: int
    shop_name: str


class IngestRepository(Protocol):
    """가게전화 인입이 필요로 하는 DB 연산 계약."""

    def find_shop_by_phone(self, phone: str) -> Optional[Shop]: ...

    def insert_call_history(self, record: dict) -> int: ...


class SupabaseIngestRepository:
    """Supabase 기반 IngestRepository 구현."""

    def find_shop_by_phone(self, phone: str) -> Optional[Shop]:
        client = get_client()
        # 1) setting_info 주문 전화번호(주문핸드폰/일반전화)에서 shop_key 탐색
        setting = (
            client.table("setting_info")
            .select("shop_key")
            .or_(
                f"order_landline_1.eq.{phone},order_landline_2.eq.{phone},"
                f"order_hp_1.eq.{phone},order_hp_2.eq.{phone}"
            )
            .limit(1)
            .execute()
        )
        shop_key: Optional[int] = setting.data[0]["shop_key"] if setting.data else None

        # 2) 폴백: member_info 가게전화/대표 핸드폰
        if shop_key is None:
            member = (
                client.table("member_info")
                .select("id")
                .or_(f"landline_number.eq.{phone},mobile_number.eq.{phone}")
                .limit(1)
                .execute()
            )
            shop_key = member.data[0]["id"] if member.data else None

        if shop_key is None:
            return None

        # 3) shop_name 조회
        info = (
            client.table("member_info")
            .select("shop_name")
            .eq("id", shop_key)
            .single()
            .execute()
        )
        return Shop(shop_key=shop_key, shop_name=info.data["shop_name"])

    def insert_call_history(self, record: dict) -> int:
        res = get_client().table("server_call_history").insert(record).execute()
        return res.data[0]["id"]
