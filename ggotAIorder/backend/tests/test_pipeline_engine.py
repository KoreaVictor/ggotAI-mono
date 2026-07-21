import asyncio
from datetime import datetime, timezone, timedelta

from ggotaiorder.pipeline import engine
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction


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

    def mark_processed(self, call_history_id: int, is_order: str) -> None:
        self.calls.append(("mark_processed", call_history_id, is_order))

    def increment_attempts(self, call_history_id: int) -> None:
        self.calls.append(("increment_attempts", call_history_id))

    def list_pending_call_ids(self, channels, max_attempts, shop_key):
        return []

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
    assert ("mark_processed", 1, "Y") in repo.calls
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
    """INSERT가 실패하면 mark_processed('Y') 부분쓰기가 남지 않아야 한다."""
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
    assert ("mark_processed", 1, "Y") not in repo.calls
    assert enqueued == []


async def test_order_path_marks_Y_after_successful_insert(monkeypatch):
    """정상 경로에서 mark_processed('Y')는 INSERT 성공 이후에 호출돼야 한다."""
    repo = FakeRepo(_row())
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert kinds.index("insert") < kinds.index("mark_processed")


async def test_store_sale_product_and_price_only_inserts(monkeypatch):
    """매장판매: 상품명+가격만 있어도 주문 경로로 INSERT·enqueue 되어야 한다."""
    repo = FakeRepo(_row())
    store_sale = OrderExtraction(product_name="호접란", quantity=1, price=50000)
    monkeypatch.setattr(engine, "extract_order", lambda text: store_sale)
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("mark_processed", 1, "Y") in repo.calls
    assert "insert" in kinds
    assert enqueued == [999]

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["product_name"] == "호접란"
    assert payload["price"] == 50000
    # 배달/수령인 미상은 안전 기본값으로 채워진다.
    assert payload["receiver_name"] == "미정"
    assert payload["delivery_place"] == "미정"


async def test_store_sale_delivery_at_defaults_to_today(monkeypatch):
    """매장판매(가게음성)는 배송일 미상 시 주문일(오늘 KST)로 채운다.

    2099 센티넬로 등록되면 FlowerNT 주문목록(오늘/이번주 화면)에 안 보이므로,
    즉석 판매는 배송일=주문일로 맞춰 등록·노출이 정상화되게 한다.
    """
    repo = FakeRepo(_row(channel_order="가게음성"))
    sale = OrderExtraction(product_name="장미꽃다발", quantity=1, price=50000)
    monkeypatch.setattr(engine, "extract_order", lambda t: sale)

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    assert payload["delivery_at"] != DELIVERY_AT_UNKNOWN
    assert payload["delivery_at"].startswith(today)


async def test_phone_order_unknown_delivery_keeps_sentinel(monkeypatch):
    """매장판매가 아닌 채널은 배송일 미상 시 센티넬(2099) 유지(기존 설계 §6)."""
    repo = FakeRepo(_row(channel_order="핸드폰"))
    e = OrderExtraction(product_name="장미", price=50000)  # 배송일 미상이지만 주문
    monkeypatch.setattr(engine, "extract_order", lambda t: e)

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["delivery_at"] == DELIVERY_AT_UNKNOWN


async def test_non_order_path_sets_N_and_no_insert(monkeypatch):
    repo = FakeRepo(_row(audio_file_name="call_001.wav"))
    monkeypatch.setattr(engine, "extract_order", lambda text: OrderExtraction())
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("mark_processed", 1, "N") in repo.calls
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


async def test_increment_attempts_called_before_work(monkeypatch):
    repo = FakeRepo(_row())
    monkeypatch.setattr(engine, "extract_order", lambda t: _full_extraction())

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("increment_attempts", 1) in repo.calls
    # attempts 증가는 실제 작업(get) 이전에 일어나야 한다.
    assert kinds.index("increment_attempts") < kinds.index("get")


def _text_order_extraction() -> OrderExtraction:
    """카톡·문자 주문 중 RPA 등록 필수값이 모두 채워진 경우."""
    return OrderExtraction(
        product_name="근조화환", quantity=1, price=100000,
        delivery_at="2026-07-22T15:00:00+09:00",
        delivery_place="서울 강남구 논현로 1", receiver_name="김철수",
    )


def test_text_channels_are_processed_by_realtime():
    """카톡·문자도 Realtime·catch-up 처리 대상이어야 한다."""
    assert {"카톡", "문자"} <= engine.REALTIME_CHANNELS


async def test_text_channel_missing_required_holds_and_skips_rpa(monkeypatch):
    """카톡 주문에 필수값이 비면 rpa_status='hold'로 두고 RPA를 돌리지 않는다.

    누락된 채로 자동입력하면 FlowerNT 등록이 깨지거나 잘못된 주문이 들어가므로,
    사장님이 ggotAIya에서 채운 뒤 등록하게 한다.
    """
    repo = FakeRepo(_row(channel_order="카톡", audio_file_name=None))
    partial = OrderExtraction(product_name="근조화환", price=100000)  # 배송정보 없음
    monkeypatch.setattr(engine, "extract_order", lambda t: partial)
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    async def fake_notify(shop_key, channel, count, outcome):
        return True

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)
    monkeypatch.setattr(engine, "notify_send", fake_notify)

    await engine.process(1, repo=repo)

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["rpa_status"] == "hold"
    assert enqueued == []
    # 주문 행은 만들어졌으므로 수집 이력은 정상 종결돼야 한다(재처리 방지).
    assert ("mark_processed", 1, "Y") in repo.calls


