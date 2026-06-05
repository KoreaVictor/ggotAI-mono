from ggotaiorder.pipeline import engine
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction


class FakeRepo:
    def __init__(self, row: CallHistory):
        self._row = row
        self.calls: list[tuple] = []
        self._next_order_id = 999

    def get_call_history(self, call_history_id: int) -> CallHistory:
        self.calls.append(("get", call_history_id))
        return self._row

    def update_stt_text(self, call_history_id: int, text: str) -> None:
        self.calls.append(("update_stt", call_history_id, text))

    def set_is_order(self, call_history_id: int, value: str) -> None:
        self.calls.append(("set_is_order", call_history_id, value))

    def insert_order_details(self, payload: dict) -> int:
        self.calls.append(("insert", payload))
        return self._next_order_id

    def delete_audio(self, audio_file_name) -> None:
        self.calls.append(("delete_audio", audio_file_name))


def _row(**kw) -> CallHistory:
    base = dict(
        id=1, shop_key=2, shop_name="꽃집", customer_name="신규",
        customer_phone_number="010-0000", stt_text="주문 텍스트",
        audio_file_name="INTRANET_CRAWLED", channel_order="인터라넷",
    )
    base.update(kw)
    return CallHistory(**base)


def _full_extraction() -> OrderExtraction:
    return OrderExtraction(
        customer_name="홍", customer_phone_number="010-1", product_name="장미",
        quantity=2, price=50000, delivery_at="내일", delivery_place="강남",
        receiver_name="이영희", receiver_phone_number="010-2",
        ribbon_congratulations="축", card_message="축하",
    )


async def test_order_path_inserts_and_enqueues(monkeypatch):
    repo = FakeRepo(_row())
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("set_is_order", 1, "Y") in repo.calls
    assert "insert" in kinds
    assert enqueued == [999]

    insert_payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert insert_payload["product_name"] == "장미"
    assert insert_payload["quantity"] == 2
    assert insert_payload["price"] == 50000
    assert insert_payload["receiver_name"] == "이영희"
    assert insert_payload["call_history_id"] == 1
    assert insert_payload["shop_key"] == 2
    assert insert_payload["rpa_status"] == "ready"


async def test_insert_failure_does_not_mark_is_order_Y(monkeypatch):
    """INSERT가 실패하면 set_is_order('Y') 부분쓰기가 남지 않아야 한다."""
    repo = FakeRepo(_row())

    def boom(payload):
        repo.calls.append(("insert", payload))
        raise RuntimeError("insert fail")

    repo.insert_order_details = boom  # type: ignore[method-assign]
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())

    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    # 주문 행 생성 실패 시 is_order='Y' 마킹과 enqueue 모두 일어나지 않아야 한다.
    assert ("set_is_order", 1, "Y") not in repo.calls
    assert enqueued == []


async def test_order_path_marks_Y_after_successful_insert(monkeypatch):
    """정상 경로에서 set_is_order('Y')는 INSERT 성공 이후에 호출돼야 한다."""
    repo = FakeRepo(_row())
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert kinds.index("insert") < kinds.index("set_is_order")


async def test_non_order_path_sets_N_and_no_insert(monkeypatch):
    repo = FakeRepo(_row(audio_file_name="call_001.wav"))
    monkeypatch.setattr(engine, "extract_order", lambda text: OrderExtraction())
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("set_is_order", 1, "N") in repo.calls
    assert "insert" not in kinds
    assert ("delete_audio", "call_001.wav") in repo.calls


async def test_stt_path_transcribes_then_processes(monkeypatch):
    repo = FakeRepo(_row(stt_text=None, audio_file_name="call_002.wav"))
    monkeypatch.setattr(engine, "transcribe", lambda name: "변환된 주문 텍스트")
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("update_stt", 1, "변환된 주문 텍스트") in repo.calls
    assert "insert" in kinds
    assert enqueued == [999]


async def test_stt_failure_skips(monkeypatch):
    repo = FakeRepo(_row(stt_text=None, audio_file_name="call_003.wav"))

    def boom(name):
        raise RuntimeError("stt fail")

    called = {"extract": False}

    def spy_extract(text):
        called["extract"] = True
        return _full_extraction()

    monkeypatch.setattr(engine, "transcribe", boom)
    monkeypatch.setattr(engine, "extract_order", spy_extract)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert "insert" not in kinds
    assert called["extract"] is False
