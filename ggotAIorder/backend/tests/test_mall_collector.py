import ggotaiorder.mall.collector as collector_mod
from ggotaiorder.mall.collector import poll_once
from ggotaiorder.mall.models import MallCredential, SmartStoreOrder
from ggotaiorder.pipeline.models import OrderExtraction


def _cred(shop_key=1):
    return MallCredential(
        shop_key=shop_key, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )


def _order(product_order_id="PO1"):
    # API 권위값: 상품명·수량·가격·받는사람 등만 채우고 배달/리본/카드/분류는 None.
    return SmartStoreOrder(
        product_order_id=product_order_id,
        raw_text="원문 배송메모",
        memo_text="내일 오후 3시 축하합니다 김철수",
        fields=OrderExtraction(
            product_name="장미꽃다발", quantity=2, price=50000,
            receiver_name="박영희", receiver_phone_number="01011112222",
            delivery_place="서울시 강남구",
        ),
    )


class FakeCredRepo:
    def __init__(self, creds):
        self._creds = creds
        self.cursor_updates = []

    def list_credentials(self, provider):
        return list(self._creds)

    def update_cursor(self, shop_key, provider, cursor):
        self.cursor_updates.append((shop_key, provider, cursor))


class FakeOrderRepo:
    def __init__(self, existing=None):
        self._existing = set(existing or [])
        self.calls = []
        self._next_id = 100

    def order_exists(self, shop_key, product_order_id):
        return (shop_key, product_order_id) in self._existing

    def insert_call_history(self, record):
        self.calls.append(("call", record))
        self._next_id += 1
        return self._next_id

    def insert_order_details(self, payload):
        self.calls.append(("order", payload))
        self._next_id += 1
        return self._next_id


class FakeClient:
    def __init__(self, orders_by_shop=None, raises=False, cursor="C-NEXT"):
        self._orders_by_shop = orders_by_shop or {}
        self._raises = raises
        self._cursor = cursor

    def fetch_new_orders(self, cred):
        if self._raises:
            raise RuntimeError("commerce api failed")
        return list(self._orders_by_shop.get(cred.shop_key, [])), self._cursor

    def confirm_order(self, cred, product_order_id):  # 미사용(수집 경로)
        raise AssertionError("collector 는 confirm 하지 않는다")


def _fake_extract_factory(soft):
    def _extract(text):
        return soft
    return _extract


def _make_notify(notified):
    async def _notify(shop_key):
        notified.append(shop_key)
    return _notify


def _patch_common(monkeypatch):
    enqueued = []

    async def fake_enqueue(order_id):
        enqueued.append(order_id)

    monkeypatch.setattr(collector_mod, "enqueue", fake_enqueue)
    monkeypatch.setattr(collector_mod, "decrypt", lambda enc, key: "plain-secret")
    return enqueued


async def test_new_order_inserts_enqueues_and_updates_cursor(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo()
    client = FakeClient({1: [_order("PO1")]}, cursor="C-NEXT")
    soft = OrderExtraction(
        delivery_at="2026-07-05T15:00:00+09:00", delivery_at_text="내일 오후 3시",
        ribbon_congratulations="축 개업", card_message="축하합니다", sang_divi="생화",
        product_name="무시되어야함", price=999,  # API 권위값이 이겨야 함
    )

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_fake_extract_factory(soft),
    )

    kinds = [c[0] for c in order_repo.calls]
    assert "call" in kinds and "order" in kinds
    call_record = next(c[1] for c in order_repo.calls if c[0] == "call")
    assert call_record["channel_order"] == "쇼핑몰"
    assert call_record["channel_classification"] == "PO1"
    assert call_record["audio_file_name"] == "SMARTSTORE_API"
    assert call_record["stt_text"] == "원문 배송메모"
    order_payload = next(c[1] for c in order_repo.calls if c[0] == "order")
    # 하이브리드: API 권위값 유지
    assert order_payload["product_name"] == "장미꽃다발"
    assert order_payload["price"] == 50000
    assert order_payload["receiver_name"] == "박영희"
    # soft 에서 취한 필드
    assert order_payload["delivery_at"] == "2026-07-05T15:00:00+09:00"
    assert order_payload["ribbon_congratulations"] == "축 개업"
    assert order_payload["card_message"] == "축하합니다"
    assert order_payload["sang_divi"] == "생화"
    # 상태 플래그
    assert order_payload["rpa_status"] == "ready"
    assert order_payload["mall_ack_status"] == "pending"
    assert len(enqueued) == 1
    assert cred_repo.cursor_updates == [(1, "smartstore", "C-NEXT")]


async def test_duplicate_order_skipped(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo(existing={(1, "PO1")})
    client = FakeClient({1: [_order("PO1")]})

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_fake_extract_factory(OrderExtraction()),
    )

    assert order_repo.calls == []
    assert enqueued == []
    # 중복이어도 커서는 갱신(그 shop 처리 완료)
    assert cred_repo.cursor_updates == [(1, "smartstore", "C-NEXT")]


async def test_gemini_failure_still_loads_authoritative_fields(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred_repo = FakeCredRepo([_cred()])
    order_repo = FakeOrderRepo()
    client = FakeClient({1: [_order("PO1")]})

    def _boom(text):
        raise RuntimeError("gemini down")

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_boom,
    )

    order_payload = next(c[1] for c in order_repo.calls if c[0] == "order")
    assert order_payload["product_name"] == "장미꽃다발"  # 유실 없음
    assert order_payload["delivery_at_text"] is None       # soft 없음
    assert len(enqueued) == 1


async def test_three_consecutive_fetch_failures_notify(monkeypatch):
    _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred_repo = FakeCredRepo([_cred()])
    order_repo = FakeOrderRepo()
    client = FakeClient(raises=True)
    notify = _make_notify(notified)
    kw = dict(cred_repo=cred_repo, order_repo=order_repo, client=client,
              notify=notify, extract=_fake_extract_factory(OrderExtraction()))

    await poll_once(**kw)
    await poll_once(**kw)
    assert notified == []
    await poll_once(**kw)
    assert notified == [1]
    # 실패 시 커서 미갱신
    assert cred_repo.cursor_updates == []


async def test_success_resets_failure_counter(monkeypatch):
    _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo()
    failing = FakeClient(raises=True)
    ok = FakeClient({1: []})
    notify = _make_notify(notified)
    empty = _fake_extract_factory(OrderExtraction())

    async def run(client):
        await poll_once(cred_repo=cred_repo, order_repo=order_repo, client=client,
                        notify=notify, extract=empty)

    await run(failing)
    await run(failing)
    await run(ok)       # 리셋
    await run(failing)
    await run(failing)
    assert notified == []


async def test_multiple_shops_isolated(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred_repo = FakeCredRepo([_cred(1), _cred(2)])
    order_repo = FakeOrderRepo()
    # shop 1 은 예외를 던지는 게 아니라, 둘 다 주문 1건씩 정상.
    client = FakeClient({1: [_order("PO1")], 2: [_order("PO2")]})

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify(notified), extract=_fake_extract_factory(OrderExtraction()),
    )

    order_payloads = [c[1] for c in order_repo.calls if c[0] == "order"]
    assert {p["shop_key"] for p in order_payloads} == {1, 2}
    assert len(enqueued) == 2