async def test_hold_notifies_owner(monkeypatch):
    """보류만 하고 알리지 않으면 사장님이 주문이 온 줄 모른다 — 'hold' 알림을 보낸다."""
    repo = FakeRepo(_row(channel_order="문자", audio_file_name=None))
    monkeypatch.setattr(
        engine, "extract_order", lambda t: OrderExtraction(product_name="장미", price=50000)
    )
    sent: list[tuple] = []

    async def fake_notify(shop_key, channel, count, outcome):
        sent.append((shop_key, channel, count, outcome))
        return True

    monkeypatch.setattr(engine, "notify_send", fake_notify)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    assert sent == [(2, "문자", 1, "hold")]


async def test_hold_notification_failure_does_not_break_pipeline(monkeypatch):
    """알림이 죽어도 주문 행은 이미 저장됐으므로 처리 흐름은 정상 종료돼야 한다."""
    repo = FakeRepo(_row(channel_order="문자", audio_file_name=None))
    monkeypatch.setattr(
        engine, "extract_order", lambda t: OrderExtraction(product_name="장미", price=50000)
    )

    async def boom(shop_key, channel, count, outcome):
        raise RuntimeError("notifier down")

    monkeypatch.setattr(engine, "notify_send", boom)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    assert ("mark_processed", 1, "Y") in repo.calls


async def test_text_channel_complete_order_goes_to_rpa(monkeypatch):
    """카톡 주문이라도 필수값이 다 있으면 기존 경로대로 자동입력한다."""
    repo = FakeRepo(_row(channel_order="문자", audio_file_name=None))
    monkeypatch.setattr(engine, "extract_order", lambda t: _text_order_extraction())
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["rpa_status"] == "ready"
    assert enqueued == [999]


async def test_voice_channel_missing_required_still_goes_to_rpa(monkeypatch):
    """보류 게이트는 텍스트 채널 전용 — 통화 주문 경로는 무영향이어야 한다."""
    repo = FakeRepo(_row(channel_order="핸드폰"))
    partial = OrderExtraction(product_name="장미", price=50000)  # 배송정보 없음
    monkeypatch.setattr(engine, "extract_order", lambda t: partial)
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["rpa_status"] == "ready"
    assert enqueued == [999]


async def test_in_flight_guard_dedups_concurrent(monkeypatch):
    """같은 id로 동시 process()가 들어와도 한 번만 처리(Realtime↔스캔 중복 방지)."""
    repo = FakeRepo(_row())
    monkeypatch.setattr(engine, "extract_order", lambda t: _full_extraction())

    async def fake_enqueue(order_id: int) -> None:
        pass

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await asyncio.gather(
        engine.process(1, repo=repo), engine.process(1, repo=repo)
    )

    increments = [c for c in repo.calls if c[0] == "increment_attempts"]
    assert len(increments) == 1
    gets = [c for c in repo.calls if c[0] == "get"]
    assert len(gets) == 1

async def test_text_channel_without_price_is_still_an_order(monkeypatch):
    """카톡·문자는 가격을 안 적는 게 정상 — 상품명만 있어도 주문으로 받아 보류한다.

    실기기에서 확인된 유실: "사장님 근조화환 하나 부탁드려요"가 가격이 없다는 이유로
    is_order='N' 으로 폐기돼, 사장님이 주문이 온 줄도 몰랐다.
    """
    repo = FakeRepo(_row(channel_order="카톡", audio_file_name=None))
    no_price = OrderExtraction(product_name="근조화환")
    monkeypatch.setattr(engine, "extract_order", lambda t: no_price)
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    async def fake_notify(shop_key, channel, count, outcome):
        return True

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)
    monkeypatch.setattr(engine, "notify_send", fake_notify)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert "insert" in kinds, "가격이 없다는 이유로 주문이 폐기됐다"
    payload = next(c[1] for c in repo.calls if c[0] == "insert")
    assert payload["rpa_status"] == "hold"
    assert ("mark_processed", 1, "Y") in repo.calls
    assert enqueued == []


async def test_voice_channel_without_price_is_not_an_order(monkeypatch):
    """통화는 기존 규칙 유지 — 가격 없이는 주문으로 보지 않는다(잡담·광고 방어선)."""
    repo = FakeRepo(_row(channel_order="핸드폰"))
    no_price = OrderExtraction(product_name="장미")
    monkeypatch.setattr(engine, "extract_order", lambda t: no_price)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("mark_processed", 1, "N") in repo.calls
    assert "insert" not in kinds


async def test_text_channel_without_product_is_not_an_order(monkeypatch):
    """상품명조차 없으면 텍스트 채널에서도 주문이 아니다(잡담이 새어들지 않게)."""
    repo = FakeRepo(_row(channel_order="문자", audio_file_name=None))
    monkeypatch.setattr(engine, "extract_order", lambda t: OrderExtraction(price=50000))
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("mark_processed", 1, "N") in repo.calls
    assert "insert" not in kinds

