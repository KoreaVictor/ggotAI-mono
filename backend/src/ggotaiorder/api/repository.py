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

    _SETTING_PHONE_COLUMNS = (
        "order_landline_1",
        "order_landline_2",
        "order_hp_1",
        "order_hp_2",
    )
    _MEMBER_PHONE_COLUMNS = ("landline_number", "mobile_number")

    def find_shop_by_phone(self, phone: str) -> Optional[Shop]:
        client = get_client()

        # 1) setting_info 주문 전화번호(주문핸드폰/일반전화)에서 shop_key 탐색
        shop_key: Optional[int] = None
        for column in self._SETTING_PHONE_COLUMNS:
            res = (
                client.table("setting_info")
                .select("shop_key")
                .eq(column, phone)
                .limit(1)
                .execute()
            )
            if res.data:
                shop_key = res.data[0]["shop_key"]
                break

        # 2) 폴백: member_info 가게전화/대표 핸드폰
        if shop_key is None:
            for column in self._MEMBER_PHONE_COLUMNS:
                res = (
                    client.table("member_info")
                    .select("id")
                    .eq(column, phone)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    shop_key = res.data[0]["id"]
                    break

        if shop_key is None:
            return None

        # 3) shop_name 조회
        info = (
            client.table("member_info")
            .select("shop_name")
            .eq("id", shop_key)
            .limit(1)
            .execute()
        )
        if not info.data:
            return None
        return Shop(shop_key=shop_key, shop_name=info.data[0]["shop_name"])

    def insert_call_history(self, record: dict) -> int:
        res = get_client().table("server_call_history").insert(record).execute()
        if not res.data:
            raise RuntimeError("server_call_history INSERT가 행을 반환하지 않았습니다.")
        return res.data[0]["id"]
