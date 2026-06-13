from ggotaiorder.pipeline.models import OrderExtraction, CallHistory


def test_order_extraction_has_11_core_plus_delivery_text():
    # 11 코어 주문 필드 + 보조 1개(delivery_at_text, 배송시간 원문)
    assert len(OrderExtraction.model_fields) == 12
    assert "delivery_at_text" in OrderExtraction.model_fields


def test_order_extraction_defaults_none():
    e = OrderExtraction()
    dumped = e.model_dump()
    assert all(v is None for v in dumped.values())


def test_call_history_dataclass():
    ch = CallHistory(
        id=1, shop_key=2, shop_name="꽃집",
        customer_name="신규", customer_phone_number="010",
        stt_text="텍스트", audio_file_name=None, channel_order="인터라넷",
    )
    assert ch.id == 1 and ch.shop_name == "꽃집"
