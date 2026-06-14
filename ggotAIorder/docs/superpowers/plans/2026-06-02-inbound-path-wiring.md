# 인입 경로 배선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가게전화 Webhook(api)과 Supabase Realtime 구독을 `pipeline.process`에 연결하되, 채널별 분리 트리거로 이중 처리를 방지한다.

**Architecture:** api(가게전화)는 샵 판별 → 음성 Storage 적재 → server_call_history INSERT → `process(id)`를 BackgroundTask로 예약. Realtime은 INSERT 구독 후 `channel_order`가 핸드폰/가게음성일 때만 `process(id)` 예약. DB/Storage는 Protocol로 추상화(실제 Supabase 구현 + 테스트 fake). 라이브 구동은 체크리스트로 분리.

**Tech Stack:** Python 3.13, FastAPI, supabase-py 2.30.1, pytest, pytest-asyncio.

설계서: `docs/superpowers/specs/2026-06-02-inbound-path-wiring-design.md`
브랜치: `feature/inbound-path-wiring` (이미 생성됨)

**검증 명령 전제:** 모든 pytest/python은 `backend\.venv\Scripts\python.exe`로, 저장소 루트 `C:\ggotAI\ggotAIorder`에서 실행.

---

## File Structure

| 파일 | 책임 | 유형 |
| --- | --- | --- |
| `backend/src/ggotaiorder/api/repository.py` | `Shop`, `IngestRepository`(Protocol) + `SupabaseIngestRepository` (샵 판별·call_history INSERT) | 신규 |
| `backend/src/ggotaiorder/api/storage.py` | `AudioStorage`(Protocol) + `SupabaseAudioStorage` (음성 업로드) | 신규 |
| `backend/src/ggotaiorder/api/service.py` | `ingest_gate_phone(...)` 오케스트레이션 | 신규 |
| `backend/src/ggotaiorder/api/routes.py` | create_app + upload 라우트(Depends·service·BackgroundTasks) | 수정 |
| `backend/src/ggotaiorder/realtime/listener.py` | 실제 구독 + `_process_record` 채널 필터 | 수정 |
| `backend/tests/test_api_service.py` | service 단위테스트 | 신규 |
| `backend/tests/test_api_routes.py` | 라우트 TestClient 테스트 | 신규 |
| `backend/tests/test_realtime_listener.py` | `_process_record` 단위테스트 | 신규 |
| `backend/README.md` | 라이브 구동 체크리스트 추가 | 수정 |

---

### Task 1: api/repository.py — 샵 판별 + call_history INSERT

**Files:** Create `backend/src/ggotaiorder/api/repository.py`

`SupabaseIngestRepository`는 실 DB(통합 영역)라 단위테스트하지 않는다. Protocol 계약 고정 + import 확인. service 단위테스트(Task 3)는 fake로 한다.

- [ ] **Step 1: 구현 작성** — `backend/src/ggotaiorder/api/repository.py`:
```python
"""가게전화 인입용 DB 접근: 샵 판별 + server_call_history INSERT."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class Shop:
    shop_key: int
    shop_name: str


class IngestRepository(Protocol):
    """가게전화 인입이 필요로 하는 DB 연산 계약."""

    def find_shop_by_phone(self, phone: str) -> Optional[Shop]: ...

    def insert_call_history(self, record: dict) -> int: ...


class SupabaseIngestRepository:
    """Supabase 기반 IngestRepository 구현."""

    def find_shop_by_phone(self, phone: str) -> Optional[Shop]:
        client = get_client()
        # 1) setting_info 주문 전화번호(주문핸드폰/일반전화)에서 shop_key 탐색
        setting = (
            client.table("setting_info")
            .select("shop_key")
            .or_(
                f"order_landline_1.eq.{phone},order_landline_2.eq.{phone},"
                f"order_hp_1.eq.{phone},order_hp_2.eq.{phone}"
            )
            .limit(1)
            .execute()
        )
        shop_key: Optional[int] = setting.data[0]["shop_key"] if setting.data else None

        # 2) 폴백: member_info 가게전화/대표 핸드폰
        if shop_key is None:
            member = (
                client.table("member_info")
                .select("id")
                .or_(f"landline_number.eq.{phone},mobile_number.eq.{phone}")
                .limit(1)
                .execute()
            )
            shop_key = member.data[0]["id"] if member.data else None

        if shop_key is None:
            return None

        # 3) shop_name 조회
        info = (
            client.table("member_info")
            .select("shop_name")
            .eq("id", shop_key)
            .single()
            .execute()
        )
        return Shop(shop_key=shop_key, shop_name=info.data["shop_name"])

    def insert_call_history(self, record: dict) -> int:
        res = get_client().table("server_call_history").insert(record).execute()
        return res.data[0]["id"]
```

