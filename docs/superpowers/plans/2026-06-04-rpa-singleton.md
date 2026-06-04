# RPA 싱글턴 엔진 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `rpa.enqueue` 스텁을 싱글턴 순차 오케스트레이션 실구현으로 — 주문 조회 → 관리 프로그램 구동 감지 → (추상화된) GUI 입력 또는 백업(.xlsx+.txt) 생성 → `rpa_status` 마킹 → 주문별 알림. 실제 GUI 입력은 골격.

**Architecture:** `enqueue`는 모듈 수준 `asyncio.Lock` 하에 순차 오케스트레이션만 담당. GUI는 `ProgramAutomator`(Protocol, 실제 `WindowsProgramAutomator` 골격), DB는 `RpaRepository`(Protocol, `SupabaseRpaRepository`). 백업은 결정적이라 실구현. 블로킹은 `asyncio.to_thread`, 전체 try/except로 호출자 보호. 오프라인은 fake repo/automator/backup + spy로 결정적 테스트.

**Tech Stack:** Python 3.13, supabase-py, openpyxl 3.1.5(설치됨), pytest, pytest-asyncio(asyncio_mode=auto).

설계서: `docs/superpowers/specs/2026-06-04-rpa-singleton-design.md`
브랜치: `feature/rpa-singleton` (이미 생성됨, master 기준)

**검증 명령 전제:** 모든 pytest/python은 `backend\.venv\Scripts\python.exe`로, 저장소 루트 `C:\ggotAI\ggotAIorder`에서 실행.

---

## File Structure

| 파일 | 책임 | 유형 |
| --- | --- | --- |
| `backend/src/ggotaiorder/rpa/models.py` | `RpaOrder` 데이터 모델 | 신규 |
| `backend/src/ggotaiorder/rpa/automator.py` | `ProgramAutomator`(Protocol) + `WindowsProgramAutomator`(골격) | 신규 |
| `backend/src/ggotaiorder/rpa/repository.py` | `RpaRepository`(Protocol) + `SupabaseRpaRepository` | 신규 |
| `backend/src/ggotaiorder/rpa/backup.py` | `BackupWriter`(.xlsx + .txt 영수증) | 신규 |
| `backend/src/ggotaiorder/config.py` | `rpa_backup_dir` 선택 필드 추가 | 수정 |
| `backend/src/ggotaiorder/rpa/singleton_macro.py` | `enqueue` 오케스트레이션 + `_rpa_lock` (스텁 대체) | 수정 |
| `backend/tests/test_config.py` | rpa_backup_dir 테스트 추가 | 수정 |
| `backend/tests/test_rpa_backup.py` | BackupWriter 오프라인 테스트 | 신규 |
| `backend/tests/test_rpa_singleton.py` | enqueue 오프라인 결정적 테스트 | 신규 |
| `backend/README.md` | RPA 라이브 구동 체크리스트 | 수정 |

---

### Task 1: rpa/models.py — 데이터 모델

**Files:**
- Create: `backend/src/ggotaiorder/rpa/models.py`

- [ ] **Step 1: 구현 작성** — `backend/src/ggotaiorder/rpa/models.py`:
```python
"""RPA 엔진 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RpaOrder:
    """RPA가 관리 프로그램에 입력/백업할 단일 주문.

    order_details 행 + server_call_history.channel_order(channel) 조인 결과.
    """

    order_detail_id: int
    shop_key: int
    shop_name: str
    channel: str                        # 전화/쇼핑몰/인터라넷 (server_call_history.channel_order)
    customer_name: str
    customer_phone_number: str
    product_name: str
    quantity: int
    price: int
    delivery_at: str | None
    delivery_place: str | None
    receiver_name: str | None
    receiver_phone_number: str | None
    ribbon_sender: str | None
    ribbon_congratulations: str | None
    card_message: str | None
```

