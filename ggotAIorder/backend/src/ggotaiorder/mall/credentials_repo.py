"""mall_credentials DB 접근: 자격 목록·커서 갱신."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import MallCredential

logger = logging.getLogger(__name__)


@runtime_checkable
class MallCredentialRepository(Protocol):
    """collector 가 필요로 하는 자격증명 DB 연산 계약."""

    def list_credentials(self, provider: str) -> list[MallCredential]: ...

    def update_cursor(self, shop_key: int, provider: str, cursor: str) -> None: ...


class SupabaseMallCredentialRepository:
    """Supabase 기반 MallCredentialRepository 구현."""

    def list_credentials(self, provider: str) -> list[MallCredential]:
        client = get_client()
        res = (
            client.table("mall_credentials")
            .select("*")
            .eq("provider", provider)
            .eq("is_active", True)
            .execute()
        )
        creds: list[MallCredential] = []
        for row in res.data or []:
            member = (
                client.table("member_info")
                .select("shop_name")
                .eq("id", row["shop_key"])
                .limit(1)
                .execute()
            )
            shop_name = member.data[0]["shop_name"] if member.data else ""
            creds.append(
                MallCredential(
                    shop_key=row["shop_key"],
                    shop_name=shop_name,
                    provider=row["provider"],
                    client_id=row["client_id"],
                    enc_client_secret=row["enc_client_secret"],
                    extra=row.get("extra") or {},
                    cursor=row.get("cursor"),
                )
            )
        return creds

    def update_cursor(self, shop_key: int, provider: str, cursor: str) -> None:
        (
            get_client()
            .table("mall_credentials")
            .update({"cursor": cursor})
            .eq("shop_key", shop_key)
            .eq("provider", provider)
            .execute()
        )
