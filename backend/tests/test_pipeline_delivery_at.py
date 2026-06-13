"""배송시간 원문(delivery_at_text) 보관 + delivery_at 타임스탬프 정규화/방어."""

from __future__ import annotations

from ggotaiorder.pipeline import engine
from ggotaiorder.pipeline.engine import count_missing
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction


def _row(**kw) -> CallHistory:
    base = dict(
        id=1, shop_key=2, shop_name="꽃집", customer_name="신규",
        customer_phone_number="010-0000", stt_text="주문", audio_file_name="x.wav",
        channel_order="핸드폰",
    )
    base.update(kw)
    return CallHistory(**base)


# ---- count_missing 은 11 코어 필드만 — delivery_at_text 는 제외 ----

def test_delivery_at_text_not_counted_when_core_complete():
    e = OrderExtraction(
        customer_name="a", customer_phone_number="b", product_name="c",
        quantity=1, price=1000, delivery_at="2026-06-14T15:00:00+09:00",
        delivery_place="e", receiver_name="f", receiver_phone_number="g",
        ribbon_congratulations="h", card_message="i", delivery_at_text="내일 오후 3시",
    )
    assert count_missing(e) == 0


def test_delivery_at_text_present_does_not_reduce_missing():
    # 코어 11개 전부 없음 + 원문만 있음 → 여전히 11
    assert count_missing(OrderExtraction(delivery_at_text="내일 오후 3시")) == 11


# ---- _build_order_payload: delivery_at 정규화 + 원문 보관 ----

def test_payload_keeps_valid_iso_and_text():
    ex = OrderExtraction(
        product_name="장미", delivery_at="2026-06-14T15:00:00+09:00",
        delivery_at_text="내일 오후 3시", delivery_place="강남", receiver_name="김",
        receiver_phone_number="010-2",
    )
    p = engine._build_order_payload(_row(), ex)
    assert p["delivery_at"] == "2026-06-14T15:00:00+09:00"
    assert p["delivery_at_text"] == "내일 오후 3시"


def test_payload_falls_back_to_sentinel_on_unparseable_delivery_at():
    # Gemini가 ISO 변환 못 하고 자연어를 넣어도 INSERT가 깨지지 않도록 센티넬 폴백,
    # 단 원문은 delivery_at_text 로 보존
    ex = OrderExtraction(
        product_name="장미", delivery_at="내일 오후 3시", delivery_at_text="내일 오후 3시",
    )
    p = engine._build_order_payload(_row(), ex)
    assert p["delivery_at"] == DELIVERY_AT_UNKNOWN
    assert p["delivery_at_text"] == "내일 오후 3시"


def test_payload_delivery_at_text_none_when_absent():
    ex = OrderExtraction(product_name="장미", delivery_at="2026-06-14T15:00:00+09:00")
    p = engine._build_order_payload(_row(), ex)
    assert p["delivery_at_text"] is None
