"""RPA 입력 성공분 자동 발주확인 스캐너.

RPA 내부에 결합하지 않고, rpa_status='success' && mall_ack_status='pending' 인
스마트스토어 주문(audio_file_name=SMARTSTORE_API)을 폴링해 커머스API 발주확인을 호출한다.
외부 쓰기(발주확인)는 RPA 성공이 DB 에 확정된 뒤에만 일어난다. 재시도 상한 초과 시
'skipped'로 마킹해 무한 재시도를 막고 수동 확인 대상으로 남긴다.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import decrypt
from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.models import PROVIDER_SMARTSTORE, SMARTSTORE_AUDIO_MARKER
from ggotaiorder.mall.order_repo import MallOrderRepository, SupabaseMallOrderRepository
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient, SmartStoreClient

logger = logging.getLogger(__name__)

# 발주확인 최대 재시도 횟수. 초과 시 'skipped'(수동 확인 대상)로 마킹.
_ACK_MAX_ATTEMPTS = 5


class MallConfirmScanner:
    """발주확인 대상을 한 번 스캔해 커머스API 승인을 시도한다.

    order_repo/client/cred_repo 미지정 시 실제 구현을 쓴다(테스트는 fake 주입).
    """

    async def scan_once(
        self,
        *,
        order_repo: MallOrderRepository | None = None,
        client: SmartStoreClient | None = None,
        cred_repo: MallCredentialRepository | None = None,
    ) -> int:
        order_repo = order_repo or SupabaseMallOrderRepository()
        client = client or HttpSmartStoreClient()
        cred_repo = cred_repo or SupabaseMallCredentialRepository()

        targets = await asyncio.to_thread(
            order_repo.list_confirmable, SMARTSTORE_AUDIO_MARKER
        )
        if not targets:
            return 0

        cfg = load_config()
        creds = await asyncio.to_thread(cred_repo.list_credentials, PROVIDER_SMARTSTORE)
        creds_by_shop = {c.shop_key: c for c in creds}

        processed = 0
        for t in targets:
            cred = creds_by_shop.get(t.shop_key)
            if cred is None:
                logger.warning("발주확인 자격증명 없음 — 스킵 shop_key=%s", t.shop_key)
                continue
            processed += 1
            attempts = await asyncio.to_thread(
                order_repo.increment_ack_attempts, t.order_id
            )
            try:
                cred.client_secret = decrypt(cred.enc_client_secret, cfg.aes_encryption_key)
                await asyncio.to_thread(client.confirm_order, cred, t.product_order_id)
                await asyncio.to_thread(order_repo.mark_ack, t.order_id, "confirmed")
            except Exception:
                logger.exception("발주확인 실패 order_id=%s", t.order_id)
                if attempts >= _ACK_MAX_ATTEMPTS:
                    await asyncio.to_thread(order_repo.mark_ack, t.order_id, "skipped")
        return processed
