from ggotaiorder.pipeline.engine import count_missing, is_order
from ggotaiorder.pipeline.models import OrderExtraction


def test_all_present_zero_missing():
    e = OrderExtraction(
        customer_name="a", customer_phone_number="b", product_name="c",
        quantity=1, price=1000, delivery_at="d", delivery_place="e",
        receiver_name="f", receiver_phone_number="g",
        ribbon_congratulations="h", card_message="i",
    )
    assert count_missing(e) == 0


def test_all_none_counts_eleven():
    assert count_missing(OrderExtraction()) == 11


def test_blank_string_counts_as_missing():
    e = OrderExtraction(product_name="   ", receiver_name="")
    assert count_missing(e) == 11


def test_two_missing_below_threshold():
    e = OrderExtraction(
        customer_name="a", customer_phone_number="b", product_name="c",
        quantity=1, price=1000, delivery_at="d", delivery_place="e",
        receiver_name="f", receiver_phone_number="g",
    )
    assert count_missing(e) == 2


# --- is_order 게이트: product_name + price 둘 다 있으면 주문 (매장판매 포함) ---


def test_is_order_store_sale_product_and_price_only():
    """매장판매: 상품명+가격만 있고 배달/수령인 전부 비어도 주문으로 인정."""
    e = OrderExtraction(product_name="호접란", quantity=1, price=50000)
    assert is_order(e) is True


def test_is_order_false_when_product_missing():
    assert is_order(OrderExtraction(price=50000)) is False


def test_is_order_false_when_price_missing():
    assert is_order(OrderExtraction(product_name="호접란")) is False


def test_is_order_false_when_product_blank():
    assert is_order(OrderExtraction(product_name="   ", price=50000)) is False


def test_is_order_false_when_all_empty():
    assert is_order(OrderExtraction()) is False
