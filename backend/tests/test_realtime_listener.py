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
