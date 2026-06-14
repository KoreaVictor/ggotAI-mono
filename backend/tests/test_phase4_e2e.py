"""T3 E2E: 업로드→인입→파이프라인→싱글턴 RPA→백업→알림 배선 검증."""

import os
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from ggotaiorder.api import routes
from ggotaiorder.api.repository import Shop
from ggotaiorder.pipeline import engine
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.rpa import singleton_macro
from ggotaiorder.rpa.backup import BackupWriter
from ggotaiorder.rpa.models import RpaOrder


class FakeIngestRepo:
    def __init__(self):
        self.inserted = None

    def find_shop_by_phone(self, phone):
        return Shop(2, "꽃집")

    def insert_call_history(self, record):
        self.inserted = record
        return 555


class FakeStorage:
    def upload_audio(self, data, shop_key, filename):
        return f"{shop_key}/obj.wav"


class FakeOrderRepo:
    """engine.process 용. 업로드된 record 기반 CallHistory 반환."""

    def __init__(self, record):
        self._record = record
        self.inserted_payload = None
        self.is_order = None

    def get_call_history(self, call_history_id):
        r = self._record
        return CallHistory(
            id=call_history_id, shop_key=r["shop_key"], shop_name=r["shop_name"],
            customer_name=r.get("customer_name"), customer_phone_number=r["customer_phone_number"],
            stt_text="장미 2송이 내일 강남 배송", audio_file_name=r["audio_file_name"],
            channel_order=r["channel_order"],
        )

    def mark_processed(self, call_history_id, is_order):
        self.is_order = is_order

    def increment_attempts(self, call_history_id):
        pass

    def list_pending_call_ids(self, channels, max_attempts):
        return []

    def insert_order_details(self, payload):
        self.inserted_payload = payload
        return 777

    def update_stt_text(self, call_history_id, text):
        pass

    def delete_audio(self, name):
        pass


class FakeRpaRepo:
    def __init__(self, payload):
        self._payload = payload
        self.status = None

    def get_order(self, order_detail_id):
        p = self._payload
        return RpaOrder(
            order_detail_id=order_detail_id, shop_key=p["shop_key"], shop_name=p["shop_name"],
            channel="가게전화", customer_name=p["customer_name"],
            customer_phone_number=p["customer_phone_number"], product_name=p["product_name"],
            quantity=p["quantity"], price=p["price"], delivery_at=p["delivery_at"],
            delivery_place=p["delivery_place"], receiver_name=p["receiver_name"],
            receiver_phone_number=p["receiver_phone_number"], ribbon_sender=None,
            ribbon_congratulations=p["ribbon_congratulations"], card_message=p["card_message"],
        )

    def set_rpa_status(self, order_detail_id, status):
        self.status = status


class NotRunningAutomator:
    def is_program_running(self):
        return False

    def input_order(self, order):
        raise AssertionError("미구동인데 input_order 호출됨")


