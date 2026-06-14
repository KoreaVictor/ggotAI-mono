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

# 영구 실패 행의 무한 재시도 차단 상한 (catch-up 스캔과 공유)
MAX_ATTEMPTS = 5

# 처리 중인 call_history_id (Realtime 콜백과 catch-up 스캔의 중복 처리 방지).
# 오케스트레이터가 단일 asyncio 루프라 add가 첫 await 이전에 일어나 원자적이다.
_in_flight: set[int] = set()


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

    같은 id가 이미 처리 중이면 즉시 스킵한다(중복 주문 INSERT 방지).
    repo 미지정 시 SupabaseOrderRepository 를 사용한다(테스트는 fake 주입).
    """
    if call_history_id in _in_flight:
        logger.debug("이미 처리 중 — 스킵 id=%s", call_history_id)
        return
    _in_flight.add(call_history_id)
    try:
        await _process_inner(call_history_id, repo or SupabaseOrderRepository())
    finally:
        _in_flight.discard(call_history_id)


async def _process_inner(call_history_id: int, repo: OrderRepository) -> None:
    # 시도 횟수를 먼저 올린다(실패해도 카운트 → MAX_ATTEMPTS 상한이 적용됨).
    await asyncio.to_thread(repo.increment_attempts, call_history_id)

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
        extraction = await asyncio.to_thread(extract_order, stt_text)
    except Exception:
        logger.exception("Gemini 추출 실패 id=%s", call_history_id)
        return

    missing = count_missing(extraction)
    if missing >= _MISSING_THRESHOLD:
        await asyncio.to_thread(repo.mark_processed, call_history_id, "N")
        await asyncio.to_thread(repo.delete_audio, row.audio_file_name)
        logger.info("주문 아님 판별 id=%s (누락 %s개)", call_history_id, missing)
        return

    # order_details INSERT가 성공한 뒤에만 종결('Y')로 마킹한다(부분쓰기 방지).
    try:
        order_id = await asyncio.to_thread(
            repo.insert_order_details, _build_order_payload(row, extraction)
        )
    except Exception:
        logger.exception("order_details 생성 실패 — 미종결 id=%s", call_history_id)
        return

    await asyncio.to_thread(repo.mark_processed, call_history_id, "Y")
    logger.info("order_details 생성 id=%s order_id=%s", call_history_id, order_id)
    await enqueue(order_id)
