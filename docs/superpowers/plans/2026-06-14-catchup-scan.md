# 부팅 시 catch-up 스캔 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PC가 꺼져 있던/절전 동안 누락된 핸드폰·가게음성 통화 행을, 부팅 시 1회 + 30분 주기로 자동 스캔해 기존 파이프라인으로 일괄 처리한다.

**Architecture:** `server_call_history`에 `processed_at`/`process_attempts` 컬럼을 추가해 "미처리"를 명확히 표시한다. `pipeline.process()`는 종결 시 `processed_at`을 찍고, 모듈 레벨 in-flight 가드로 Realtime과의 중복 처리를 막는다. 새 `CatchupScanner`가 미처리 행을 조회해 순차 처리하며, 오케스트레이터가 부팅 1회 + APScheduler 30분 주기로 호출한다.

**Tech Stack:** Python 3.13, supabase-py(PostgREST), APScheduler(AsyncIOScheduler), pytest + pytest-asyncio(asyncio_mode=auto).

**공통 실행 명령:** 테스트는 `backend` 디렉터리에서
`.venv\Scripts\python.exe -m pytest <경로> -v` 로 실행한다.

---

## File Structure

- **Modify** `docs/database_schema.sql` — `server_call_history`에 컬럼 2개 추가(계약 단일 출처).
- **Create** `docs/migrations/2026-06-14-catchup-scan.sql` — 라이브 적용용 ALTER 문.
- **Modify** `backend/src/ggotaiorder/pipeline/repository.py` — Protocol/Supabase 구현: `set_is_order`→`mark_processed`, `list_pending_call_ids`, `increment_attempts` 추가.
- **Modify** `backend/src/ggotaiorder/pipeline/engine.py` — in-flight 가드, attempts 증가, `mark_processed` 사용. `MAX_ATTEMPTS` 상수.
- **Create** `backend/src/ggotaiorder/pipeline/catchup.py` — `CatchupScanner.scan_once()`.
- **Modify** `backend/src/ggotaiorder/orchestrator.py` — 부팅 1회 스캔 + 30분 주기 잡.
- **Modify** `backend/tests/test_pipeline_engine.py` — FakeRepo·단언 갱신 + 신규 테스트.
- **Modify** `backend/tests/test_phase4_e2e.py` — FakeRepo의 `set_is_order`→`mark_processed`.
- **Create** `backend/tests/test_pipeline_catchup.py` — 스캐너 테스트.

---

## Task 1: DB 마이그레이션 (스키마 계약 + ALTER SQL)

**Files:**
- Modify: `docs/database_schema.sql` (server_call_history 정의)
- Create: `docs/migrations/2026-06-14-catchup-scan.sql`

- [ ] **Step 1: `docs/database_schema.sql`의 server_call_history에 컬럼 2개 추가**

`is_order CHAR(1) DEFAULT 'N',` 줄 **바로 아래**에 다음 두 줄을 추가:

```sql
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL, -- 파이프라인 종결(Y/N) 시각. NULL=미처리(catch-up 대상)
    process_attempts INT NOT NULL DEFAULT 0,            -- 처리 시도 횟수(영구 실패 행의 무한 재시도 차단용)
```

- [ ] **Step 2: 마이그레이션 SQL 파일 작성**

`docs/migrations/2026-06-14-catchup-scan.sql`:

```sql
-- 2026-06-14 부팅 시 catch-up 스캔: 미처리 핸드폰/가게음성 행 식별용 컬럼.
-- 둘 다 nullable/default 이므로 ggotAIhp 기존 INSERT 무손상.
ALTER TABLE server_call_history
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS process_attempts INT NOT NULL DEFAULT 0;

-- 미처리 행 조회 가속(부분 인덱스: 미종결 행만).
CREATE INDEX IF NOT EXISTS idx_sch_pending
    ON server_call_history (channel_order, process_attempts)
    WHERE processed_at IS NULL;
```

