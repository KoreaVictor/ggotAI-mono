from pathlib import Path

from tests.support.schema_contract import parse_schema, required_columns

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"


def test_parses_all_four_tables():
    tables = parse_schema(SCHEMA)
    assert set(tables) == {
        "member_info", "server_call_history", "order_details", "setting_info"
    }


def test_order_details_columns_and_nullability():
    cols = parse_schema(SCHEMA)["order_details"]
    assert "product_name" in cols
    assert cols["product_name"].nullable is False
    assert cols["product_name"].has_default is False
    # id 는 SERIAL → has_default True
    assert cols["id"].has_default is True
    # ribbon_sender 는 NULL 허용
    assert cols["ribbon_sender"].nullable is True


def test_required_columns_order_details():
    tables = parse_schema(SCHEMA)
    req = required_columns(tables, "order_details")
    assert req == {
        "call_history_id", "shop_key", "shop_name", "customer_phone_number",
        "product_name", "delivery_at", "delivery_place",
        "receiver_name", "receiver_phone_number",
    }


def test_required_columns_server_call_history():
    tables = parse_schema(SCHEMA)
    req = required_columns(tables, "server_call_history")
    assert req == {
        "channel_classification", "shop_key", "shop_name", "call_date", "call_time"
    }
