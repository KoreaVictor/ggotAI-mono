"""AI 데이터 정형화 파이프라인.

stt_text → Gemini 11필드 추출 → 누락 3개 이상이면 주문 아님(is_order='N'),
아니면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
STT(음성→텍스트)는 stt.transcribe 인터페이스로 위임(현재 스텁).
"""

from __future__ import annotations

import logging

from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository
from ggotaiorder.pipeline.stt import transcribe
from ggotaiorder.rpa.singleton_macro import enqueue
from ggotaiorder.scraper.crawler import INTRANET_AUDIO_MARKER

logger = logging.getLogger(__name__)

# Gemini가 추출하는 11개 표준 주문서 필드 (OrderExtraction과 동일)
ORDER_FIELDS = tuple(OrderExtraction.model_fields.keys())

# 누락이 이 값 이상이면 꽃 주문이 아닌 것으로 판별 (PRD 6-4)
_MISSING_THRESHOLD = 3


def count_missing(extraction: OrderExtraction) -> int:
    """11필드 중 None 또는 공백 문자열인 항목 수를 센다."""
    missing = 0
    for value in extraction.model_dump().values():
        if value is None:
            missing += 1
        elif isinstance(value, str) and value.strip() == "":
            missing += 1
    return missing


def _build_order_payload(row: CallHistory, extraction: OrderExtraction) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다."""
    return {
        "call_history_id": row.id,
        "shop_key": row.shop_key,
        "shop_name": row.shop_name,
        "customer_name": extraction.customer_name or row.customer_name or "신규",
        "customer_phone_number": (
            extraction.customer_phone_number or row.customer_phone_number or ""
        ),
        "product_name": extraction.product_name,
        "quantity": extraction.quantity or 1,
        "price": extraction.price or 0,
        "delivery_at": extraction.delivery_at,
        "delivery_place": extraction.delivery_place,
        "receiver_name": extraction.receiver_name,
        "receiver_phone_number": extraction.receiver_phone_number,
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
        row = repo.get_call_history(call_history_id)
    except Exception:
        logger.exception("수집 이력 조회 실패 id=%s", call_history_id)
        return

    stt_text = row.stt_text
    if not stt_text:
        if row.audio_file_name and row.audio_file_name != INTRANET_AUDIO_MARKER:
            try:
                stt_text = transcribe(row.audio_file_name)
                repo.update_stt_text(call_history_id, stt_text)
            except NotImplementedError:
                logger.warning("STT 미구현 — 건너뜀 id=%s", call_history_id)
                return
        else:
            logger.warning("stt_text 없음 — 건너뜀 id=%s", call_history_id)
            return

    try:
        extraction = extract_order(stt_text)
    except Exception:
        logger.exception("Gemini 추출 실패 id=%s", call_history_id)
        return

    missing = count_missing(extraction)
    if missing >= _MISSING_THRESHOLD:
        repo.set_is_order(call_history_id, "N")
        repo.delete_audio(row.audio_file_name)
        logger.info("주문 아님 판별 id=%s (누락 %s개)", call_history_id, missing)
        return

    repo.set_is_order(call_history_id, "Y")
    order_id = repo.insert_order_details(_build_order_payload(row, extraction))
    logger.info("order_details 생성 id=%s order_id=%s", call_history_id, order_id)
    await enqueue(order_id)
