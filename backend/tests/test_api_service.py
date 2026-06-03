from ggotaiorder.api.repository import Shop
from ggotaiorder.api.service import ingest_gate_phone


class FakeRepo:
    def __init__(self, shop):
        self._shop = shop
        self.inserted: dict | None = None

    def find_shop_by_phone(self, phone):
        self.last_phone = phone
        return self._shop

    def insert_call_history(self, record):
        self.inserted = record
        return 777


class FakeStorage:
    def __init__(self):
        self.uploaded = None

    def upload_audio(self, data, shop_key, filename):
        self.uploaded = (data, shop_key, filename)
        return f"{shop_key}/obj.wav"


async def test_shop_found_uploads_inserts_returns_id():
    repo = FakeRepo(Shop(shop_key=5, shop_name="장미꽃집"))
    storage = FakeStorage()
    cid = await ingest_gate_phone(
        file_bytes=b"audio", filename="call.wav", caller_number="010-111",
        call_duration=42, user_phone_number="02-9999",
        repo=repo, storage=storage,
    )
    assert cid == 777
    assert storage.uploaded == (b"audio", 5, "call.wav")
    rec = repo.inserted
    assert rec["channel_order"] == "가게전화"
    assert rec["channel_classification"] == "02-9999"
    assert rec["customer_phone_number"] == "010-111"
    assert rec["shop_key"] == 5
    assert rec["shop_name"] == "장미꽃집"
    assert rec["duration_seconds"] == 42
    assert rec["audio_file_name"] == "5/obj.wav"
    assert rec["is_order"] == "N"
    assert "call_date" in rec and "call_time" in rec


async def test_shop_not_found_returns_none_no_insert():
    repo = FakeRepo(None)
    storage = FakeStorage()
    cid = await ingest_gate_phone(
        file_bytes=b"audio", filename="call.wav", caller_number="010-111",
        call_duration=42, user_phone_number="02-0000",
        repo=repo, storage=storage,
    )
    assert cid is None
    assert repo.inserted is None
    assert storage.uploaded is None
