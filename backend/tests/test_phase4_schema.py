"""T1 스키마 정합성: 백엔드 INSERT 페이로드가 계약을 준수하는지 검증."""

from pathlib import Path

from ggotaiorder.pipeline.engine import _build_order_payload
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.scraper.crawler import _call_record, _order_payload
from ggotaiorder.scraper.models import IntranetShop, ScrapedOrder
from tests.support.schema_contract import parse_schema, required_columns

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"
TABLES = parse_schema(SCHEMA)


def _assert_conforms(payload: dict, table: str):
    cols = set(TABLES[table])
    extra = set(payload) - cols
    assert not extra, f"{table}: 계약에 없는 컬럼 {extra}"
    missing = required_columns(TABLES, table) - set(payload)
    assert not missing, f"{table}: 필수 컬럼 누락 {missing}"
    none_required = {
        k for k in required_columns(TABLES, table)
        if payload.get(k) is None
    }
    assert not none_required, f"{table}: 필수 컬럼이 None {none_required}"


def _call_history(**kw) -> CallHistory:
    base = dict(
        id=1, shop_key=2, shop_name="꽃집", customer_name="신규",
        customer_phone_number="010-0000", stt_text="주문",
        audio_file_name="INTRANET_CRAWLED", channel_order="인터라넷",
    )
    base.update(kw)
    return CallHistory(**base)


def _shop() -> IntranetShop:
    return IntranetShop(
        shop_key=2, shop_name="꽃집", url="http://x", username="u", enc_password="e"
    )


def test_engine_order_payload_full_conforms():
    extraction = OrderExtraction(
        customer_name="홍", customer_phone_number="010-1", product_name="장미",
        quantity=2, price=50000, delivery_at="2026-06-10T10:00:00+09:00",
        delivery_place="강남", receiver_name="이", receiver_phone_number="010-2",
        ribbon_congratulations="축", card_message="축하",
    )
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_engine_order_payload_sparse_still_conforms():
    # 누락<3 이지만 NN 컬럼이 None 인 케이스 → 기본값으로 NN 충족해야 함
    extraction = OrderExtraction(
        customer_name="홍", customer_phone_number="010-1", product_name=None,
        quantity=1, price=1000, delivery_at="2026-06-10T10:00:00+09:00",
        delivery_place="강남", receiver_name="이", receiver_phone_number="010-2",
        ribbon_congratulations="축", card_message="축하",
    )
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_engine_order_payload_all_optional_none_conforms():
    extraction = OrderExtraction(customer_name="홍", customer_phone_number="010-1")
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_crawler_call_record_conforms():
    order = ScrapedOrder(order_no="A1", raw_text="원문", fields=OrderExtraction())
    _assert_conforms(_call_record(_shop(), order), "server_call_history")


def test_crawler_order_payload_conforms():
    order = ScrapedOrder(order_no="A1", raw_text="원문", fields=OrderExtraction())
    _assert_conforms(_order_payload(_shop(), order, 1), "order_details")
