from ggotaiorder.pipeline.engine import count_missing
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
