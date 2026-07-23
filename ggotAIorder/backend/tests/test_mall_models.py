from ggotaiorder.mall.models import (
    PROVIDER_SMARTSTORE,
    SMARTSTORE_AUDIO_MARKER,
    SMARTSTORE_CHANNEL,
    ConfirmTarget,
    MallCredential,
    SmartStoreOrder,
)
from ggotaiorder.pipeline.models import OrderExtraction


def test_constants():
    assert SMARTSTORE_CHANNEL == "쇼핑몰"
    assert SMARTSTORE_AUDIO_MARKER == "SMARTSTORE_API"
    assert PROVIDER_SMARTSTORE == "smartstore"


def test_credential_defaults():
    cred = MallCredential(
        shop_key=1, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={"store_id": "s1"},
    )
    assert cred.cursor is None
    assert cred.client_secret is None
    assert cred.extra["store_id"] == "s1"


def test_smartstore_order_holds_fields():
    order = SmartStoreOrder(
        product_order_id="PO1", raw_text="원문", memo_text="메모",
        fields=OrderExtraction(product_name="장미", price=30000),
    )
    assert order.fields.product_name == "장미"


def test_confirm_target():
    t = ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=2)
    assert t.order_id == 10 and t.ack_attempts == 2
