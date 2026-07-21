"""RPA 등록 필수값 누락 판정 (카톡·문자 보류 게이트의 기준)."""

from ggotaiorder.pipeline.models import OrderExtraction
from ggotaiorder.pipeline.required_fields import missing_required


def _complete() -> OrderExtraction:
    return OrderExtraction(
        product_name="근조화환",
        price=100000,
        delivery_at="2026-07-22T15:00:00+09:00",
        delivery_place="서울 강남구 논현로 1",
        receiver_name="김철수",
    )


def test_complete_extraction_has_no_missing():
    assert missing_required(_complete()) == []


def test_empty_extraction_lists_all_required():
    assert missing_required(OrderExtraction()) == [
        "product_name", "price", "delivery_at", "delivery_place", "receiver_name",
    ]


def test_blank_string_counts_as_missing():
    e = _complete().model_copy(update={"receiver_name": "   "})
    assert missing_required(e) == ["receiver_name"]


def test_unparseable_delivery_at_counts_as_missing():
    """'내일 오후 3시' 같은 자연어는 ISO 파싱이 안 돼 센티넬로 떨어진다 → 보완 필요."""
    e = _complete().model_copy(update={"delivery_at": "내일 오후 3시"})
    assert missing_required(e) == ["delivery_at"]


def test_null_price_is_missing_but_zero_is_present():
    """가격은 None만 누락으로 본다(0원은 값이 채워진 것 — is_order 규칙과 동일)."""
    assert missing_required(_complete().model_copy(update={"price": None})) == ["price"]
    assert missing_required(_complete().model_copy(update={"price": 0})) == []


def test_reports_multiple_missing_in_field_order():
    e = OrderExtraction(product_name="장미", delivery_place="강남")
    assert missing_required(e) == ["price", "delivery_at", "receiver_name"]
