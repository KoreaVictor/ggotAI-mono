import ggotaiorder.scraper.crawler as crawler_mod
from ggotaiorder.pipeline.models import OrderExtraction
from ggotaiorder.scraper.crawler import poll_once
from ggotaiorder.scraper.models import IntranetShop, ScrapedOrder


def _shop(shop_key=1):
    return IntranetShop(
        shop_key=shop_key, shop_name="꽃집", url="https://intra",
        username="u", enc_password="enc",
    )


def _order(order_no="A1"):
    return ScrapedOrder(
        order_no=order_no,
        raw_text="원문 주문",
        fields=OrderExtraction(product_name="장미", quantity=2, price=30000),
    )


class FakeRepo:
    def __init__(self, shops, existing=None):
        self._shops = shops
        self._existing = set(existing or [])
        self.calls = []
        self._next_id = 100

    def list_intranet_shops(self):
        return list(self._shops)

    def order_exists(self, shop_key, order_no):
        return (shop_key, order_no) in self._existing

    def insert_call_history(self, record):
        self.calls.append(("call", record))
        self._next_id += 1
        return self._next_id

    def insert_order_details(self, payload):
        self.calls.append(("order", payload))
        self._next_id += 1
        return self._next_id


class FakeScraper:
    def __init__(self, orders_by_url=None, raises=False):
        self._orders_by_url = orders_by_url or {}
        self._raises = raises

    def fetch_orders(self, url, username, password):
        if self._raises:
            raise RuntimeError("scrape failed")
        return self._orders_by_url.get(url, [])


def _make_notify(notified_list):
    async def _notify(shop_key):
        notified_list.append(shop_key)
    return _notify


def _patch_common(monkeypatch):
    enqueued = []

    async def fake_enqueue(order_id):
        enqueued.append(order_id)

    monkeypatch.setattr(crawler_mod, "enqueue", fake_enqueue)
    monkeypatch.setattr(crawler_mod, "decrypt", lambda enc, key: "plain-pw")
    return enqueued


async def test_new_order_inserts_and_enqueues(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    notified = []
    shop = _shop()
    repo = FakeRepo([shop])
    scraper = FakeScraper({shop.url: [_order("A1")]})

    await poll_once(repo=repo, scraper=scraper, notify=_make_notify(notified))

    kinds = [c[0] for c in repo.calls]
    assert "call" in kinds and "order" in kinds
    call_record = next(c[1] for c in repo.calls if c[0] == "call")
    assert call_record["channel_order"] == "인터라넷"
    assert call_record["channel_classification"] == "A1"
    assert call_record["audio_file_name"] == crawler_mod.INTRANET_AUDIO_MARKER
    assert call_record["stt_text"] == "원문 주문"
    order_payload = next(c[1] for c in repo.calls if c[0] == "order")
    assert order_payload["product_name"] == "장미"
    assert order_payload["rpa_status"] == "ready"
    assert len(enqueued) == 1


async def test_duplicate_order_skipped(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    shop = _shop()
    repo = FakeRepo([shop], existing={(1, "A1")})
    scraper = FakeScraper({shop.url: [_order("A1")]})

    await poll_once(repo=repo, scraper=scraper, notify=_make_notify([]))

    assert repo.calls == []
    assert enqueued == []


async def test_three_consecutive_failures_notify(monkeypatch):
    _patch_common(monkeypatch)
    crawler_mod._failure_counts.clear()
    notified = []
    shop = _shop()
    repo = FakeRepo([shop])
    scraper = FakeScraper(raises=True)
    notify = _make_notify(notified)

    await poll_once(repo=repo, scraper=scraper, notify=notify)
    await poll_once(repo=repo, scraper=scraper, notify=notify)
    assert notified == []
    await poll_once(repo=repo, scraper=scraper, notify=notify)
    assert notified == [1]


async def test_success_resets_failure_counter(monkeypatch):
    _patch_common(monkeypatch)
    crawler_mod._failure_counts.clear()
    notified = []
    shop = _shop()
    repo = FakeRepo([shop])
    failing = FakeScraper(raises=True)
    ok = FakeScraper({shop.url: []})
    notify = _make_notify(notified)

    await poll_once(repo=repo, scraper=failing, notify=notify)
    await poll_once(repo=repo, scraper=failing, notify=notify)
    await poll_once(repo=repo, scraper=ok, notify=notify)
    await poll_once(repo=repo, scraper=failing, notify=notify)
    await poll_once(repo=repo, scraper=failing, notify=notify)
    assert notified == []