- [ ] **Step 2: import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.api.repository import Shop, IngestRepository, SupabaseIngestRepository; print('ok', Shop(1,'a').shop_name)"
```
Expected: `ok a` (네트워크 호출 없음).

- [ ] **Step 3: Commit**
```bash
git add backend/src/ggotaiorder/api/repository.py
git commit -m "feat: 가게전화 인입 repository(샵 판별·call_history INSERT) 추가"
```

---

### Task 2: api/storage.py — 음성 Storage 추상화

**Files:** Create `backend/src/ggotaiorder/api/storage.py`

- [ ] **Step 1: 구현 작성** — `backend/src/ggotaiorder/api/storage.py`:
```python
"""가게전화 음성 파일 Storage 적재 추상화."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Protocol
from uuid import uuid4

from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)

AUDIO_BUCKET = "call-audio"


class AudioStorage(Protocol):
    """음성 파일 저장 계약."""

    def upload_audio(self, data: bytes, shop_key: int, filename: str) -> str: ...


class SupabaseAudioStorage:
    """Supabase Storage 기반 구현. 객체 경로 `{shop_key}/{uuid}{ext}` 반환."""

    def upload_audio(self, data: bytes, shop_key: int, filename: str) -> str:
        ext = PurePosixPath(filename).suffix or ".bin"
        object_name = f"{shop_key}/{uuid4().hex}{ext}"
        get_client().storage.from_(AUDIO_BUCKET).upload(object_name, data)
        return object_name
```

- [ ] **Step 2: import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.api.storage import AudioStorage, SupabaseAudioStorage, AUDIO_BUCKET; print('ok', AUDIO_BUCKET)"
```
Expected: `ok call-audio`.

- [ ] **Step 3: Commit**
```bash
git add backend/src/ggotaiorder/api/storage.py
git commit -m "feat: 가게전화 음성 Storage 추상화 추가"
```

---

### Task 3: api/service.py — ingest_gate_phone (TDD)

**Files:** Create `backend/src/ggotaiorder/api/service.py`, `backend/tests/test_api_service.py`

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/test_api_service.py`:
```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api_service.py -v`
Expected: FAIL (ImportError: cannot import name 'ingest_gate_phone').

- [ ] **Step 3: 구현 작성** — `backend/src/ggotaiorder/api/service.py`:
```python
"""가게전화 업로드 인입 오케스트레이션: 샵 판별 → Storage 적재 → call_history INSERT."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ggotaiorder.api.repository import IngestRepository
from ggotaiorder.api.storage import AudioStorage

logger = logging.getLogger(__name__)