- [ ] **Step 3: 스키마 계약 테스트가 깨지지 않는지 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_phase4_schema_contract.py tests/test_phase4_frontend_schema.py -v`
Expected: PASS (새 컬럼은 nullable/default라 기존 단언 불변. 실패 시 컬럼 집합을 하드코딩한 단언이 있는지 확인해 신규 컬럼 반영).

- [ ] **Step 4: Commit**

```bash
git add docs/database_schema.sql docs/migrations/2026-06-14-catchup-scan.sql
git commit -m "feat(db): catch-up용 processed_at/process_attempts 컬럼 + 마이그레이션"
```

---

## Task 2: 리포지토리 계약 — mark_processed / list_pending_call_ids / increment_attempts

**Files:**
- Modify: `backend/src/ggotaiorder/pipeline/repository.py`

- [ ] **Step 1: Protocol 갱신**

`repository.py`의 `OrderRepository(Protocol)` 안에서 `set_is_order` 줄을 삭제하고 아래로 교체:

```python
    def mark_processed(self, call_history_id: int, is_order: str) -> None: ...

    def increment_attempts(self, call_history_id: int) -> None: ...

    def list_pending_call_ids(
        self, channels: set[str], max_attempts: int
    ) -> list[int]: ...
```

(`update_stt_text`, `get_call_history`, `insert_order_details`, `delete_audio` 는 그대로 유지.)

- [ ] **Step 2: import에 datetime 추가**

`repository.py` 상단 import 블록에 추가:

```python
from datetime import datetime, timezone
```

- [ ] **Step 3: SupabaseOrderRepository 구현 교체/추가**

`SupabaseOrderRepository`의 `set_is_order` 메서드를 삭제하고 아래 세 메서드로 교체:

```python
    def mark_processed(self, call_history_id: int, is_order: str) -> None:
        get_client().table("server_call_history").update(
            {
                "is_order": is_order,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", call_history_id).execute()

    def increment_attempts(self, call_history_id: int) -> None:
        # PostgREST에 원자적 increment가 없어 read-modify-write 한다.
        # in-flight 가드가 동일 id 동시 처리를 막으므로 경합 없음(단일 PC).
        res = (
            get_client()
            .table("server_call_history")
            .select("process_attempts")
            .eq("id", call_history_id)
            .single()
            .execute()
        )
        current = res.data.get("process_attempts") or 0
        get_client().table("server_call_history").update(
            {"process_attempts": current + 1}
        ).eq("id", call_history_id).execute()

    def list_pending_call_ids(
        self, channels: set[str], max_attempts: int
    ) -> list[int]:
        res = (
            get_client()
            .table("server_call_history")
            .select("id")
            .in_("channel_order", list(channels))
            .is_("processed_at", "null")
            .lt("process_attempts", max_attempts)
            .order("id")
            .execute()
        )
        return [r["id"] for r in res.data]
```

- [ ] **Step 4: import 정합성만 빠르게 확인**

Run: `.venv\Scripts\python.exe -c "import ggotaiorder.pipeline.repository"`
Expected: 에러 없이 종료(import OK). 실행 전 `PYTHONPATH`에 `backend\src`가 잡혀 있어야 함 — 이미 venv editable 설치면 불필요.

> 이 태스크는 다음 Task 3에서 engine·테스트와 함께 검증되므로 단독 커밋은 Task 3 끝에서 함께 한다.

---

## Task 3: engine — in-flight 가드 + attempts 증가 + mark_processed

**Files:**
- Modify: `backend/src/ggotaiorder/pipeline/engine.py`
- Modify: `backend/tests/test_pipeline_engine.py`
- Modify: `backend/tests/test_phase4_e2e.py`

- [ ] **Step 1: 기존 FakeRepo(test_pipeline_engine.py)를 신규 계약으로 갱신**

`tests/test_pipeline_engine.py`의 `FakeRepo.set_is_order` 메서드(18~19행)를 삭제하고 아래로 교체:

```python
    def mark_processed(self, call_history_id: int, value: str) -> None:
        self.calls.append(("mark_processed", call_history_id, value))

    def increment_attempts(self, call_history_id: int) -> None:
        self.calls.append(("increment_attempts", call_history_id))
```

그리고 기존 단언에서 `set_is_order` → `mark_processed` 로 치환:
- 61행 `assert ("set_is_order", 1, "Y") in repo.calls` → `assert ("mark_processed", 1, "Y") in repo.calls`
- 96행 `assert ("set_is_order", 1, "Y") not in repo.calls` → `assert ("mark_processed", 1, "Y") not in repo.calls`
- 113행 `assert kinds.index("insert") < kinds.index("set_is_order")` → `... kinds.index("mark_processed")`
- 124행 `assert ("set_is_order", 1, "N") in repo.calls` → `assert ("mark_processed", 1, "N") in repo.calls`

- [ ] **Step 2: 신규 실패 테스트 작성 (in-flight 가드 + attempts)**

`tests/test_pipeline_engine.py` 상단에 `import asyncio` 추가하고, 파일 끝에 추가:

```python
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

    gets = [c for c in repo.calls if c[0] == "get"]
    assert len(gets) == 1
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_engine.py -v`
Expected: FAIL — `mark_processed`/`increment_attempts` 미구현, in-flight 가드 없어 `get` 2회.

- [ ] **Step 4: engine.py 구현**

`engine.py`에서 `import asyncio` 가 이미 있는지 확인(있음). 상단 상수 블록에 추가:

```python
# 영구 실패 행의 무한 재시도 차단 상한 (catch-up 스캔과 공유)
MAX_ATTEMPTS = 5

# 처리 중인 call_history_id (Realtime 콜백과 catch-up 스캔의 중복 처리 방지).
# 오케스트레이터가 단일 asyncio 루프라 add가 첫 await 이전에 일어나 원자적이다.
_in_flight: set[int] = set()
```

`process()` 함수를 아래로 **전체 교체**(기존 본문은 `_process_inner`로 이동):

```python
async def process(call_history_id: int, repo: OrderRepository | None = None) -> None:
    """단일 수집 건을 정형화 처리한다.

    같은 id가 이미 처리 중이면 즉시 스킵한다(중복 주문 INSERT 방지).
    repo 미지정 시 SupabaseOrderRepository 를 사용한다(테스트는 fake 주입).
    """
    if call_history_id in _in_flight:
        logger.debug("이미 처리 중 — 스킵 id=%s", call_history_id)
        return
    _in_flight.add(call_history_id)
    try:
        await _process_inner(call_history_id, repo or SupabaseOrderRepository())
    finally:
        _in_flight.discard(call_history_id)


async def _process_inner(call_history_id: int, repo: OrderRepository) -> None:
    # 시도 횟수를 먼저 올린다(실패해도 카운트 → MAX_ATTEMPTS 상한이 적용됨).
    await asyncio.to_thread(repo.increment_attempts, call_history_id)

    try:
        row = await asyncio.to_thread(repo.get_call_history, call_history_id)
    except Exception:
        logger.exception("수집 이력 조회 실패 id=%s", call_history_id)
        return

    stt_text = row.stt_text
    if not stt_text:
        if row.audio_file_name and row.audio_file_name != INTRANET_AUDIO_MARKER:
            try:
                stt_text = await asyncio.to_thread(transcribe, row.audio_file_name)
                await asyncio.to_thread(repo.update_stt_text, call_history_id, stt_text)
            except Exception:
                logger.exception("STT 처리 실패 — 건너뜀 id=%s", call_history_id)
                return
        else:
            logger.warning("stt_text 없음 — 건너뜀 id=%s", call_history_id)
            return

    try:
        extraction = await asyncio.to_thread(extract_order, stt_text)
    except Exception:
        logger.exception("Gemini 추출 실패 id=%s", call_history_id)
        return

    missing = count_missing(extraction)
    if missing >= _MISSING_THRESHOLD:
        await asyncio.to_thread(repo.mark_processed, call_history_id, "N")
        await asyncio.to_thread(repo.delete_audio, row.audio_file_name)
        logger.info("주문 아님 판별 id=%s (누락 %s개)", call_history_id, missing)
        return

    # order_details INSERT가 성공한 뒤에만 종결('Y')로 마킹한다(부분쓰기 방지).
    try:
        order_id = await asyncio.to_thread(
            repo.insert_order_details, _build_order_payload(row, extraction)
        )
    except Exception:
        logger.exception("order_details 생성 실패 — 미종결 id=%s", call_history_id)
        return

    await asyncio.to_thread(repo.mark_processed, call_history_id, "Y")
    logger.info("order_details 생성 id=%s order_id=%s", call_history_id, order_id)
    await enqueue(order_id)
```

- [ ] **Step 5: 다른 FakeRepo(test_phase4_e2e.py) 갱신**

`tests/test_phase4_e2e.py` 53행의 `set_is_order` 메서드를 찾아 이름을 `mark_processed`로 바꾸고, 같은 클래스에 `increment_attempts`가 없으면 추가:

```python
    def mark_processed(self, call_history_id, value):
        # (기존 set_is_order 본문 유지)
        ...

    def increment_attempts(self, call_history_id):
        pass
```

> 53행 본문을 열어 기존 동작(예: dict 갱신/기록)을 그대로 `mark_processed`로 옮긴다. 메서드 호출처는 engine뿐이므로 이름만 바꾸면 된다.

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_engine.py tests/test_phase4_e2e.py -v`
Expected: PASS (전부).

- [ ] **Step 7: Commit (Task 2 + Task 3 함께)**

```bash
git add backend/src/ggotaiorder/pipeline/repository.py backend/src/ggotaiorder/pipeline/engine.py backend/tests/test_pipeline_engine.py backend/tests/test_phase4_e2e.py
git commit -m "feat(pipeline): in-flight 중복가드 + attempts 카운트 + mark_processed(processed_at 기록)"
```

---

## Task 4: CatchupScanner

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/catchup.py`
- Create: `backend/tests/test_pipeline_catchup.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_pipeline_catchup.py`:

```python
from ggotaiorder.pipeline import catchup, engine


class FakeScanRepo:
    def __init__(self, pending: list[int]):
        self._pending = pending
        self.queried: list[tuple] = []

    def list_pending_call_ids(self, channels, max_attempts):
        self.queried.append((set(channels), max_attempts))
        return list(self._pending)


async def test_scan_once_processes_each_pending(monkeypatch):
    repo = FakeScanRepo([10, 11, 12])
    processed: list[int] = []

    async def fake_process(call_history_id, repo=None):
        processed.append(call_history_id)

    monkeypatch.setattr(catchup, "process", fake_process)

    scanner = catchup.CatchupScanner(repo=repo)
    count = await scanner.scan_once()

    assert processed == [10, 11, 12]
    assert count == 3
    # 채널/상한 계약 확인
    channels, max_attempts = repo.queried[0]
    assert channels == engine._REALTIME_CHANNELS
    assert max_attempts == engine.MAX_ATTEMPTS


async def test_scan_once_empty_returns_zero(monkeypatch):
    repo = FakeScanRepo([])

    async def fake_process(call_history_id, repo=None):
        raise AssertionError("미처리 행이 없으면 process가 호출되면 안 된다")

    monkeypatch.setattr(catchup, "process", fake_process)

    scanner = catchup.CatchupScanner(repo=repo)
    assert await scanner.scan_once() == 0
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_catchup.py -v`
Expected: FAIL — `ggotaiorder.pipeline.catchup` 모듈 없음.

- [ ] **Step 3: catchup.py 구현**

`backend/src/ggotaiorder/pipeline/catchup.py`:

```python
"""부팅 시/주기적 catch-up 스캔.

Realtime 이 놓친(오프라인·절전 동안 INSERT된) 핸드폰/가게음성 미처리 행을
조회해 pipeline.process 로 순차 처리한다. engine 의 in-flight 가드가
Realtime 경로와의 중복 처리를 막는다.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.pipeline.engine import MAX_ATTEMPTS, _REALTIME_CHANNELS, process
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository

logger = logging.getLogger(__name__)


class CatchupScanner:
    """미처리 통화 행을 찾아 순차 처리한다."""

    def __init__(self, repo: OrderRepository | None = None) -> None:
        self._repo = repo or SupabaseOrderRepository()

    async def scan_once(self) -> int:
        """미처리 핸드폰/가게음성 행을 조회해 순차 처리하고 처리 건수를 반환한다.

        순차(await)로 처리해 대량 백로그가 Gemini/STT 레이트리밋을 버스트로
        때리지 않게 한다. 스캔 중 도착한 신규 INSERT 는 Realtime 이 받는다.
        """
        ids = await asyncio.to_thread(
            self._repo.list_pending_call_ids, _REALTIME_CHANNELS, MAX_ATTEMPTS
        )
        if not ids:
            return 0
        logger.info("catch-up 스캔: 미처리 %s건 처리 시작", len(ids))
        for call_history_id in ids:
            await process(call_history_id, repo=self._repo)
        logger.info("catch-up 스캔 완료: %s건", len(ids))
        return len(ids)
```

> `_REALTIME_CHANNELS` 는 engine 모듈 변수다. listener.py 도 같은 이름의 자체 상수를 갖고 있으니, **단일 출처로 engine 쪽을 쓴다**. (listener.py 는 이번 변경 범위 밖 — 그대로 둔다.)

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_catchup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/catchup.py backend/tests/test_pipeline_catchup.py
git commit -m "feat(pipeline): CatchupScanner.scan_once — 미처리 행 순차 처리"
```

---

## Task 5: 오케스트레이터 배선 (부팅 1회 + 30분 주기)

**Files:**
- Modify: `backend/src/ggotaiorder/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_orchestrator.py` 끝에 추가(상단 import는 그대로 사용):

```python
import asyncio

import ggotaiorder.orchestrator as orch_mod


def test_catchup_interval_constant_is_30_min():
    assert orch_mod._CATCHUP_INTERVAL_MIN == 30


async def test_scheduled_catchup_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 0

    monkeypatch.setattr(orch._scanner, "scan_once", fake_scan)

    await orch._scheduled_catchup()

    assert called["scan"] is False


async def test_scheduled_catchup_runs_when_active(monkeypatch):
    orch = Orchestrator()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 2

    monkeypatch.setattr(orch._scanner, "scan_once", fake_scan)

    await orch._scheduled_catchup()

    assert called["scan"] is True
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `_CATCHUP_INTERVAL_MIN`/`_scanner`/`_scheduled_catchup` 없음.

- [ ] **Step 3: orchestrator.py 구현**

`orchestrator.py` 상단 import에 추가:

```python
from ggotaiorder.pipeline.catchup import CatchupScanner
```

상수 블록(`_DEFAULT_INTRANET_INTERVAL_MIN` 근처)에 추가:

```python
# catch-up 스캔 주기(분). 부팅 1회 후 이 간격으로 미처리분을 따라잡는다.
_CATCHUP_INTERVAL_MIN = 30
```

`__init__`의 `self._listener = RealtimeListener()` 바로 아래에 추가:

```python
        self._scanner = CatchupScanner()
```

`_scheduled_poll` 메서드 바로 아래에 새 메서드 추가:

```python
    async def _scheduled_catchup(self) -> None:
        """일시정지가 아니면 catch-up 스캔을 1회 수행한다(누락분 따라잡기)."""
        if self._paused:
            logger.debug("paused 상태 — catch-up 스킵")
            return
        try:
            await self._scanner.scan_once()
        except Exception:
            logger.exception("catch-up 스캔 실패(다음 주기에 재시도)")
```

`start()`에서 `await self._listener.start()` **바로 다음 줄**에 부팅 1회 스캔 추가:

```python
        # 부팅 직후: 구독 이후 1회 스캔(오프라인/절전 누락분 따라잡기).
        # 구독 후에 실행하므로 스캔 중 도착분은 Realtime이 받고 in-flight로 중복 방지.
        await self._scheduled_catchup()
```

그리고 인트라넷 잡 등록 블록(`self._scheduler.add_job(... id="intranet_poll")`) **다음에** catch-up 주기 잡 추가:

```python
        self._scheduler.add_job(
            self._scheduled_catchup,
            "interval",
            minutes=_CATCHUP_INTERVAL_MIN,
            id="catchup_scan",
            max_instances=1,
        )
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_orchestrator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat(orchestrator): 부팅 1회 + 30분 주기 catch-up 스캔 배선"
```

---

## Task 6: 전체 회귀 + 라이브 배포

**Files:** 없음(검증/배포 단계)

- [ ] **Step 1: 전체 백엔드 테스트 회귀**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 전체 PASS, 회귀 0. (라이브를 때리는 `*_live.py`는 키/네트워크 필요 — 평소처럼 스킵/실패면 별도 확인.)

- [ ] **Step 2: 라이브 마이그레이션 적용**

`docs/migrations/2026-06-14-catchup-scan.sql` 를 라이브 Supabase에 적용한다. Supabase MCP는 Unauthorized이므로 둘 중 하나:
- (A) Management API(PAT)로 SQL 실행 — PAT는 사장님이 채팅으로 제공.
- (B) 사장님이 Supabase 대시보드 SQL 편집기에 붙여넣어 실행.

적용 후 확인 쿼리(컬럼 존재):

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name='server_call_history'
  AND column_name IN ('processed_at','process_attempts');
```

Expected: 2행 반환.

- [ ] **Step 3: 실행 중인 백엔드 재기동**

작업 스케줄러 인스턴스를 새 코드로 재시작:

```powershell
Stop-ScheduledTask -TaskName "ggotAIorder"; Start-ScheduledTask -TaskName "ggotAIorder"
```

(또는 기존 pythonw 종료 후 재기동.) 로그 `backend/logs/` 에서 `오케스트레이터 시작` + catch-up 스캔 로그 확인.

- [ ] **Step 4: 라이브 스모크 (합성 미처리 행)**

`processed_at IS NULL`·`channel_order='핸드폰'`·완전한 `stt_text` 를 가진 합성 행 1건을 service-role로 INSERT → 30분 기다리지 말고 수동으로 `CatchupScanner().scan_once()` 1회 실행(또는 재기동의 부팅 스캔 활용) → `order_details` 생성·`processed_at` 채워짐 확인 → 테스트 행(order_details→server_call_history 순) 삭제로 흔적 0.

> 스모크 스크립트는 일회성이며, 한글 출력 시 `PYTHONIOENCODING=utf-8` 설정 필수. 실행 후 스크립트 삭제.

- [ ] **Step 5: 최종 검증 후 머지 준비**

`superpowers:requesting-code-review` 로 리뷰 → `superpowers:finishing-a-development-branch` 로 머지 옵션 진행.

---

## Self-Review 결과 (작성자 점검)

- **Spec coverage:** §3 데이터모델→T1, §4 식별쿼리→T2(list_pending), §5 파이프라인(가드/attempts/mark_processed)→T3, §6 스캐너→T4, §7 오케스트레이터→T5, §10 테스트→각 태스크, §11 배포→T6. 누락 없음.
- **Placeholder scan:** 코드 단계는 전부 실제 코드 포함. T3 Step5는 기존 파일 본문 의존부가 있어 "본문 유지" 지시 명시.
- **Type consistency:** `mark_processed(id, value)`, `increment_attempts(id)`, `list_pending_call_ids(channels, max_attempts)`, `_REALTIME_CHANNELS`, `MAX_ATTEMPTS`, `_scheduled_catchup`, `_CATCHUP_INTERVAL_MIN`, `_scanner` 명칭 전 태스크 일치.
