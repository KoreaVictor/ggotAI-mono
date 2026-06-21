import asyncio

from ggotaiorder.rpa.retry import RPA_MAX_ATTEMPTS, RpaRetryScanner


class FakeRepo:
    def __init__(self, manual_ids):
        self._manual_ids = manual_ids
        self.calls = []

    def list_manual_order_ids(self, max_attempts, shop_key):
        self.calls.append(("list", max_attempts, shop_key))
        return list(self._manual_ids)

    def increment_rpa_attempts(self, order_detail_id):
        self.calls.append(("increment", order_detail_id))


def test_scan_retries_each_manual_order():
    repo = FakeRepo([11, 22])
    events = []

    async def fake_enqueue(oid):
        events.append(("enqueue", oid))

    repo_increment = repo.increment_rpa_attempts

    def tracking_increment(oid):
        events.append(("increment", oid))
        return repo_increment(oid)

    repo.increment_rpa_attempts = tracking_increment

    scanner = RpaRetryScanner(enqueue_fn=fake_enqueue, repo=repo, shop_key=19)
    n = asyncio.run(scanner.scan_once())

    assert n == 2
    # 각 건마다 시도횟수를 먼저 올린 뒤 enqueue (무한재시도 차단: 상한 RPA_MAX_ATTEMPTS)
    assert events == [
        ("increment", 11), ("enqueue", 11),
        ("increment", 22), ("enqueue", 22),
    ]


def test_scan_passes_cap_and_shop_key():
    repo = FakeRepo([])

    async def fake_enqueue(oid):
        pass

    scanner = RpaRetryScanner(enqueue_fn=fake_enqueue, repo=repo, shop_key=19)
    asyncio.run(scanner.scan_once())
    assert repo.calls == [("list", RPA_MAX_ATTEMPTS, 19)]


def test_scan_continues_after_one_enqueue_fails():
    repo = FakeRepo([1, 2, 3])
    enqueued = []

    async def flaky_enqueue(oid):
        if oid == 2:
            raise RuntimeError("boom")
        enqueued.append(oid)

    scanner = RpaRetryScanner(enqueue_fn=flaky_enqueue, repo=repo, shop_key=19)
    n = asyncio.run(scanner.scan_once())

    assert n == 3  # 시도한 건수(예외 포함)
    assert enqueued == [1, 3]  # 2 실패해도 3 계속 처리


def test_scan_returns_zero_when_no_manual():
    repo = FakeRepo([])

    async def fake_enqueue(oid):
        raise AssertionError("enqueue 호출되면 안 됨")

    scanner = RpaRetryScanner(enqueue_fn=fake_enqueue, repo=repo, shop_key=19)
    assert asyncio.run(scanner.scan_once()) == 0
