"""HttpSmartStoreClient 실 HTTP 오프라인 테스트.

라이브(실 네이버 커머스API) 호출은 등록 IP에서만 가능하므로, 여기서는 httpx 를
가짜로 대체해 요청 형식(엔드포인트·파라미터·헤더·서명)과 응답 파싱·필드 매핑을
기계적으로 검증한다. 실제 응답 필드명은 라이브 첫 응답으로 확정한다(client 의
_to_order LIVE-RECONCILE 주석 참조) — 이 테스트의 가짜 JSON 과 매핑을 함께 고친다.
"""

from __future__ import annotations

import base64
import re

import bcrypt
import pytest

import ggotaiorder.mall.smartstore_client as sc_mod
from ggotaiorder.mall.models import MallCredential
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient

# 유효한 bcrypt salt (네이버 client_secret 형식)
_SALT = "$2b$12$R9h/cIPz0gi.URNNX3kh2O"


def _cred(cursor=None):
    return MallCredential(
        shop_key=19, shop_name="테스트꽃집", provider="smartstore",
        client_id="cid-abc", enc_client_secret="enc", extra={"seller_id": "ncp_x_01"},
        cursor=cursor, client_secret=_SALT,
    )


class FakeResp:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status
        self.text = str(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    """URL 경로로 응답을 라우팅하는 httpx 대역. 호출 기록을 남긴다."""

    def __init__(self, routes):
        self._routes = routes            # substring -> FakeResp
        self.calls = []                  # (method, url, kwargs)

    def _match(self, url):
        for key, resp in self._routes.items():
            if key in url:
                return resp
        raise AssertionError(f"라우트 없음: {url}")

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._match(url)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._match(url)


@pytest.fixture(autouse=True)
def _clear_token_cache():
    sc_mod._token_cache.clear()
    yield
    sc_mod._token_cache.clear()


def _token_resp():
    return FakeResp({"access_token": "TOK123", "expires_in": 10800, "token_type": "Bearer"})


def test_get_token_posts_form_with_valid_signature(monkeypatch):
    fake = FakeHttp({"/oauth2/token": _token_resp()})
    monkeypatch.setattr(sc_mod, "httpx", fake)

    client = HttpSmartStoreClient()
    token = client._get_token(_cred())

    assert token == "TOK123"
    method, url, kwargs = fake.calls[0]
    assert method == "POST" and url.endswith("/oauth2/token")
    data = kwargs["data"]
    assert data["client_id"] == "cid-abc"
    assert data["grant_type"] == "client_credentials"
    assert data["type"] == "SELF"
    # 서명 검증: bcrypt(f"{client_id}_{timestamp}", salt=secret) 의 base64
    ts = int(data["timestamp"])
    expected = base64.b64encode(
        bcrypt.hashpw(f"cid-abc_{ts}".encode(), _SALT.encode())
    ).decode()
    assert data["client_secret_sign"] == expected


def test_get_token_is_cached(monkeypatch):
    fake = FakeHttp({"/oauth2/token": _token_resp()})
    monkeypatch.setattr(sc_mod, "httpx", fake)
    client = HttpSmartStoreClient()

    client._get_token(_cred())
    client._get_token(_cred())

    token_posts = [c for c in fake.calls if "/oauth2/token" in c[1]]
    assert len(token_posts) == 1  # 두 번째는 캐시 사용


def _changed_resp(ids):
    return FakeResp({"data": {
        "lastChangeStatuses": [{"productOrderId": i, "productOrderStatus": "PAYED"} for i in ids],
        "lastChangedTo": "2026-07-04T12:00:00.000+09:00",
    }})


def _query_resp():
    return FakeResp({"data": [
        {
            "productOrder": {
                "productOrderId": "PO1",
                "productName": "장미 꽃다발",
                "quantity": 2,
                "totalPaymentAmount": 55000,
                "shippingAddress": {
                    "name": "박영희", "tel1": "010-1111-2222",
                    "baseAddress": "서울시 강남구 테헤란로 1",
                    "detailAddress": "3층",
                },
                "shippingMemo": "7월 5일 오후 3시 배송, 축 개업 리본, 카드: 번창하세요",
                "productOption": "색상: 레드",
            },
            "order": {
                "ordererName": "김철수", "ordererTel": "010-3333-4444",
                "orderId": "ORD1",
            },
        },
    ]})


def test_fetch_new_orders_maps_fields(monkeypatch):
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": _changed_resp(["PO1"]),
        "/product-orders/query": _query_resp(),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    client = HttpSmartStoreClient()
    orders, next_cursor = client.fetch_new_orders(_cred(cursor="2026-07-04T00:00:00.000+09:00"))

    assert len(orders) == 1
    o = orders[0]
    assert o.product_order_id == "PO1"
    # API 권위 필드
    assert o.fields.product_name == "장미 꽃다발"
    assert o.fields.quantity == 2
    assert o.fields.price == 55000
    assert o.fields.receiver_name == "박영희"
    assert o.fields.receiver_phone_number == "010-1111-2222"
    assert "강남구" in (o.fields.delivery_place or "")
    assert o.fields.customer_name == "김철수"
    assert o.fields.customer_phone_number == "010-3333-4444"
    # Gemini 병합 대상은 None (수집 단계에서 채움)
    assert o.fields.delivery_at is None
    assert o.fields.ribbon_congratulations is None
    # 메모 텍스트에 배송메모/옵션 포함(Gemini 입력)
    assert "축 개업" in o.memo_text and "레드" in o.memo_text
    # 커서는 응답의 lastChangedTo 로 전진
    assert next_cursor == "2026-07-04T12:00:00.000+09:00"


def test_fetch_new_orders_empty_skips_query(monkeypatch):
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": _changed_resp([]),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    client = HttpSmartStoreClient()
    orders, next_cursor = client.fetch_new_orders(_cred())

    assert orders == []
    assert next_cursor == "2026-07-04T12:00:00.000+09:00"
    # 신규 없으면 상세조회 호출 안 함
    assert not any("/product-orders/query" in c[1] for c in fake.calls)


def test_fetch_new_orders_sends_bearer_and_payed_filter(monkeypatch):
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": _changed_resp(["PO1"]),
        "/product-orders/query": _query_resp(),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    HttpSmartStoreClient().fetch_new_orders(_cred(cursor="2026-07-04T00:00:00.000+09:00"))

    changed = next(c for c in fake.calls if "/last-changed-statuses" in c[1])
    assert changed[0] == "GET"
    assert changed[2]["headers"]["Authorization"] == "Bearer TOK123"
    assert changed[2]["params"]["lastChangedType"] == "PAYED"
    assert changed[2]["params"]["lastChangedFrom"] == "2026-07-04T00:00:00.000+09:00"
    query = next(c for c in fake.calls if "/product-orders/query" in c[1])
    assert query[0] == "POST"
    assert query[2]["json"]["productOrderIds"] == ["PO1"]


def test_fetch_new_orders_normalizes_cursor_without_millis(monkeypatch):
    """밀리초 없는 커서를 그대로 보내면 네이버가 400 을 준다(라이브 확인).

    커서는 성공해야 전진하므로, 한 번 이런 값이 저장되면 폴링이 영구히 막힌다
    (실제로 2026-07-06 커서로 16일간 400 이 반복됐다).
    """
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": _changed_resp([]),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    HttpSmartStoreClient().fetch_new_orders(_cred(cursor="2026-07-06T01:26:05+00:00"))

    changed = next(c for c in fake.calls if "/last-changed-statuses" in c[1])
    assert changed[2]["params"]["lastChangedFrom"] == "2026-07-06T01:26:05.000+00:00"


def test_fetch_new_orders_normalizes_cursor_from_response(monkeypatch):
    """응답의 lastChangedTo 에 밀리초가 없어도 다음 요청에 쓸 수 있게 저장한다."""
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": FakeResp({"data": {
            "lastChangeStatuses": [],
            "lastChangedTo": "2026-07-22T10:00:00+09:00",
        }}),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    _, next_cursor = HttpSmartStoreClient().fetch_new_orders(_cred())

    assert next_cursor == "2026-07-22T10:00:00.000+09:00"


