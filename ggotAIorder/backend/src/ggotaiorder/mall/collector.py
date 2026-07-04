"""스마트스토어 신규주문 정기 폴링 수집 (오케스트레이션).

커머스API 신규주문(결제완료) → server_call_history + order_details(rpa_status='ready',
mall_ack_status='pending') 직접 적재 → rpa.enqueue. API 정형값을 권위로 두고, 자유텍스트
(메모+옵션)만 Gemini 로 병합(배달일시·리본·카드·상품분류). 연속 3회 수집 실패 시 비상 알림.
실제 커머스API 상호작용은 SmartStoreClient(Protocol) 뒤로 추상화(테스트는 fake 주입).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import decrypt
from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.models import (
    PROVIDER_SMARTSTORE,
    SMARTSTORE_AUDIO_MARKER,
    SMARTSTORE_CHANNEL,
    MallCredential,
    SmartStoreOrder,
)
from ggotaiorder.mall.order_repo import MallOrderRepository, SupabaseMallOrderRepository
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient, SmartStoreClient
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.pipeline.order_payload import build_order_payload
from ggotaiorder.rpa.singleton_macro import enqueue

logger = logging.getLogger(__name__)

# 연속 수집 실패가 이 값에 도달하면 비상 알림(scraper 와 동일 관례).
_FAILURE_THRESHOLD = 3

# shop_key -> 연속 실패 횟수
_failure_counts: dict[int, int] = {}

# API 권위값을 덮지 않고 Gemini soft 에서만 취하는 필드(설계서 §4).
_SOFT_FIELDS = (
    "delivery_at",
    "delivery_at_text",
    "ribbon_congratulations",
    "card_message",
    "sang_divi",
)


async def _default_notify(shop_key: int) -> None:
    """기본 비상 알림: notifier 실패 문구로 발송(전용 문구는 후속)."""
    await notifier_send(shop_key, channel=SMARTSTORE_CHANNEL, count=0, outcome="fail")


def _merge_fields(order: SmartStoreOrder, extract) -> OrderExtraction:
    """API 권위값(order.fields) 위에 Gemini soft 필드만 덮어 병합한다.

    soft 추출이 실패해도 정형값은 유효하므로 예외를 흡수하고 API 값만으로 진행한다
    (주문 유실 방지). soft 에서 취하는 건 배달일시·리본·카드·상품분류뿐.
    """
    try:
        soft = extract(order.memo_text)
    except Exception:
        logger.exception("메모 Gemini 추출 실패 — 정형값만으로 진행 po=%s", order.product_order_id)
        return order.fields
    updates = {name: getattr(soft, name) for name in _SOFT_FIELDS}
    return order.fields.model_copy(update=updates)


def _call_record(cred: MallCredential, order: SmartStoreOrder) -> dict:
    now = datetime.now()
    f = order.fields
    return {
        "channel_order": SMARTSTORE_CHANNEL,
        "channel_classification": order.product_order_id,
        "shop_key": cred.shop_key,
        "shop_name": cred.shop_name,
        "customer_name": f.customer_name or "신규",
        "customer_phone_number": f.customer_phone_number or "",
        "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"),
        "duration_seconds": 0,
        "audio_file_name": SMARTSTORE_AUDIO_MARKER,
        "stt_text": order.raw_text,
        "is_order": "Y",
    }


def _order_payload(
    cred: MallCredential, order: SmartStoreOrder, merged: OrderExtraction, call_id: int
) -> dict:
    """공용 build_order_payload 로 조립한 뒤 발주확인 상태(pending)를 덧붙인다."""
    row = CallHistory(
        id=call_id,
        shop_key=cred.shop_key,
        shop_name=cred.shop_name,
        customer_name=merged.customer_name,
        customer_phone_number=merged.customer_phone_number,
        stt_text=order.raw_text,
        audio_file_name=SMARTSTORE_AUDIO_MARKER,
        channel_order=SMARTSTORE_CHANNEL,
    )
    payload = build_order_payload(row, merged)
    payload["mall_ack_status"] = "pending"
    return payload


async def _handle_failure(shop_key: int, notify) -> None:
    count = _failure_counts.get(shop_key, 0) + 1
    _failure_counts[shop_key] = count
    logger.warning("스마트스토어 수집 실패 shop_key=%s (연속 %s회)", shop_key, count)
    if count >= _FAILURE_THRESHOLD:
        await notify(shop_key)
        _failure_counts[shop_key] = 0


async def poll_once(
    *,
    cred_repo: MallCredentialRepository | None = None,
    order_repo: MallOrderRepository | None = None,
    client: SmartStoreClient | None = None,
    notify=None,
    extract=None,
) -> None:
    """스마트스토어를 1회 폴링한다 (APScheduler 가 주기 호출)."""
    cred_repo = cred_repo or SupabaseMallCredentialRepository()
    order_repo = order_repo or SupabaseMallOrderRepository()
    client = client or HttpSmartStoreClient()
    notify = notify or _default_notify
    extract = extract or extract_order

    cfg = load_config()
    creds = await asyncio.to_thread(cred_repo.list_credentials, PROVIDER_SMARTSTORE)

    for cred in creds:
        try:
            cred.client_secret = decrypt(cred.enc_client_secret, cfg.aes_encryption_key)
            orders, next_cursor = await asyncio.to_thread(client.fetch_new_orders, cred)
        except Exception:
            logger.exception("스마트스토어 수집 실패 shop_key=%s", cred.shop_key)
            await _handle_failure(cred.shop_key, notify)
            continue

        _failure_counts[cred.shop_key] = 0

        for order in orders:
            try:
                if await asyncio.to_thread(
                    order_repo.order_exists, cred.shop_key, order.product_order_id
                ):
                    continue
                merged = _merge_fields(order, extract)
                call_id = await asyncio.to_thread(
                    order_repo.insert_call_history, _call_record(cred, order)
                )
                order_id = await asyncio.to_thread(
                    order_repo.insert_order_details,
                    _order_payload(cred, order, merged, call_id),
                )
                await enqueue(order_id)
            except Exception:
                logger.exception(
                    "스마트스토어 주문 적재 실패 shop_key=%s po=%s",
                    cred.shop_key, order.product_order_id,
                )

        await asyncio.to_thread(
            cred_repo.update_cursor, cred.shop_key, PROVIDER_SMARTSTORE, next_cursor
        )
