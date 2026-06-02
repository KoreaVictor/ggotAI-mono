"""AI 데이터 정형화 파이프라인 (스텁).

PRD 6-4: STT(faster-whisper)로 stt_text 생성 → Gemini로 11필드 JSON 추출
→ 공백 항목 3개 이상이면 is_order='N' + 음성파일 강제삭제
→ is_order='Y' 이면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Gemini가 추출할 11개 표준 주문서 필드
ORDER_FIELDS = (
    "customer_name",
    "customer_phone_number",
    "product_name",
    "quantity",
    "price",
    "delivery_at",
    "delivery_place",
    "receiver_name",
    "receiver_phone_number",
    "ribbon_congratulations",
    "card_message",
)


async def process(call_history_id: int) -> None:
    """[스텁] 단일 수집 건을 STT→Gemini 정형화 처리한다.

    TODO(후속):
      1. server_call_history 조회 → audio_file_name 확보
      2. faster-whisper STT → stt_text UPDATE
      3. Gemini 11필드 JSON 추출
      4. 공백 >= 3 → is_order='N', 음성파일 삭제, 종료
      5. is_order='Y' → order_details INSERT(rpa_status='ready')
      6. await rpa.enqueue(order_detail_id)
    """
    logger.warning("[STUB] pipeline.process(call_history_id=%s)", call_history_id)