- [ ] **Step 2: import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.rpa.models import RpaOrder; o=RpaOrder(1,2,'꽃집','전화','홍','010','장미',1,1000,None,None,None,None,None,None,None); print('ok', o.product_name)"
```
Expected: `ok 장미`.

- [ ] **Step 3: Commit**
```bash
git add backend/src/ggotaiorder/rpa/models.py
git commit -m "feat: rpa 데이터 모델(RpaOrder) 추가"
```

---

### Task 2: rpa/automator.py — GUI 자동화 추상화 (골격)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/automator.py`

`WindowsProgramAutomator`는 라이브 영역(실 프로그램 필요) — 단위테스트 안 함. enqueue 테스트는 fake automator로.

- [ ] **Step 1: 구현 작성** — `backend/src/ggotaiorder/rpa/automator.py`:
```python
"""관리 프로그램 GUI 자동화 추상화.

ProgramAutomator(Protocol)로 계약을 고정하고, 실제 Windows 구현은 골격이다.
대상 꽃집 관리 프로그램의 창 제목·입력 폼 Tab 순서를 확보해야 완성할 수 있다(라이브 체크리스트).
"""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class ProgramAutomator(Protocol):
    """꽃집 관리 프로그램에 주문을 입력하는 계약."""

    def is_program_running(self) -> bool: ...

    def input_order(self, order: RpaOrder) -> None: ...


class WindowsProgramAutomator:
    """Windows 관리 프로그램 GUI 자동화 (골격).

    라이브 전엔 is_program_running()이 항상 False를 반환해 안전하게 백업 경로로 흐른다.
    """

    def is_program_running(self) -> bool:
        # TODO(라이브): pygetwindow로 관리 프로그램 창 탐색. 실 프로그램 창 제목 확보 후.
        logger.debug("[STUB] WindowsProgramAutomator.is_program_running -> False")
        return False

    def input_order(self, order: RpaOrder) -> None:
        # TODO(라이브): pyperclip 클립보드 + Tab 키 시퀀스 입력. 실 프로그램 UI 확보 후.
        logger.warning("[STUB] WindowsProgramAutomator.input_order — 실 프로그램 미확보")
        raise NotImplementedError(
            "관리 프로그램 GUI 입력은 대상 프로그램 확보 후 구현됩니다."
        )
```

- [ ] **Step 2: import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.rpa.automator import ProgramAutomator, WindowsProgramAutomator; print('ok', WindowsProgramAutomator().is_program_running())"
```
Expected: `ok False`.

- [ ] **Step 3: Commit**
```bash
git add backend/src/ggotaiorder/rpa/automator.py
git commit -m "feat: rpa GUI 자동화 추상화(ProgramAutomator+Windows 골격) 추가"
```

---

### Task 3: rpa/repository.py — DB 추상화

**Files:**
- Create: `backend/src/ggotaiorder/rpa/repository.py`

`SupabaseRpaRepository`는 실 DB(통합) — 단위테스트 안 함. enqueue 테스트는 fake repo로.

- [ ] **Step 1: 구현 작성** — `backend/src/ggotaiorder/rpa/repository.py`:
```python
"""RPA 엔진 DB 접근: 주문 조회(채널 조인)·상태 마킹."""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class RpaRepository(Protocol):
    """RPA 엔진이 필요로 하는 DB 연산 계약."""

    def get_order(self, order_detail_id: int) -> RpaOrder | None: ...

    def set_rpa_status(self, order_detail_id: int, status: str) -> None: ...


