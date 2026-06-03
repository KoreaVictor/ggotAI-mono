from fastapi.testclient import TestClient

from ggotaiorder.api import routes
from ggotaiorder.api.repository import Shop


class FakeRepo:
    def __init__(self, shop):
        self._shop = shop
        self.inserted = None

    def find_shop_by_phone(self, phone):
        return self._shop

    def insert_call_history(self, record):
        self.inserted = record
        return 321


class FakeStorage:
    def upload_audio(self, data, shop_key, filename):
        return f"{shop_key}/obj.wav"


def test_health():
    app = routes.create_app()
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_upload_accepted_and_schedules_process(monkeypatch):
    app = routes.create_app()
    app.dependency_overrides[routes.get_ingest_repository] = lambda: FakeRepo(Shop(2, "꽃집"))
    app.dependency_overrides[routes.get_audio_storage] = lambda: FakeStorage()
    scheduled: list[int] = []

    async def spy_process(call_history_id: int) -> None:
        scheduled.append(call_history_id)

    monkeypatch.setattr(routes, "process", spy_process)

    r = TestClient(app).post(
        "/api/v1/gate-phone/upload",
        data={"caller_number": "010-1", "call_duration": "30", "user_phone_number": "02-9"},
        files={"file": ("call.wav", b"bytes", "audio/wav")},
    )
    assert r.status_code == 200
    assert r.json()["call_history_id"] == 321
    assert scheduled == [321]


def test_upload_shop_not_found_returns_400(monkeypatch):
    app = routes.create_app()
    app.dependency_overrides[routes.get_ingest_repository] = lambda: FakeRepo(None)
    app.dependency_overrides[routes.get_audio_storage] = lambda: FakeStorage()
    monkeypatch.setattr(routes, "process", lambda call_history_id: None)

    r = TestClient(app).post(
        "/api/v1/gate-phone/upload",
        data={"caller_number": "010-1", "call_duration": "30", "user_phone_number": "02-0"},
        files={"file": ("call.wav", b"bytes", "audio/wav")},
    )
    assert r.status_code == 400
