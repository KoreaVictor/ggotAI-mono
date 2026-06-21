"""Gemini 기반 주문 정형화 추출 (google-genai 구조화 출력).

stt_text → OrderExtraction(11필드). 입력에 없는 값은 절대 추측하지 않고 None.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from google import genai
from google.genai import types

from ggotaiorder.config import load_config
from ggotaiorder.pipeline.models import OrderExtraction

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

_KST = timezone(timedelta(hours=9))

_SYSTEM_INSTRUCTION = (
    "너는 꽃집 주문 통화/텍스트에서 주문 정보를 추출하는 엄격한 추출기다.\n"
    "규칙:\n"
    "1. 입력에 명시적으로 나타난 값만 채운다.\n"
    "2. 언급되지 않았거나 불확실하면 반드시 null. 추측·창작 금지.\n"
    "3. 예시/기본값(홍길동, 010-1234-5678 등)을 임의로 넣지 마라.\n"
    "4. 꽃 주문·판매가 아니면(음식주문/잡담/광고/시세 언급 등) 모든 필드를 null.\n"
    "   '판매/구매 의도가 없는' 광고·홍보·가격표·시세 비교·잡담은 상품과 가격이 보여도 "
    "product_name 과 price 를 포함해 전부 null 로 둔다.\n"
    "4-1. (중요) 실제 판매/주문 발화 — '~을 ~원에 팔았다/판매했다/팝니다/주문' 처럼 상품과 "
    "금액이 함께 나오면, 문장이 아무리 짧고 구어체여도(매장판매처럼 받는사람·배달정보가 전혀 "
    "없어도) product_name 과 price 는 반드시 채운다. 이때 정보 부족을 이유로 전부 null 로 비우지 "
    "마라 — 말한 상품명과 금액만큼은 항상 추출한다.\n"
    "5. 가격은 '5만원'/'오만 원'->50000 처럼 원 단위 정수로 변환(한글 수사도 숫자로).\n"
    "6. delivery_at 은 ISO 8601(예: 2026-06-14T15:00:00+09:00)로 변환한다. "
    "'내일/오늘/모레 오후 3시' 같은 상대표현은 제공된 '현재 시각'을 기준으로 절대시각을 계산한다. "
    "날짜·시간이 불명확하면 null.\n"
    "7. delivery_at_text 에는 배달 시점을 말한 그대로의 원본 문구를 넣는다(예: '내일 오후 3시'). "
    "언급이 없으면 null. (delivery_at 이 null 이어도 원문이 있으면 delivery_at_text 는 채운다.)\n"
    "예시(매장판매 — 짧아도 상품·가격 반드시 추출):\n"
    "  입력: '오늘 꽃바구니 오만 원짜리 하나 판매했어.'\n"
    "  → product_name='꽃바구니', quantity=1, price=50000, 나머지 null.\n"
    "  입력: '서양란 한 개 5만원에 팔았습니다.'\n"
    "  → product_name='서양란', quantity=1, price=50000, 나머지 null.\n"
    "예시(광고/잡담 — 전부 null):\n"
    "  입력: '호접란 특가 5만원! 지금 전화주세요'  → 모든 필드 null."
)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=load_config().gemini_api_key)
    return _client


def extract_order(
    stt_text: str, *, reference_time: str | None = None, max_retries: int = 3
) -> OrderExtraction:
    """stt_text 에서 주문 필드를 구조화 추출한다.

    reference_time: 상대 배송표현('내일' 등) 해석 기준 시각(ISO). 미지정 시 현재 KST.
    일시적 오류(예: 503)는 재시도하며, 끝내 실패하면 RuntimeError.
    """
    client = _get_client()
    ref = reference_time or datetime.now(_KST).isoformat()
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=OrderExtraction,
        temperature=0,
    )
    contents = f"현재 시각: {ref}\n입력:\n{stt_text}"
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config
            )
            parsed = resp.parsed
            if isinstance(parsed, OrderExtraction):
                return parsed
            return OrderExtraction.model_validate_json(resp.text)
        except Exception as exc:  # noqa: BLE001 - 외부 API 오류 일괄 처리
            last_error = exc
            logger.warning(
                "Gemini 추출 시도 %s/%s 실패: %s",
                attempt + 1, max_retries, str(exc)[:120],
            )
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini 추출 실패(재시도 {max_retries}회 초과): {last_error}")
