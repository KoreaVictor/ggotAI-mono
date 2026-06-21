"""AI 데이터 정형화 파이프라인.

stt_text → Gemini 11필드 추출 → 상품명·가격이 모두 있으면 주문, 아니면 주문 아님
(is_order='N'). 주문이면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
상품명+가격만 있으면 되므로 매장판매(배달·수령인 정보 없는 즉석 판매)도 주문으로 처리된다.
STT(음성→텍스트)는 stt.transcribe 인터페이스로 위임(현재 스텁).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository
from ggotaiorder.pipeline.stt import transcribe
from ggotaiorder.rpa.singleton_macro import enqueue
from ggotaiorder.scraper.crawler import INTRANET_AUDIO_MARKER

logger = logging.getLogger(__name__)

# Gemini가 추출하는 11개 표준 주문서 필드 (누락 개수 로깅용 — 보조필드 delivery_at_text 제외)
ORDER_FIELDS = (
    "customer_name", "customer_phone_number", "product_name", "quantity", "price",
    "delivery_at", "delivery_place", "receiver_name", "receiver_phone_number",
    "ribbon_congratulations", "card_message",
)

# Realtime이 직접 처리하는 채널 (catch-up 스캔도 같은 집합을 사용 — 단일 출처).
REALTIME_CHANNELS = {"핸드폰", "가게음성"}

# 매장판매(즉석 판매) 채널. 배송일 미상 시 주문일(오늘)로 채운다.
STORE_SALE_CHANNEL = "가게음성"

_KST = timezone(timedelta(hours=9))

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


def is_order(extraction: OrderExtraction) -> bool:
    """주문 판정: 상품명과 가격이 모두 있으면 주문으로 본다.

    배달 주문뿐 아니라 매장판매(배달장소·수령인·리본·카드가 없는 즉석 판매)도
    상품명+가격만 있으면 주문 경로로 처리한다. 광고·시세·잡담은 추출기가
    product_name/price 를 null 로 비우는 것을 1차 방어선으로 삼는다(extractor 규칙).
    """
    name = extraction.product_name
    has_product = isinstance(name, str) and name.strip() != ""
    has_price = extraction.price is not None
    return has_product and has_price


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


def _resolve_delivery_at(row: CallHistory, extraction: OrderExtraction) -> str:
    """배송일시 결정. 매장판매는 배송일 미상 시 주문일(오늘 KST)로 채운다.

    매장판매(가게음성)는 즉석 판매라 배송일=주문일이다. 센티넬(2099)로 두면
    FlowerNT 등록 시 주문목록(오늘/이번주 화면)에 안 보이므로 오늘로 보정한다.
    그 외 채널은 기존대로 센티넬 유지(사장님 수동 보정 대상).
    """
    resolved = _normalize_delivery_at(extraction.delivery_at)
    if resolved == DELIVERY_AT_UNKNOWN and row.channel_order == STORE_SALE_CHANNEL:
        return datetime.now(_KST).isoformat()
    return resolved


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
        "delivery_at": _resolve_delivery_at(row, extraction),
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
    try:
        await asyncio.to_thread(repo.increment_attempts, call_history_id)
    except Exception:
        logger.exception("attempts 증가 실패 id=%s — 재시도 가능", call_history_id)
        return

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

    if not is_order(extraction):
        await asyncio.to_thread(repo.mark_processed, call_history_id, "N")
        await asyncio.to_thread(repo.delete_audio, row.audio_file_name)
        logger.info(
            "주문 아님 판별 id=%s (상품명·가격 미존재, 누락 %s개)",
            call_history_id, count_missing(extraction),
        )
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
