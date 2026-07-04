from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction
from ggotaiorder.pipeline.order_payload import (
    build_order_payload,
    normalize_delivery_at,
)


def _row(channel="쇼핑몰"):
    return CallHistory(
        id=1, shop_key=7, shop_name="꽃집", customer_name=None,
        customer_phone_number=None, stt_text="원문", audio_file_name="X",
        channel_order=channel,
    )


def test_normalize_iso_passthrough():
    assert normalize_delivery_at("2026-07-04T15:00:00+09:00") == "2026-07-04T15:00:00+09:00"


def test_normalize_natural_language_falls_back_to_sentinel():
    assert normalize_delivery_at("내일 오후 3시") == DELIVERY_AT_UNKNOWN


def test_build_payload_defaults_and_status():
    p = build_order_payload(_row(), OrderExtraction(product_name="장미", price=30000))
    assert p["product_name"] == "장미"
    assert p["quantity"] == 1          # None → 기본 1
    assert p["delivery_place"] == "미정"
    assert p["delivery_at"] == DELIVERY_AT_UNKNOWN  # 쇼핑몰 채널은 센티넬 유지(매장판매 아님)
    assert p["rpa_status"] == "ready"


def test_engine_aliases_still_exist():
    # 하위호환: 기존 테스트가 참조하는 engine 심볼이 살아있어야 한다.
    from ggotaiorder.pipeline import engine
    assert engine._build_order_payload is build_order_payload
