import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# 기본 실행에서는 skip. 실제 Gemini 호출 검증은 RUN_LIVE_GEMINI=1 일 때만.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMINI") != "1",
    reason="RUN_LIVE_GEMINI=1 일 때만 실제 Gemini 호출 테스트 실행",
)

REAL_ORDER = (
    "내일 오후 3시 강남역 1번출구로 배달해주세요. 김철수 생일 축하 꽃다발 한개 "
    "5만원이고 받는분은 이영희 010-1234-5678. 카드에 생일 축하해 라고 적어주세요."
)
NON_ORDER = "여보세요 거기 중국집이죠? 짜장면 두 그릇 배달돼요?"


def test_real_order_extracts_core_fields():
    from ggotaiorder.pipeline.extractor import extract_order

    e = extract_order(REAL_ORDER)
    assert e.product_name is not None
    assert e.price == 50000
    assert e.receiver_name is not None


def test_non_order_returns_mostly_null():
    from ggotaiorder.pipeline.engine import count_missing
    from ggotaiorder.pipeline.extractor import extract_order

    e = extract_order(NON_ORDER)
    assert count_missing(e) >= 9


# 짧은 구어체 매장판매 발화: gemini-2.5-flash가 가끔 전부 null로 비우던 회귀 케이스.
# 프롬프트의 판매 발화 강제 추출(4-1)+예시로 안정화 — 반복해도 항상 주문이어야 한다.
STORE_SALE = "오늘 꽃바구니 오만 원짜리 하나 판매했어."


def test_store_sale_terse_always_extracts_product_and_price():
    from ggotaiorder.pipeline.engine import is_order
    from ggotaiorder.pipeline.extractor import extract_order

    for _ in range(5):
        e = extract_order(STORE_SALE)
        assert e.product_name and e.product_name.strip(), "상품명 추출 실패"
        assert e.price == 50000
        assert is_order(e) is True
