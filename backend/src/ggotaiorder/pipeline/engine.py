"""AI 데이터 정형화 파이프라인.

stt_text → Gemini 11필드 추출 → 누락 3개 이상이면 주문 아님(is_order='N'),
아니면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
STT(음성→텍스트)는 stt.transcribe 인터페이스로 위임(현재 스텁).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository
from ggotaiorder.pipeline.stt import transcribe
from ggotaiorder.rpa.singleton_macro import enqueue
from ggotaiorder.scraper.crawler import INTRANET_AUDIO_MARKER

logger = logging.getLogger(__name__)

# Gemini가 추출하는 11개 표준 주문서 필드 (누락 판정 기준 — 보조필드 delivery_at_text 제외)
ORDER_FIELDS = (
    "customer_name", "customer_phone_number", "product_name", "quantity", "price",
    "delivery_at", "delivery_place", "receiver_name", "receiver_phone_number",
    "ribbon_congratulations", "card_message",
)

# 누락이 이 값 이상이면 꽃 주문이 아닌 것으로 판별 (PRD 6-4)
_MISSING_THRESHOLD = 3


def count_missing(extraction: OrderExtraction) -> int:
    """11 코어 필드 중 None 또는 공백 문자열인 항목 수를 센다(delivery_at_text 제외)."""
    data = extraction.model_dump()
    missing = 0
    for name in ORDER_FIELDS:
        value = data[name]
        if value is None:
            missing += 1
        elif isinstance(value, str) and value.strip() == "":
            missing += 1
    return missing


def _normalize_delivery_at(value: str | None) -> str:
    """배달일시를 유효한 timestamptz 문자열로 정규화한다.

    Gemini가 ISO 8601 을 주면 그대로, 자연어("내일 오후 3시")거나 비어 있으면
    센티넬로 폴백해 INSERT(NOT NULL) 가 절대 깨지지 않게 한다(원문은 delivery_at_text 보존).
    """
    if value:
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            logger.info("delivery_at 파싱 불가 — 센티넬 폴백: %r", value)
    return DELIVERY_AT_UNKNOWN


def _build_order_payload(row: CallHistory, extraction: OrderExtraction) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다.

    order_details 의 NOT NULL·DEFAULT 없는 컬럼은 미상 시 안전 기본값으로 채운다
    (설계서 §6: product_name/delivery_at/delivery_place/receiver_* NN 위반 방지).
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
        "delivery_at": _normalize_delivery_at(extraction.delivery_at),
        "delivery_at_text": extraction.delivery_at_text,
        "delivery_place": extraction.delivery_place or "미정",
        "receiver_name": extraction.receiver_name or "미정",
        "receiver_phone_number": extraction.receiver_phone_number or "",
        "ribbon_congratulations": extraction.ribbon_congratulations,
        "card_message": extraction.card_message,
        "rpa_status": "ready",
    }


async def process(call_history_id: int, repo: OrderRepository | None = None) -> None:
    """단일 수집 건을 정형화 처리한다.

    repo 미지정 시 SupabaseOrderRepository 를 사용한다(테스트는 fake 주입).
    """
    repo = repo or SupabaseOrderRepository()

    try:
        row = await asyncio.to_thread(repo.get_call_history, call_history_id)
    except Exception:
        logger.exception("수집 이력 조회 실패 id=%s", call_history_id)
        return

    stt_text = row.stt_text
    if not stt_text:
        if row.audio_file_name and row.audio_file_name != INTRANET_AUDIO_MARKER:
            try:
                stt_text = await asyncio.to_thread(transcribe, row.audio_file_name)
                await asyncio.to_thread(repo.update_stt_text, call_history_id, stt_text)
            except Exception:
                logger.exception("STT 처리 실패 — 건너뜀 id=%s", call_history_id)
                return
        else:
            logger.warning("stt_text 없음 — 건너뜀 id=%s", call_history_id)
            return

    try:
        # 동기 Gemini 호출(재시도 time.sleep 포함)을 워커 스레드로 오프로드해
        # asyncio 이벤트 루프를 블로킹하지 않는다.
        extraction = await asyncio.to_thread(extract_order, stt_text)
    except Exception:
        logger.exception("Gemini 추출 실패 id=%s", call_history_id)
        return

    missing = count_missing(extraction)
    if missing >= _MISSING_THRESHOLD:
        await asyncio.to_thread(repo.set_is_order, call_history_id, "N")
        await asyncio.to_thread(repo.delete_audio, row.audio_file_name)
        logger.info("주문 아님 판별 id=%s (누락 %s개)", call_history_id, missing)
        return

    # order_details INSERT가 성공한 뒤에만 is_order='Y'로 마킹한다.
    # 순서를 뒤집으면 INSERT 실패 시 주문 행 없이 is_order만 'Y'가 되는 부분쓰기가 남는다.
    try:
        order_id = await asyncio.to_thread(
            repo.insert_order_details, _build_order_payload(row, extraction)
        )
    except Exception:
        logger.exception("order_details 생성 실패 — is_order 미변경 id=%s", call_history_id)
        return

    await asyncio.to_thread(repo.set_is_order, call_history_id, "Y")
    logger.info("order_details 생성 id=%s order_id=%s", call_history_id, order_id)
    await enqueue(order_id)
