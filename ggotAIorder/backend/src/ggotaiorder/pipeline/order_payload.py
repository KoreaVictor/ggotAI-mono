"""order_details INSERT payload 조립 (pipeline·mall 공용 단일 출처).

기존 engine 내부 헬퍼를 이관. delivery_at 정규화·센티넬 폴백, 매장판매 배송일=주문일
보정, NOT NULL 안전 기본값 규칙을 한 곳에서 관리한다(설계서 §6). engine 은 이 모듈을
재수출(별칭)해 동작 불변.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# 매장판매(즉석 판매) 채널. 배송일 미상 시 주문일(오늘 KST)로 채운다.
STORE_SALE_CHANNEL = "가게음성"


def normalize_delivery_at(value: str | None) -> str:
    """배달일시를 유효한 timestamptz 문자열로 정규화한다.

    ISO 8601 이면 그대로, 자연어거나 비어 있으면 센티넬로 폴백해 INSERT(NOT NULL)가
    깨지지 않게 한다(원문은 delivery_at_text 보존).
    """
    if value:
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            logger.info("delivery_at 파싱 불가 — 센티넬 폴백: %r", value)
    return DELIVERY_AT_UNKNOWN


def resolve_delivery_at(row: CallHistory, extraction: OrderExtraction) -> str:
    """배송일시 결정. 매장판매는 배송일 미상 시 주문일(오늘 KST)로 채운다."""
    resolved = normalize_delivery_at(extraction.delivery_at)
    if resolved == DELIVERY_AT_UNKNOWN and row.channel_order == STORE_SALE_CHANNEL:
        return datetime.now(_KST).isoformat()
    return resolved


def build_order_payload(
    row: CallHistory, extraction: OrderExtraction, rpa_status: str = "ready"
) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다.

    NOT NULL·DEFAULT 없는 컬럼은 미상 시 안전 기본값으로 채운다(설계서 §6).
    rpa_status 는 카톡·문자 보류 건에서 'hold' 로 넘어온다(기본값은 즉시 자동입력).
    """
    return {
        "call_history_id": row.id,
        "shop_key": row.shop_key,
        "shop_name": row.shop_name,
        "customer_name": extraction.customer_name or row.customer_name or "신규",
        "customer_phone_number": (
            extraction.customer_phone_number or row.customer_phone_number or ""
        ),
        "product_name": extraction.product_name or "미정",
        "quantity": extraction.quantity if extraction.quantity is not None else 1,
        "price": extraction.price if extraction.price is not None else 0,
        "delivery_at": resolve_delivery_at(row, extraction),
        "delivery_at_text": extraction.delivery_at_text,
        "delivery_place": extraction.delivery_place or "미정",
        "receiver_name": extraction.receiver_name or "미정",
        "receiver_phone_number": extraction.receiver_phone_number or "",
        "ribbon_congratulations": extraction.ribbon_congratulations,
        "card_message": extraction.card_message,
        "sang_divi": extraction.sang_divi,
        "rpa_status": rpa_status,
    }