async def ingest_gate_phone(
    *,
    file_bytes: bytes,
    filename: str,
    caller_number: str,
    call_duration: int,
    user_phone_number: str,
    repo: IngestRepository,
    storage: AudioStorage,
) -> Optional[int]:
    """가게전화 1건을 인입한다.

    샵을 판별하지 못하면 None(라우트가 400). 성공 시 새 call_history_id.
    """
    shop = repo.find_shop_by_phone(user_phone_number)
    if shop is None:
        logger.warning("샵 판별 실패 — user_phone_number=%s", user_phone_number)
        return None

    object_name = storage.upload_audio(file_bytes, shop.shop_key, filename)
    now = datetime.now()
    record = {
        "channel_order": "가게전화",
        "channel_classification": user_phone_number,
        "customer_phone_number": caller_number,
        "shop_key": shop.shop_key,
        "shop_name": shop.shop_name,
        "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"),
        "duration_seconds": call_duration,
        "audio_file_name": object_name,
        "is_order": "N",
    }
    return repo.insert_call_history(record)
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**
```bash
git add backend/src/ggotaiorder/api/service.py backend/tests/test_api_service.py
git commit -m "feat: 가게전화 인입 service(ingest_gate_phone) 추가"
```

---

### Task 4: api/routes.py — 라우트 배선 (TDD, TestClient)

**Files:** Modify `backend/src/ggotaiorder/api/routes.py`; create `backend/tests/test_api_routes.py`

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/test_api_routes.py`:
```python
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


def _client(app):
    return TestClient(app)


def test_health():
    app = routes.create_app()
    r = _client(app).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_upload_accepted_and_schedules_process(monkeypatch):
    app = routes.create_app()
    app.dependency_overrides[routes.get_ingest_repository] = lambda: FakeRepo(Shop(2, "꽃집"))
    app.dependency_overrides[routes.get_audio_storage] = lambda: FakeStorage()
    scheduled: list[int] = []

    async def spy_process(call_history_id: int) -> None:
        scheduled.append(call_history_id)

    monkeypatch.setattr(routes, "process", spy_process)

    r = _client(app).post(
        "/api/v1/gate-phone/upload",
        data={"caller_number": "010-1", "call_duration": "30", "user_phone_number": "02-9"},
        files={"file": ("call.wav", b"bytes", "audio/wav")},
    )
    assert r.status_code == 200
    assert r.json()["call_history_id"] == 321
    assert scheduled == [321]  # background task ran (TestClient runs background tasks)


