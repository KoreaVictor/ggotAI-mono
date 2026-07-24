"""RpaOrder → RoseWeb 주문폼 필드값 매핑(순수 로직)."""

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.roseweb import layout, mapping


def _order(**kw):
    base = dict(order_detail_id=1, shop_key=19, shop_name="꽃집", channel="쇼핑몰",
                customer_name="김발주", customer_phone_number="01011112222",
                product_name="장미꽃다발", quantity=1, price=55000,
                delivery_at="2026-07-25T14:30:00", delivery_place="서울 강남구 논현로 1",
                receiver_name="이받는", receiver_phone_number="01033334444",
                ribbon_sender="김발주", ribbon_congratulations="축 개업",
                card_message="번창하세요")
    base.update(kw)
    return RpaOrder(**base)


def test_order_to_values_maps_core_fields():
    v = mapping.order_to_values(_order())
    assert v["product_name"] == "장미꽃다발"
    assert v["unit_price"] == "55000"
    assert v["quantity"] == "1"
    assert v["delivery_date"] == "2026-07-25"
    assert v["delivery_time"] == "14:30"
    assert v["delivery_place"] == "서울 강남구 논현로 1"
    assert v["receiver_name"] == "이받는"
    assert v["receiver_phone"] == "01033334444"
    assert v["ribbon_congrats"] == "축 개업"
    assert v["ribbon_sender"] == "김발주"
    assert v["card"] == "번창하세요"
    assert v["orderer_name"] == "김발주"
    assert v["orderer_phone"] == "01011112222"


def test_keys_are_a_subset_of_layout_positions():
    """값을 만들었는데 넣을 자리를 모르면 그 값은 조용히 버려진다."""
    v = mapping.order_to_values(_order())
    assert set(v) <= set(layout.FIELD_POSITIONS)


def test_omits_empty_optionals():
    v = mapping.order_to_values(_order(card_message=None, ribbon_sender=None))
    assert "card" not in v
    assert "ribbon_sender" not in v


def test_timezone_suffix_is_dropped():
    """DB 는 +09:00 을 달고 오는데 폼은 현지시각 기준이다."""
    v = mapping.order_to_values(_order(delivery_at="2026-07-25T14:30:00+09:00"))
    assert v["delivery_date"] == "2026-07-25"
    assert v["delivery_time"] == "14:30"


def test_delivery_time_falls_back_to_spoken_text():
    """시각을 못 뽑았으면 사장님이 들은 원문("오후 2시경")이라도 넣어준다.

    배달시간 칸은 자유입력(TdxDBPickEdit)이라 문구가 그대로 들어간다. 빈칸으로 두면
    정보가 사라진다.
    """
    v = mapping.order_to_values(_order(delivery_at="2026-07-25", delivery_at_text="오후 2시경"))
    assert v["delivery_date"] == "2026-07-25"
    assert v["delivery_time"] == "오후 2시경"


def test_no_delivery_at_omits_date_and_time():
    v = mapping.order_to_values(_order(delivery_at=None, delivery_at_text=None))
    assert "delivery_date" not in v
    assert "delivery_time" not in v


def test_price_with_currency_text_is_digits_only():
    v = mapping.order_to_values(_order(price="55,000원"))
    assert v["unit_price"] == "55000"


def test_zero_price_is_kept():
    """0 은 '값 없음'이 아니다 — 빈값 생략 규칙에 휩쓸리면 안 된다."""
    v = mapping.order_to_values(_order(price=0))
    assert v["unit_price"] == "0"


def test_quantity_defaults_to_one_when_missing():
    v = mapping.order_to_values(_order(quantity=None))
    assert v["quantity"] == "1"