async def test_assembled_e2e_upload_to_backup_and_notify(monkeypatch, tmp_path):
    # --- 1) 업로드(api 인입) ---
    app = routes.create_app()
    ingest_repo = FakeIngestRepo()
    app.dependency_overrides[routes.get_ingest_repository] = lambda: ingest_repo
    app.dependency_overrides[routes.get_audio_storage] = lambda: FakeStorage()
    monkeypatch.setattr(routes, "process", lambda cid: None)  # 백그라운드는 별도 구동

    resp = TestClient(app).post(
        "/api/v1/gate-phone/upload",
        data={"caller_number": "010-1", "call_duration": "30", "user_phone_number": "02-9"},
        files={"file": ("call.wav", b"bytes", "audio/wav")},
    )
    assert resp.status_code == 200
    call_history_id = resp.json()["call_history_id"]
    assert call_history_id == 555
    assert ingest_repo.inserted["channel_order"] == "가게전화"

    # --- 2) 파이프라인(process) 실제 구동, RPA leg 는 fake 주입 enqueue 로 ---
    order_repo = FakeOrderRepo(ingest_repo.inserted)
    monkeypatch.setattr(
        engine, "extract_order",
        lambda text: OrderExtraction(
            customer_name="홍", customer_phone_number="010-1", product_name="장미",
            quantity=2, price=30000, delivery_at="2026-06-10T10:00:00+09:00",
            delivery_place="강남", receiver_name="이", receiver_phone_number="010-2",
            ribbon_congratulations="축", card_message="축하",
        ),
    )

    rpa_repo_holder = {}
    notify_calls = []

    async def spy_notify(order, success):
        notify_calls.append((order.order_detail_id, success))

    async def wired_enqueue(order_id):
        rpa_repo = FakeRpaRepo(order_repo.inserted_payload)
        rpa_repo_holder["repo"] = rpa_repo
        await singleton_macro.enqueue(
            order_id, repo=rpa_repo, automator=NotRunningAutomator(),
            backup=BackupWriter(tmp_path), notify=spy_notify,
        )

    monkeypatch.setattr(engine, "enqueue", wired_enqueue)

    await engine.process(call_history_id, repo=order_repo)

    # --- 3) 배선 단언 ---
    assert order_repo.is_order == "Y"
    assert order_repo.inserted_payload["product_name"] == "장미"
    assert rpa_repo_holder["repo"].status == "fail"  # 미구동→백업→fail
    assert notify_calls == [(777, False)]
    backups = list(tmp_path.glob("*.xlsx"))
    assert len(backups) == 1
    assert list(tmp_path.glob("*.txt"))


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_E2E") != "1" or not os.getenv("E2E_TEST_SHOP_KEY"),
    reason="풀 라이브 E2E 는 RUN_LIVE_E2E=1 + E2E_TEST_SHOP_KEY 필요",
)
async def test_full_live_e2e(monkeypatch, tmp_path):
    """실 Gemini + 실 Supabase. automator 미구동→백업, notify 는 spy."""
    from datetime import datetime

    from ggotaiorder.core.supabase_client import get_client
    from ggotaiorder.pipeline.repository import SupabaseOrderRepository
    from ggotaiorder.rpa.repository import SupabaseRpaRepository

    shop_key = int(os.environ["E2E_TEST_SHOP_KEY"])
    client = get_client()

    # 1) 테스트용 call_history 행 생성(가게전화, stt_text 주입 → STT 우회)
    now = datetime.now()
    rec = {
        "channel_order": "가게전화", "channel_classification": "E2E-TEST",
        "customer_phone_number": "010-0000-0000", "shop_key": shop_key,
        "shop_name": "E2E꽃집", "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"), "duration_seconds": 0,
        "audio_file_name": None,
        "stt_text": "장미 2송이 내일 오전 10시 강남구청 배송, 받는분 이영희 010-1111-2222",
        "is_order": "N",
    }

    notify_calls = []

    async def spy_notify(order, success):
        notify_calls.append((order.order_detail_id, success))

    async def wired_enqueue(order_id):
        await singleton_macro.enqueue(
            order_id, repo=SupabaseRpaRepository(), automator=NotRunningAutomator(),
            backup=BackupWriter(tmp_path), notify=spy_notify,
        )

    monkeypatch.setattr(engine, "enqueue", wired_enqueue)

    call_history_id = None
    try:
        ins = client.table("server_call_history").insert(rec).execute()
        assert ins.data, f"server_call_history insert 실패: {ins}"
        call_history_id = ins.data[0]["id"]

        # 2) 실 Gemini 추출 + 실 Supabase INSERT(process)
        await engine.process(call_history_id, repo=SupabaseOrderRepository())

        # 3) 검증: order_details 생성 + rpa_status 마킹 + 백업 + notify
        od = (
            client.table("order_details")
            .select("id, rpa_status, product_name")
            .eq("call_history_id", call_history_id)
            .execute()
        )
        assert od.data, "order_details 가 생성되지 않음"
        assert od.data[0]["rpa_status"] == "fail"  # 미구동→백업
        assert list(tmp_path.glob("*.xlsx"))
        assert len(notify_calls) == 1
        assert notify_calls[0][1] is False
    finally:
        # 4) 정리: call_history 삭제 → FK CASCADE 로 order_details 동반 삭제
        if call_history_id is not None:
            del_res = client.table("server_call_history").delete().eq("id", call_history_id).execute()
            assert del_res.data, f"cleanup DELETE 실패 — 행 누수 가능 id={call_history_id}"