def test_upload_shop_not_found_returns_400(monkeypatch):
    app = routes.create_app()
    app.dependency_overrides[routes.get_ingest_repository] = lambda: FakeRepo(None)
    app.dependency_overrides[routes.get_audio_storage] = lambda: FakeStorage()
    monkeypatch.setattr(routes, "process", lambda call_history_id: None)

    r = _client(app).post(
        "/api/v1/gate-phone/upload",
        data={"caller_number": "010-1", "call_duration": "30", "user_phone_number": "02-0"},
        files={"file": ("call.wav", b"bytes", "audio/wav")},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api_routes.py -v`
Expected: FAIL (`get_ingest_repository` 없음 / 라우트가 process 예약 안 함).

- [ ] **Step 3: routes.py 전체 교체** — `backend/src/ggotaiorder/api/routes.py`:
```python
"""가게전화 VoIP Webhook 수신 API.

PRD 6-1: POST /api/v1/gate-phone/upload 로 통화 종료 웹훅(Multipart)을 수신해
음성 Storage 적재 → server_call_history INSERT → pipeline.process 를 백그라운드 예약.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, UploadFile

from ggotaiorder.api.repository import IngestRepository, SupabaseIngestRepository
from ggotaiorder.api.service import ingest_gate_phone
from ggotaiorder.api.storage import AudioStorage, SupabaseAudioStorage
from ggotaiorder.pipeline.engine import process

logger = logging.getLogger(__name__)


def get_ingest_repository() -> IngestRepository:
    """기본 IngestRepository 제공자(테스트에서 override)."""
    return SupabaseIngestRepository()


def get_audio_storage() -> AudioStorage:
    """기본 AudioStorage 제공자(테스트에서 override)."""
    return SupabaseAudioStorage()


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록해 반환한다."""
    app = FastAPI(title="ggotAIorder", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/gate-phone/upload")
    async def gate_phone_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile,
        caller_number: str = Form(...),
        call_duration: int = Form(...),
        user_phone_number: str = Form(...),
        repo: IngestRepository = Depends(get_ingest_repository),
        storage: AudioStorage = Depends(get_audio_storage),
    ) -> dict[str, object]:
        """통화 종료 웹훅을 수신해 인입 후 AI 파이프라인을 백그라운드 예약한다."""
        data = await file.read()
        call_history_id = await ingest_gate_phone(
            file_bytes=data,
            filename=file.filename or "audio.bin",
            caller_number=caller_number,
            call_duration=call_duration,
            user_phone_number=user_phone_number,
            repo=repo,
            storage=storage,
        )
        if call_history_id is None:
            raise HTTPException(status_code=400, detail="shop not found")
        background_tasks.add_task(process, call_history_id)
        return {"status": "accepted", "call_history_id": call_history_id}

    return app
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api_routes.py -v`
Expected: 3 passed. (StarletteDeprecationWarning은 무해 — 무시.)

- [ ] **Step 5: 스모크 호환 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_smoke.py -v`
Expected: 모두 pass (`test_fastapi_app_has_health_route`가 /health·/api/v1/gate-phone/upload 존재 확인).

- [ ] **Step 6: Commit**
```bash
git add backend/src/ggotaiorder/api/routes.py backend/tests/test_api_routes.py
git commit -m "feat: 가게전화 업로드 라우트 배선(service·BackgroundTasks·process)"
```

---

### Task 5: realtime/listener.py — 구독 + 채널 필터 (TDD)

**Files:** Modify `backend/src/ggotaiorder/realtime/listener.py`; create `backend/tests/test_realtime_listener.py`

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/test_realtime_listener.py`:
```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_realtime_listener.py -v`
Expected: FAIL (`_process_record` 없음).

- [ ] **Step 3: listener.py 전체 교체** — `backend/src/ggotaiorder/realtime/listener.py`:
```python
"""Supabase Realtime 감시.

PRD 6-2: public.server_call_history 의 INSERT 이벤트를 구독하여, 채널이
'핸드폰'/'가게음성'인 신규 행에 대해서만 pipeline.process 를 예약한다.
('가게전화'는 api가, '인터라넷'은 크롤러가 직접 처리 → 이중 처리 방지)
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.pipeline.engine import process

logger = logging.getLogger(__name__)

# Realtime이 직접 처리할 채널 (api/크롤러가 처리하는 채널은 제외)
_REALTIME_CHANNELS = {"핸드폰", "가게음성"}


class RealtimeListener:
    """server_call_history INSERT 구독 리스너."""

    def __init__(self) -> None:
        self._channel = None

    async def start(self) -> None:
        """Realtime 채널 구독을 시작한다 (라이브 검증은 체크리스트)."""
        client = get_client()
        self._channel = client.channel("server_call_history_inserts")
        self._channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="server_call_history",
            callback=self._on_message,
        )
        await self._channel.subscribe()
        logger.info("Realtime 구독 시작: server_call_history INSERT")

    async def stop(self) -> None:
        """구독을 해제한다."""
        if self._channel is not None:
            await self._channel.unsubscribe()
            self._channel = None
            logger.info("Realtime 구독 해제")

    def _on_message(self, payload: dict) -> None:
        """raw Realtime 메시지에서 record를 방어적으로 추출해 처리로 넘긴다."""
        try:
            record = (
                payload.get("data", {}).get("record")
                or payload.get("record")
                or payload.get("new")
            )
            if record:
                self._process_record(record)
        except Exception:  # noqa: BLE001 - 구독 유지를 위해 콜백 예외 흡수
            logger.exception("Realtime 콜백 처리 실패")

    def _process_record(self, record: dict) -> None:
        """채널이 핸드폰/가게음성이면 process(id)를 예약한다."""
        channel = record.get("channel_order")
        call_history_id = record.get("id")
        if channel in _REALTIME_CHANNELS and call_history_id is not None:
            asyncio.create_task(process(call_history_id))
        else:
            logger.debug(
                "Realtime skip: channel=%s id=%s", channel, call_history_id
            )
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_realtime_listener.py -v`
Expected: 4 passed.

- [ ] **Step 5: 스모크/오케스트레이터 import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "import ggotaiorder.realtime.listener, ggotaiorder.orchestrator; print('import ok')"
```
Expected: `import ok`.

- [ ] **Step 6: Commit**
```bash
git add backend/src/ggotaiorder/realtime/listener.py backend/tests/test_realtime_listener.py
git commit -m "feat: Realtime 구독 + 채널 필터(핸드폰/가게음성) process 예약"
```

---

### Task 6: 전체 검증 + README 라이브 체크리스트

**Files:** Modify `backend/README.md`

- [ ] **Step 1: 전체 스위트 실행** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: 모두 pass + 2 skipped(기존 라이브 Gemini). 신규: api_service 2 + api_routes 3 + realtime_listener 4 = 9 추가. 실제 합계를 보고.

- [ ] **Step 2: README 에 인입 경로 라이브 체크리스트 추가** — `backend/README.md`의 `## 구조` 섹션 바로 앞에 다음 섹션 삽입:
```markdown
## 인입 경로 라이브 구동 체크리스트

api Webhook·Realtime은 코드로 구현·오프라인 테스트되었으나, 실제 동작에는 다음 인프라가 필요합니다(인프라 준비 시 수행):

1. Supabase Storage에 비공개 버킷 `call-audio` 생성.
2. `server_call_history` 테이블 Realtime(Replication) 활성화.
3. `run_dev.py` 기동 후 멀티파트 업로드 → server_call_history 행 + order_details 생성 확인.
4. '핸드폰' 채널 행 INSERT(모바일 앱/수동) → Realtime이 process 트리거하는지 확인.

```

- [ ] **Step 3: Commit**
```bash
git add backend/README.md
git commit -m "docs: 인입 경로 라이브 구동 체크리스트 README 추가"
```

---

## Self-Review 결과

- **Spec 커버리지**: 채널별 트리거(Task4 api 직접 process·Task5 Realtime 채널필터) / api 분리 routes·service·repository·storage(Task1~4) / 샵 판별 setting_info→member_info(Task1) / INSERT 필드(Task3) / Storage 버킷·경로(Task2) / 에러 400·콜백 예외흡수(Task3·4·5) / 오프라인 테스트 service·route·listener(Task3·4·5) / 라이브 체크리스트(Task6) — 설계서 절 모두 매핑.
- **Placeholder 스캔**: repository/storage의 Supabase 구현은 통합 영역(라이브 체크리스트로 검증), 빈 placeholder 아님. TODO 없음.
- **타입 일관성**: `Shop(shop_key,shop_name)`, `IngestRepository.find_shop_by_phone/insert_call_history`, `AudioStorage.upload_audio(data,shop_key,filename)`, `ingest_gate_phone(*, file_bytes,filename,caller_number,call_duration,user_phone_number,repo,storage)->int|None`, `routes.get_ingest_repository/get_audio_storage/process`, `RealtimeListener._process_record(record)` — Task 간 시그니처 일치. 테스트의 fake가 동일 시그니처 구현.
- **검증 가능성**: service/route/listener 모두 fake/override/monkeypatch로 결정적 오프라인 테스트. 라이브는 체크리스트. 기존 39 회귀 유지.
- **주의(통합 영역)**: `find_shop_by_phone`의 supabase `.or_()` 필터·`insert_call_history`·Storage upload는 실 DB/버킷에서만 검증되므로 라이브 체크리스트로 확인. 버킷 미생성 시 업로드는 라이브에서 실패 → 체크리스트 1번 선행 필요.