def test_fetch_new_orders_falls_back_when_cursor_unparseable(monkeypatch):
    """읽을 수 없는 커서는 기본 조회창으로 대체한다 — 400 으로 멈추지 않게."""
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/last-changed-statuses": _changed_resp([]),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    HttpSmartStoreClient().fetch_new_orders(_cred(cursor="쓰레기값"))

    changed = next(c for c in fake.calls if "/last-changed-statuses" in c[1])
    sent = changed[2]["params"]["lastChangedFrom"]
    assert sent != "쓰레기값"
    # 기본 조회창 형식(밀리초 포함)이어야 한다.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$", sent)


def test_confirm_order_posts_ids(monkeypatch):
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/product-orders/confirm": FakeResp({"data": {"successProductOrderIds": ["PO1"]}}),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    HttpSmartStoreClient().confirm_order(_cred(), "PO1")

    confirm = next(c for c in fake.calls if "/product-orders/confirm" in c[1])
    assert confirm[0] == "POST"
    assert confirm[2]["headers"]["Authorization"] == "Bearer TOK123"
    assert confirm[2]["json"]["productOrderIds"] == ["PO1"]


def test_confirm_order_raises_when_in_fail_list(monkeypatch):
    fake = FakeHttp({
        "/oauth2/token": _token_resp(),
        "/product-orders/confirm": FakeResp(
            {"data": {"successProductOrderIds": [], "failProductOrderIds": ["PO1"]}}
        ),
    })
    monkeypatch.setattr(sc_mod, "httpx", fake)

    with pytest.raises(RuntimeError):
        HttpSmartStoreClient().confirm_order(_cred(), "PO1")


def test_signature_still_deterministic():
    # 기존 계약 회귀: _make_signature 는 여전히 결정적
    c = HttpSmartStoreClient()
    a = c._make_signature("cid", _SALT, 1700000000000)
    b = c._make_signature("cid", _SALT, 1700000000000)
    assert a == b