class SupabaseRpaRepository:
    """Supabase 기반 RpaRepository 구현."""

    def get_order(self, order_detail_id: int) -> RpaOrder | None:
        client = get_client()
        res = (
            client.table("order_details")
            .select("*")
            .eq("id", order_detail_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]

        channel = ""
        ch = (
            client.table("server_call_history")
            .select("channel_order")
            .eq("id", row["call_history_id"])
            .limit(1)
            .execute()
        )
        if ch.data:
            channel = ch.data[0].get("channel_order") or ""

        return RpaOrder(
            order_detail_id=row["id"],
            shop_key=row["shop_key"],
            shop_name=row["shop_name"],
            channel=channel,
            customer_name=row.get("customer_name") or "",
            customer_phone_number=row.get("customer_phone_number") or "",
            product_name=row.get("product_name") or "",
            quantity=row.get("quantity") if row.get("quantity") is not None else 1,
            price=row.get("price") if row.get("price") is not None else 0,
            delivery_at=row.get("delivery_at"),
            delivery_place=row.get("delivery_place"),
            receiver_name=row.get("receiver_name"),
            receiver_phone_number=row.get("receiver_phone_number"),
            ribbon_sender=row.get("ribbon_sender"),
            ribbon_congratulations=row.get("ribbon_congratulations"),
            card_message=row.get("card_message"),
        )

    def set_rpa_status(self, order_detail_id: int, status: str) -> None:
        (
            get_client()
            .table("order_details")
            .update({"rpa_status": status})
            .eq("id", order_detail_id)
            .execute()
        )
```

- [ ] **Step 2: import 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.rpa.repository import RpaRepository, SupabaseRpaRepository; print('ok')"
```
Expected: `ok` (네트워크 호출 없음).

- [ ] **Step 3: Commit**
```bash
git add backend/src/ggotaiorder/rpa/repository.py
git commit -m "feat: rpa DB 추상화(RpaRepository) 추가"
```

---

### Task 4: config.py — rpa_backup_dir 선택 필드 (TDD)

**Files:**
- Modify: `backend/src/ggotaiorder/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: 실패 테스트 추가** — `backend/tests/test_config.py` 끝에 추가:
```python
from pathlib import Path


def test_rpa_backup_dir_default():
    cfg = load_config(env=VALID)
    assert isinstance(cfg.rpa_backup_dir, Path)
    assert cfg.rpa_backup_dir.name == "backups"


def test_rpa_backup_dir_override():
    cfg = load_config(env=dict(VALID, RPA_BACKUP_DIR="/tmp/custom-backups"))
    assert str(cfg.rpa_backup_dir).endswith("custom-backups")
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: FAIL — `Config`에 `rpa_backup_dir` 속성 없음(AttributeError) / Config 생성 인자 불일치.

- [ ] **Step 3: config.py 수정** — `Config` 데이터클래스에 필드 추가(`gemini_api_key` 아래):
```python
@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    aes_encryption_key: str
    gemini_api_key: str
    rpa_backup_dir: Path
```

그리고 `load_config`의 `return Config(...)` 직전에 백업 경로 계산 추가, return에 인자 추가:
```python
    backup_dir = env.get("RPA_BACKUP_DIR")
    rpa_backup_dir = (
        Path(backup_dir) if backup_dir
        else Path(__file__).resolve().parents[2] / "backups"
    )

    return Config(
        supabase_url=env["SUPABASE_URL"],
        supabase_anon_key=env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=env["SUPABASE_SERVICE_ROLE_KEY"],
        aes_encryption_key=aes_key,
        gemini_api_key=env["GEMINI_API_KEY"],
        rpa_backup_dir=rpa_backup_dir,
    )
```
(`from pathlib import Path`는 이미 import됨. `RPA_BACKUP_DIR`은 `_REQUIRED_KEYS`에 넣지 않음 — 선택값.)

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: 기존 5 + 신규 2 = 7 passed.

- [ ] **Step 5: Commit**
```bash
git add backend/src/ggotaiorder/config.py backend/tests/test_config.py
git commit -m "feat: config rpa_backup_dir 선택 환경변수 추가"
```

---

### Task 5: rpa/backup.py — BackupWriter (TDD)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/backup.py`
- Test: `backend/tests/test_rpa_backup.py`

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/test_rpa_backup.py`:
```python
from openpyxl import load_workbook

from ggotaiorder.rpa.backup import BackupWriter
from ggotaiorder.rpa.models import RpaOrder


def _order(**kw):
    base = dict(
        order_detail_id=7, shop_key=3, shop_name="꽃집", channel="전화",
        customer_name="홍길동", customer_phone_number="010-0000-0000",
        product_name="장미다발", quantity=2, price=30000,
        delivery_at="2026-06-04 10:00", delivery_place="서울시 강남구",
        receiver_name="김철수", receiver_phone_number="010-1111-1111",
        ribbon_sender="보내는분", ribbon_congratulations="축 결혼",
        card_message="행복하세요",
    )
    base.update(kw)
    return RpaOrder(**base)


def test_backup_writes_xlsx_and_txt(tmp_path):
    writer = BackupWriter(tmp_path / "backups")
    xlsx_path, txt_path = writer.write(_order())

    assert xlsx_path.exists()
    assert txt_path.exists()

    ws = load_workbook(xlsx_path).active
    data_row = [c.value for c in ws[2]]      # 1행=헤더, 2행=값
    assert "장미다발" in data_row
    assert ws.cell(row=2, column=8).value == 2   # 8열=수량

    txt = txt_path.read_text(encoding="utf-8")
    assert "장미다발" in txt
    assert "김철수" in txt


def test_backup_creates_missing_dir(tmp_path):
    target = tmp_path / "nested" / "backups"
    writer = BackupWriter(target)
    writer.write(_order())
    assert target.exists()
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_rpa_backup.py -v`
Expected: FAIL — `ggotaiorder.rpa.backup` 모듈/`BackupWriter` 없음(ModuleNotFoundError).

- [ ] **Step 3: 구현 작성** — `backend/src/ggotaiorder/rpa/backup.py`:
```python
"""관리 프로그램 미구동/입력 실패 시 비상 백업 생성.

PRD 6-5: .xlsx(데이터) + .txt(사람이 읽는 영수증)를 백업 폴더에 생성한다.
사장님이 수동으로 관리 프로그램에 입력할 수 있게 한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

_HEADERS = [
    "주문ID", "꽃집KEY", "꽃집명", "채널", "고객명", "고객전화", "상품명",
    "수량", "가격", "배송일시", "배송지", "받는분", "받는분전화",
    "리본_보내는분", "리본_경조사", "카드메시지",
]


def _row(o: RpaOrder) -> list:
    return [
        o.order_detail_id, o.shop_key, o.shop_name, o.channel,
        o.customer_name, o.customer_phone_number, o.product_name,
        o.quantity, o.price, o.delivery_at, o.delivery_place,
        o.receiver_name, o.receiver_phone_number,
        o.ribbon_sender, o.ribbon_congratulations, o.card_message,
    ]


def _receipt_text(o: RpaOrder) -> str:
    return "\n".join([
        "===== ggotAI 주문 영수증 (수동 입력 백업) =====",
        f"주문ID: {o.order_detail_id}",
        f"꽃집: {o.shop_name} (key={o.shop_key})",
        f"채널: {o.channel}",
        f"상품: {o.product_name} x {o.quantity} ({o.price}원)",
        f"배송일시: {o.delivery_at}",
        f"배송지: {o.delivery_place}",
        f"받는분: {o.receiver_name} / {o.receiver_phone_number}",
        f"고객: {o.customer_name} / {o.customer_phone_number}",
        f"리본(보내는분): {o.ribbon_sender}",
        f"리본(경조사): {o.ribbon_congratulations}",
        f"카드메시지: {o.card_message}",
        "==========================================",
    ])


class BackupWriter:
    """주문 1건을 .xlsx + .txt 영수증으로 백업 폴더에 기록한다."""

    def __init__(self, backup_dir: Path) -> None:
        self._dir = Path(backup_dir)

    def write(self, order: RpaOrder) -> tuple[Path, Path]:
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{order.shop_key}_{order.order_detail_id}_{stamp}"
        xlsx_path = self._dir / f"{base}.xlsx"
        txt_path = self._dir / f"{base}.txt"

        wb = Workbook()
        ws = wb.active
        ws.title = "주문"
        ws.append(_HEADERS)
        ws.append(_row(order))
        wb.save(xlsx_path)

        txt_path.write_text(_receipt_text(order), encoding="utf-8")

        logger.info("RPA 백업 생성 id=%s -> %s", order.order_detail_id, base)
        return xlsx_path, txt_path
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_rpa_backup.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**
```bash
git add backend/src/ggotaiorder/rpa/backup.py backend/tests/test_rpa_backup.py
git commit -m "feat: rpa 비상 백업(.xlsx+영수증) BackupWriter 추가"
```

---

### Task 6: rpa/singleton_macro.py — enqueue 오케스트레이션 (TDD)

**Files:**
- Modify: `backend/src/ggotaiorder/rpa/singleton_macro.py` (전체 교체)
- Test: `backend/tests/test_rpa_singleton.py`

현재 singleton_macro.py는 `_rpa_lock`과 stub `enqueue(order_detail_id)`를 가진다. `enqueue` 시그니처는 하위호환(추가 인자 모두 기본값)으로 교체한다 — pipeline.engine/scraper.crawler가 `await enqueue(order_id)`로 호출하므로.

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/test_rpa_singleton.py`:
```python
import asyncio

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.singleton_macro import enqueue


def _order(order_detail_id=7):
    return RpaOrder(
        order_detail_id=order_detail_id, shop_key=3, shop_name="꽃집", channel="전화",
        customer_name="홍", customer_phone_number="010", product_name="장미",
        quantity=1, price=1000, delivery_at=None, delivery_place=None,
        receiver_name=None, receiver_phone_number=None, ribbon_sender=None,
        ribbon_congratulations=None, card_message=None,
    )


class FakeRepo:
    def __init__(self, order):
        self._order = order
        self.statuses = []

    def get_order(self, order_detail_id):
        return self._order

    def set_rpa_status(self, order_detail_id, status):
        self.statuses.append((order_detail_id, status))


class FakeAutomator:
    def __init__(self, running, raises=False):
        self._running = running
        self._raises = raises
        self.inputs = []

    def is_program_running(self):
        return self._running

    def input_order(self, order):
        if self._raises:
            raise RuntimeError("input failed")
        self.inputs.append(order.order_detail_id)


class FakeBackup:
    def __init__(self):
        self.written = []

    def write(self, order):
        self.written.append(order.order_detail_id)
        return ("x.xlsx", "x.txt")


def _spy_notify():
    calls = []

    async def notify(order, success):
        calls.append((order.order_detail_id, success))

    return calls, notify


async def test_program_running_input_success():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert autom.inputs == [7]
    assert backup.written == []
    assert repo.statuses == [(7, "success")]
    assert calls == [(7, True)]


async def test_program_running_input_fails_backs_up():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=True, raises=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert backup.written == [7]
    assert repo.statuses == [(7, "fail")]
    assert calls == [(7, False)]


async def test_program_not_running_backs_up():
    repo = FakeRepo(_order())
    autom = FakeAutomator(running=False)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(7, repo=repo, automator=autom, backup=backup, notify=notify)

    assert autom.inputs == []
    assert backup.written == [7]
    assert repo.statuses == [(7, "fail")]
    assert calls == [(7, False)]


async def test_missing_order_skips():
    repo = FakeRepo(None)
    autom = FakeAutomator(running=True)
    backup = FakeBackup()
    calls, notify = _spy_notify()

    await enqueue(999, repo=repo, automator=autom, backup=backup, notify=notify)

    assert repo.statuses == []
    assert backup.written == []
    assert calls == []


async def test_singleton_lock_serializes():
    import time

    active = {"count": 0, "max": 0}

    class SlowAutomator:
        def is_program_running(self):
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            time.sleep(0.02)
            active["count"] -= 1
            return False

        def input_order(self, order):
            pass

    autom = SlowAutomator()
    backup = FakeBackup()
    _, notify = _spy_notify()

    await asyncio.gather(
        enqueue(1, repo=FakeRepo(_order(1)), automator=autom, backup=backup, notify=notify),
        enqueue(2, repo=FakeRepo(_order(2)), automator=autom, backup=backup, notify=notify),
    )

    assert active["max"] == 1   # 락으로 동시 실행 0 → 최대 동시 1
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_rpa_singleton.py -v`
Expected: FAIL — 현재 stub `enqueue`가 `repo/automator/backup/notify` 인자를 받지 않음(TypeError).

- [ ] **Step 3: singleton_macro.py 전체 교체** — `backend/src/ggotaiorder/rpa/singleton_macro.py`:
```python
"""싱글턴 순차 RPA 제어.

PRD 6-5/8-4: asyncio.Lock()으로 단 하나의 RPA만 순차 실행. 관리 프로그램 창을
찾으면 GUI 입력, 못 찾으면 엑셀(.xlsx)+텍스트 영수증 백업을 생성한다. 완료 후
rpa_status를 'success'/'fail'로 마킹하고 주문별 알림을 발송한다. 실제 GUI 입력은
ProgramAutomator(Protocol) 뒤로 추상화한다.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.config import load_config
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.rpa.automator import ProgramAutomator, WindowsProgramAutomator
from ggotaiorder.rpa.backup import BackupWriter
from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.repository import RpaRepository, SupabaseRpaRepository

logger = logging.getLogger(__name__)

# 다중 채널 충돌 방지용 싱글턴 락 (PRD 8-4)
_rpa_lock = asyncio.Lock()


async def _default_notify(order: RpaOrder, success: bool) -> None:
    """기본 알림: notifier로 주문별(count=1) 결과 발송."""
    await notifier_send(order.shop_key, channel=order.channel, count=1, success=success)


async def enqueue(
    order_detail_id: int,
    *,
    repo: RpaRepository | None = None,
    automator: ProgramAutomator | None = None,
    backup: BackupWriter | None = None,
    notify=None,
) -> None:
    """order_details 1건을 전산 프로그램에 입력한다 (락 순차).

    구동 중이면 GUI 입력 → success, 입력 실패/미구동이면 백업 → fail.
    완료 후 rpa_status 마킹 + 주문별 알림. 호출자 보호를 위해 전체를 try/except.
    """
    repo = repo or SupabaseRpaRepository()
    automator = automator or WindowsProgramAutomator()
    backup = backup or BackupWriter(load_config().rpa_backup_dir)
    notify = notify or _default_notify

    try:
        async with _rpa_lock:
            order = await asyncio.to_thread(repo.get_order, order_detail_id)
            if order is None:
                logger.warning("RPA 대상 주문 없음 id=%s", order_detail_id)
                return

            success = False
            if await asyncio.to_thread(automator.is_program_running):
                try:
                    await asyncio.to_thread(automator.input_order, order)
                    success = True
                except Exception:
                    logger.exception("관리 프로그램 입력 실패 id=%s", order_detail_id)
                    await asyncio.to_thread(backup.write, order)
            else:
                logger.info("관리 프로그램 미구동 — 백업 생성 id=%s", order_detail_id)
                await asyncio.to_thread(backup.write, order)

            status = "success" if success else "fail"
            await asyncio.to_thread(repo.set_rpa_status, order_detail_id, status)
            await notify(order, success)
    except Exception:
        logger.exception("RPA enqueue 처리 실패 id=%s", order_detail_id)
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_rpa_singleton.py -v`
Expected: 5 passed.

- [ ] **Step 5: 호출자/스모크 import 회귀 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "import ggotaiorder.pipeline.engine, ggotaiorder.scraper.crawler, ggotaiorder.rpa.singleton_macro; from ggotaiorder.rpa.singleton_macro import enqueue; print('ok')"
```
Expected: `ok`. (engine/crawler가 `await enqueue(order_id)`로 호출 — 추가 인자 모두 기본값이라 호환.)

- [ ] **Step 6: Commit**
```bash
git add backend/src/ggotaiorder/rpa/singleton_macro.py backend/tests/test_rpa_singleton.py
git commit -m "feat: rpa enqueue 싱글턴 오케스트레이션 실구현(구동감지·입력/백업·status·알림)"
```

---

### Task 7: 전체 검증 + README 체크리스트

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: 전체 스위트 실행** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: 모두 pass + 3 skipped(기존 라이브). 신규: config 2 + backup 2 + singleton 5 = 9 추가. 대략 76 passed, 3 skipped.

- [ ] **Step 2: README에 RPA 라이브 체크리스트 추가** — `backend/README.md`의 `## 구조` 섹션 바로 앞에 삽입:
```markdown
## RPA(싱글턴 입력 엔진) 라이브 구동 체크리스트

enqueue 오케스트레이션·백업은 구현·오프라인 테스트되었으나, 실제 자동 입력에는 다음이 필요합니다:

1. 대상 꽃집 관리 프로그램 창 제목·입력 폼 필드 Tab 이동 순서 확보.
2. `WindowsProgramAutomator.is_program_running` 창 탐색(pygetwindow) 구현.
3. `WindowsProgramAutomator.input_order` 클립보드(pyperclip)+키 시퀀스 입력 구현.
4. (선택) `.env`에 `RPA_BACKUP_DIR` 설정 — 기본값은 `backend/backups`.
5. enqueue 실행 → 구동 시 자동 입력·`rpa_status='success'`·성공 알림 / 미구동·입력실패 시 백업(.xlsx+.txt)·`'fail'`·경고 알림 확인.

```

- [ ] **Step 3: Commit**
```bash
git add backend/README.md
git commit -m "docs: rpa 라이브 구동 체크리스트 README 추가"
```

---

## Self-Review 결과

- **Spec 커버리지**: models(Task1) / ProgramAutomator 추상화·Windows 골격(Task2) / RpaRepository·채널 조인·status 마킹(Task3) / config rpa_backup_dir(Task4) / BackupWriter .xlsx+영수증 실구현(Task5) / enqueue 싱글턴 락·구동감지·입력/백업 분기·success·fail·주문별 알림·방어적 try/except(Task6) / 전체검증·README 체크리스트(Task7) — 설계서 절 모두 매핑.
- **Placeholder 스캔**: Windows automator의 TODO는 의도된 라이브 표식(골격 NotImplementedError/False). 그 외 placeholder 없음. 모든 코드 스텝에 완전한 코드 포함.
- **타입 일관성**: `RpaOrder(order_detail_id, shop_key, shop_name, channel, customer_name, customer_phone_number, product_name, quantity, price, delivery_at, delivery_place, receiver_name, receiver_phone_number, ribbon_sender, ribbon_congratulations, card_message)` — Task1 정의가 Task3 매핑/Task5 `_row`·`_receipt_text`/Task6 테스트 fixture와 인자 순서·이름 일치. `ProgramAutomator.is_program_running()->bool`/`input_order(order)`, `RpaRepository.get_order(id)->RpaOrder|None`/`set_rpa_status(id, status)`, `BackupWriter(backup_dir).write(order)->tuple[Path,Path]`, `enqueue(order_detail_id, *, repo, automator, backup, notify)`, `notify(order, success)`, `notifier_send(shop_key, channel, count, success)`(기존 sms_sender.send 시그니처와 일치) — Task 간·fake·spy 일치.
- **회귀 안전성**: `enqueue` 추가 인자 전부 기본값 → engine/crawler의 `await enqueue(order_id)` 무인자 호출 호환(Task6 Step5). config `rpa_backup_dir`는 선택값·`_REQUIRED_KEYS` 불변 → 기존 config 4개 테스트 회귀 없음. 스모크 MODULES에 rpa.singleton_macro 포함 — enqueue 유지로 import 안전.
- **순환참조 점검**: singleton_macro → notifier.sms_sender / rpa.automator / rpa.backup / rpa.models / rpa.repository / config. backup → rpa.models, automator → rpa.models, repository → core.supabase_client + rpa.models. engine/crawler → rpa.singleton_macro(기존). rpa.* 는 engine/crawler를 import하지 않아 cycle 없음.
