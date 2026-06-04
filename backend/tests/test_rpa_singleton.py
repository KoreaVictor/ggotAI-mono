import asyncio

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.singleton_macro import enqueue


def _order(order_detail_id=7):
    return RpaOrder(
        order_detail_id=order_detail_id, shop_key=3, shop_name="꽃집", channel="전화",
        customer_name="홍", customer_phone_number="010", product_name="장미",
        quantity=1, price=1000, delivery_at=None, delivery_place=None,
        receiver_name=None, receiver_phone_number=None, ribbon_sender=None,
        ribbon_congratulations=None, card_message=None,
    )


class FakeRepo:
    def __init__(self, order):
        self._order = order
        self.statuses = []

    def get_order(self, order_detail_id):
        return self._order

    def set_rpa_status(self, order_detail_id, status):
        self.statuses.append((order_detail_id, status))


class FakeAutomator:
    def __init__(self, running, raises=False):
        self._running = running
        self._raises = raises
        self.inputs = []

    def is_program_running(self):
        return self._running

    def input_order(self, order):
        if self._raises:
            raise RuntimeError("input failed")
        self.inputs.append(order.order_detail_id)


class FakeBackup:
    def __init__(self):
        self.written = []

    def write(self, order):
        self.written.append(order.order_detail_id)
        return ("x.xlsx", "x.txt")


def _spy_notify():
    calls = []

    async def notify(order, success):
        calls.append((order.order_detail_id, success))

    return calls, notify


async def test_program_running_input_success():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert autom.inputs == [7]
    assert backup.written == []
    assert repo.statuses == [(7, "success")]
    assert calls == [(7, True)]


async def test_program_running_input_fails_backs_up():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=True, raises=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert backup.written == [7]
    assert repo.statuses == [(7, "fail")]
    assert calls == [(7, False)]


async def test_program_not_running_backs_up():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=False)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert autom.inputs == []
    assert backup.written == [7]
    assert repo.statuses == [(7, "fail")]
    assert calls == [(7, False)]


async def test_missing_order_skips():
    repo = FakeRepo(None)
    autom = FakeAutomator(running=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(999, repo=repo, automator=autom, backup=backup, notify=notify)

    assert repo.statuses == []
    assert backup.written == []
    assert calls == []


async def test_singleton_lock_serializes():
    import time

    active = {"count": 0, "max": 0}

    class SlowAutomator:
        def is_program_running(self):
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            time.sleep(0.02)
            active["count"] -= 1
            return False

        def input_order(self, order):
            pass

    autom = SlowAutomator()
    backup = FakeBackup()
    _, notify = _spy_notify()

    await asyncio.gather(
        enqueue(1, repo=FakeRepo(_order(1)), automator=autom, backup=backup, notify=notify),
        enqueue(2, repo=FakeRepo(_order(2)), automator=autom, backup=backup, notify=notify),
    )

    assert active["max"] == 1   # 락으로 동시 실행 0 → 최대 동시 1
