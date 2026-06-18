from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.flowernt3 import mapping as m


def _order(**kw):
    base = dict(
        order_detail_id=1, shop_key=19, shop_name="테스트꽃집", channel="전화",
        customer_name="홍길동", customer_phone_number="01011112222",
        product_name="장미 꽃다발", quantity=1, price=50000,
        delivery_at="2026-06-20T15:30:00", delivery_place="서울시 강남구 1-2",
        receiver_name="김영희", receiver_phone_number="01033334444",
        ribbon_sender="홍길동", ribbon_congratulations="축 개업",
        card_message="축하합니다", delivery_at_text="모레 오후 3시 반",
    )
    base.update(kw)
    return RpaOrder(**base)


def test_channel_to_order_divi_known():
    # FlowerNT3 order_divi 실제 value: 인터넷/전화/팩스/매장/프로그램간/기타
    assert m.channel_to_order_divi("전화") == "전화"
    assert m.channel_to_order_divi("가게전화") == "전화"
    assert m.channel_to_order_divi("핸드폰") == "전화"
    assert m.channel_to_order_divi("가게음성") == "매장"
    assert m.channel_to_order_divi("쇼핑몰") == "인터넷"
    assert m.channel_to_order_divi("인터라넷") == "프로그램간"


def test_channel_to_order_divi_unknown_is_etc():
    assert m.channel_to_order_divi("") == "기타"
    assert m.channel_to_order_divi("알수없음") == "기타"
    assert m.channel_to_order_divi(None) == "기타"


def test_normalize_price_digits_only():
    assert m.normalize_price(50000) == "50000"
    assert m.normalize_price("50,000원") == "50000"
    assert m.normalize_price(None) == ""
    assert m.normalize_price(50000.0) == "50000"  # float 자릿수 붕괴 방지


def test_product_to_sang_divi():
    assert m.product_to_sang_divi("장미 꽃다발") == "생화"
    assert m.product_to_sang_divi("꽃바구니") == "생화"
    assert m.product_to_sang_divi("축하화환 3단") == "축하화환"
    assert m.product_to_sang_divi("근조화환") == "근조화환"
    assert m.product_to_sang_divi("쌀화환 10kg") == "쌀화환"
    assert m.product_to_sang_divi("동양란") == "동양란"
    assert m.product_to_sang_divi("서양란 호접란") == "서양란"
    assert m.product_to_sang_divi("관엽식물 화분") == "화분"
    assert m.product_to_sang_divi("과일바구니") == "과일바구니"
    assert m.product_to_sang_divi("축하 오브제") == "축하오브제"
    assert m.product_to_sang_divi("") == ""
    assert m.product_to_sang_divi("알수없는상품") == ""


def test_split_delivery_datetime():
    assert m.split_delivery_datetime("2026-06-20T15:30:00") == ("2026-06-20", "15:30")
    assert m.split_delivery_datetime("2026-06-20 09:05") == ("2026-06-20", "09:05")
    assert m.split_delivery_datetime("2026-06-20") == ("2026-06-20", "")
    assert m.split_delivery_datetime(None) == ("", "")
    assert m.split_delivery_datetime("2026-06-20T::") == ("2026-06-20", "")  # garbage 시각
    assert m.split_delivery_datetime("2026-06-20T09:05:00+09:00") == ("2026-06-20", "09:05")


def test_order_to_fields():
    fields = m.order_to_fields(_order())
    assert fields["customer_name"] == "홍길동"
    assert fields["customer_hp"] == "01011112222"
    assert fields["sang_name"] == "장미 꽃다발"
    assert fields["sang_money"] == "50000"
    assert fields["sang_realMoney"] == "50000"   # 판매가 = 소비정가
    assert fields["receive_name"] == "김영희"
    assert fields["receive_hp"] == "01033334444"
    assert fields["receive_address1"] == "서울시 강남구 1-2"
    assert fields["hope_date"] == "2026-06-20"
    assert fields["hope_time"] == "15:30"
    assert fields["msg_text"] == "축하합니다"
    assert fields["event_txt"] == "축 개업"      # 경조사명
    assert fields["people_txt"] == "홍길동"      # 사람명(보내는분)


def test_order_to_fields_omits_empty_optional():
    fields = m.order_to_fields(_order(
        delivery_at=None, delivery_place=None, receiver_name=None,
        receiver_phone_number=None, ribbon_sender=None,
        ribbon_congratulations=None, card_message=None,
    ))
    assert fields["receive_name"] == ""
    assert fields["event_txt"] == ""
    assert fields["people_txt"] == ""
    assert fields["msg_text"] == ""
    assert "hope_date" not in fields
    assert "hope_time" not in fields
