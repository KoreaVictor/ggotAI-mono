from ggotaiorder.mall.confirm_scanner import MallConfirmScanner
from ggotaiorder.mall.models import ConfirmTarget, MallCredential


def _cred(shop_key=1):
    return MallCredential(
        shop_key=shop_key, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )


class FakeCredRepo:
    def __init__(self, creds):
        self._creds = creds

    def list_credentials(self, provider):
        return list(self._creds)


class FakeOrderRepo:
    def __init__(self, targets):
        self._targets = targets
        self.acks = []
        self.increments = []
        self._attempts = {t.order_id: t.ack_attempts for t in targets}

    def list_confirmable(self, provider_marker):
        return list(self._targets)

    def increment_ack_attempts(self, order_id):
        self._attempts[order_id] = self._attempts.get(order_id, 0) + 1
        self.increments.append(order_id)
        return self._attempts[order_id]

    def mark_ack(self, order_id, status):
        self.acks.append((order_id, status))


class FakeClient:
    def __init__(self, raises=False):
        self._raises = raises
        self.confirmed = []

    def confirm_order(self, cred, product_order_id):
        if self._raises:
            raise RuntimeError("confirm failed")
        self.confirmed.append((cred.shop_key, product_order_id))

    def fetch_new_orders(self, cred):  # 미사용
        raise AssertionError("scanner 는 fetch 하지 않는다")


async def test_confirms_success_pending_target():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient()
    scanner = MallConfirmScanner()

    n = await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert n == 1
    assert client.confirmed == [(1, "PO1")]
    assert order_repo.acks == [(10, "confirmed")]


async def test_confirm_failure_retries_until_cap_then_skips():
    # ack_attempts=4 → increment 로 5(=상한) 도달, confirm 예외 → skipped
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=4)])
    client = FakeClient(raises=True)
    scanner = MallConfirmScanner()

    await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert order_repo.acks == [(10, "skipped")]


async def test_confirm_failure_below_cap_no_skip():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient(raises=True)
    scanner = MallConfirmScanner()

    await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert order_repo.acks == []  # 아직 상한 미만 → 다음 주기 재시도


async def test_missing_cred_shop_skipped():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=99, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient()
    scanner = MallConfirmScanner()

    n = await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert client.confirmed == []
    assert order_repo.acks == []
