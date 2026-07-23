import asyncio

from ggotaiorder.realtime import listener as listener_mod
from ggotaiorder.realtime.listener import RealtimeListener


def _patch_process(monkeypatch):
    seen: list[int] = []

    async def spy(call_history_id: int) -> None:
        seen.append(call_history_id)

    monkeypatch.setattr(listener_mod, "process", spy)
    return seen


async def test_mobile_channel_triggers_process(monkeypatch):
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._process_record({"id": 11, "channel_order": "핸드폰"})
    await asyncio.sleep(0)  # 예약된 태스크 실행 기회
    assert seen == [11]


async def test_store_voice_channel_triggers_process(monkeypatch):
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._process_record({"id": 12, "channel_order": "가게음성"})
    await asyncio.sleep(0)
    assert seen == [12]


async def test_gate_phone_and_intranet_skipped(monkeypatch):
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._process_record({"id": 13, "channel_order": "가게전화"})
    rl._process_record({"id": 14, "channel_order": "인터라넷"})
    await asyncio.sleep(0)
    assert seen == []


async def test_missing_id_does_not_raise(monkeypatch):
    _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._process_record({"channel_order": "핸드폰"})  # id 없음 → 예외 없이 skip
    await asyncio.sleep(0)


async def test_on_message_extracts_and_processes(monkeypatch):
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._on_message({"data": {"record": {"id": 21, "channel_order": "핸드폰"}}})
    await asyncio.sleep(0)
    assert seen == [21]


async def test_on_message_empty_record_skips_without_processing(monkeypatch):
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener()
    rl._on_message({"data": {"record": {}}})  # 빈 record → process 미호출, 예외 없음
    await asyncio.sleep(0)
    assert seen == []


async def test_own_shop_record_processed(monkeypatch):
    """shop_key가 지정된 리스너는 자기 가게 record를 처리한다."""
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener(shop_key=19)
    rl._process_record({"id": 31, "channel_order": "핸드폰", "shop_key": 19})
    await asyncio.sleep(0)
    assert seen == [31]


async def test_other_shop_record_skipped(monkeypatch):
    """shop_key가 다른 가게 record는 방어적으로 skip한다(서버 필터 우회 대비)."""
    seen = _patch_process(monkeypatch)
    rl = RealtimeListener(shop_key=19)
    rl._process_record({"id": 32, "channel_order": "핸드폰", "shop_key": 20})
    await asyncio.sleep(0)
    assert seen == []


def _patch_enqueue(monkeypatch):
    """리스너가 부르는 RPA 투입을 가로챈다."""
    seen: list[int] = []

    async def spy(order_detail_id: int) -> None:
        seen.append(order_detail_id)

    monkeypatch.setattr(listener_mod, "enqueue", spy)
    return seen


async def test_order_released_to_ready_triggers_rpa(monkeypatch):
    """사장님이 보류 주문을 보완 저장하면(ready 전환) 즉시 자동입력으로 넘어가야 한다.

    ready 는 지금까지 쓰기만 하고 아무도 읽지 않아, 보완 저장해도 영원히 대기중이었다.
    """
    seen = _patch_enqueue(monkeypatch)
    rl = RealtimeListener(shop_key=19)

    rl._process_order_update({"id": 49, "shop_key": 19, "rpa_status": "ready"})
    await asyncio.sleep(0)

    assert seen == [49]


async def test_other_statuses_do_not_trigger_rpa(monkeypatch):
    """success/fail/manual/hold 로의 변경은 RPA 를 부르지 않는다(무한루프 방지)."""
    seen = _patch_enqueue(monkeypatch)
    rl = RealtimeListener(shop_key=19)

    for status in ("success", "fail", "manual", "hold"):
        rl._process_order_update({"id": 50, "shop_key": 19, "rpa_status": status})
    await asyncio.sleep(0)

    assert seen == []


async def test_other_shop_order_is_skipped(monkeypatch):
    """서버측 필터가 빠져도 남의 가게 주문은 처리하지 않는다."""
    seen = _patch_enqueue(monkeypatch)
    rl = RealtimeListener(shop_key=19)

    rl._process_order_update({"id": 51, "shop_key": 99, "rpa_status": "ready"})
    await asyncio.sleep(0)

    assert seen == []


async def test_order_update_without_id_does_not_raise(monkeypatch):
    _patch_enqueue(monkeypatch)
    rl = RealtimeListener(shop_key=19)

    rl._process_order_update({"shop_key": 19, "rpa_status": "ready"})
    await asyncio.sleep(0)


# --- watchdog: realtime-py 2.5.3 이 서버발 1001(ConnectionClosedOK)에 재연결을
#     안 걸어 소켓이 죽은 채 is_connected 만 True 로 남는 wedge 를 복구한다. ---


class _FakeTask:
    def __init__(self, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


class _FakeRealtime:
    def __init__(self, is_connected: bool, listen_task) -> None:
        self.is_connected = is_connected
        self._listen_task = listen_task


class _FakeClient:
    def __init__(self, *, is_connected: bool, listen_done: bool) -> None:
        self.realtime = _FakeRealtime(is_connected, _FakeTask(listen_done))


def test_healthy_when_connected_and_listen_alive():
    rl = RealtimeListener(shop_key=19)
    rl._client = _FakeClient(is_connected=True, listen_done=False)
    assert rl._is_connection_healthy() is True


def test_unhealthy_when_listen_task_done():
    """wedge: 소켓은 살아있다고(is_connected=True) 보이지만 listen 루프가 죽었다."""
    rl = RealtimeListener(shop_key=19)
    rl._client = _FakeClient(is_connected=True, listen_done=True)
    assert rl._is_connection_healthy() is False


def test_unhealthy_when_not_connected():
    rl = RealtimeListener(shop_key=19)
    rl._client = _FakeClient(is_connected=False, listen_done=False)
    assert rl._is_connection_healthy() is False


def test_unhealthy_when_no_client():
    rl = RealtimeListener(shop_key=19)
    assert rl._client is None
    assert rl._is_connection_healthy() is False


async def test_ensure_healthy_rebuilds_when_wedged(monkeypatch):
    """wedge 감지 시 stop() 후 start() 로 클라이언트를 통째 재생성해야 한다."""
    rl = RealtimeListener(shop_key=19)
    calls: list[str] = []

    async def stop_spy() -> None:
        calls.append("stop")

    async def start_spy() -> None:
        calls.append("start")

    monkeypatch.setattr(rl, "stop", stop_spy)
    monkeypatch.setattr(rl, "start", start_spy)
    monkeypatch.setattr(rl, "_is_connection_healthy", lambda: False)

    await rl.ensure_healthy()

    assert calls == ["stop", "start"]


async def test_ensure_healthy_noop_when_healthy(monkeypatch):
    """정상 연결이면 재생성하지 않는다(불필요한 churn 방지)."""
    rl = RealtimeListener(shop_key=19)
    calls: list[str] = []

    async def stop_spy() -> None:
        calls.append("stop")

    async def start_spy() -> None:
        calls.append("start")

    monkeypatch.setattr(rl, "stop", stop_spy)
    monkeypatch.setattr(rl, "start", start_spy)
    monkeypatch.setattr(rl, "_is_connection_healthy", lambda: True)

    await rl.ensure_healthy()

    assert calls == []

