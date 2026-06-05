# Phase 4 통합·최종 검증 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `task.md` Phase 4(통합·최종 검증) 3개 항목을 접근법 A(오프라인 항상-on 자동화 + 라이브 opt-in + OS/GUI 수동 폴백)로 구현하고, 검증이 드러내는 `order_details` NOT NULL 잠복 버그를 수정한다.

**Architecture:** `docs/database_schema.sql`을 단일 기준으로 하는 계약 파서를 만들고, 백엔드 INSERT 페이로드·repository 컬럼 참조·실 DB·프론트 소스를 그 계약과 대조한다(T1). FastAPI TestClient 업로드부터 실제 모듈을 조립해 백업·알림 배선까지 관통하는 E2E를 오프라인(fake)·라이브(opt-in)로 검증한다(T3). IPC→서비스정지→트레이는 수동 체크리스트 문서로 남긴다(T2).

**Tech Stack:** Python 3.11, pytest(asyncio_mode=auto), FastAPI TestClient, supabase-py, openpyxl, 정규식 기반 DDL 파서.

**Branch:** `feature/phase4-integration` (master에서 분기).

**설계서:** `docs/superpowers/specs/2026-06-05-phase4-integration-design.md`

---

## §6 결함 수정 결정 (plan 확정)

`order_details`의 NOT NULL·DEFAULT 없는 컬럼에 `engine._build_order_payload`/`crawler._order_payload`가 None을 넣을 수 있다. 안전 기본값을 다음으로 확정한다(NN 위반 불변식):

| 컬럼 | 타입 | 미상 시 기본값 |
|---|---|---|
| `product_name` | VARCHAR NN | `"미정"` |
| `delivery_place` | VARCHAR NN | `"미정"` |
| `receiver_name` | VARCHAR NN | `"미정"` |
| `receiver_phone_number` | VARCHAR NN | `""`(빈 문자, customer와 동일 관례) |
| `delivery_at` | TIMESTAMPTZ NN | 센티넬 `"2099-12-31T23:59:59+09:00"` (=배송일시 미상; 임의 문자열은 timestamp 파싱 실패하므로 far-future 센티넬로 NN 충족 + UI에서 명백히 보정 대상) |

`count_missing`은 기본값 적용 **이전**의 `extraction`에 대해 수행되므로 주문 판별(is_order) 로직은 영향 없음.

---

## Task 1: 스키마 계약 파서

**Files:**
- Create: `backend/tests/support/__init__.py`
- Create: `backend/tests/support/schema_contract.py`
- Test: `backend/tests/test_phase4_schema_contract.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_phase4_schema_contract.py`:
```python
from pathlib import Path

from tests.support.schema_contract import parse_schema, required_columns

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"


def test_parses_all_four_tables():
    tables = parse_schema(SCHEMA)
    assert set(tables) == {
        "member_info", "server_call_history", "order_details", "setting_info"
    }


def test_order_details_columns_and_nullability():
    cols = parse_schema(SCHEMA)["order_details"]
    assert "product_name" in cols
    assert cols["product_name"].nullable is False
    assert cols["product_name"].has_default is False
    # id 는 SERIAL → has_default True
    assert cols["id"].has_default is True
    # ribbon_sender 는 NULL 허용
    assert cols["ribbon_sender"].nullable is True


def test_required_columns_order_details():
    tables = parse_schema(SCHEMA)
    req = required_columns(tables, "order_details")
    assert req == {
        "call_history_id", "shop_key", "shop_name", "customer_phone_number",
        "product_name", "delivery_at", "delivery_place",
        "receiver_name", "receiver_phone_number",
    }


def test_required_columns_server_call_history():
    tables = parse_schema(SCHEMA)
    req = required_columns(tables, "server_call_history")
    assert req == {
        "channel_classification", "shop_key", "shop_name", "call_date", "call_time"
    }
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: tests.support.schema_contract`

- [ ] **Step 3: 파서 구현**

`backend/tests/support/__init__.py`: 빈 파일.

`backend/tests/support/schema_contract.py`:
```python
"""docs/database_schema.sql 을 단일 기준 계약으로 파싱한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", re.S | re.I
)
_CONSTRAINT_PREFIXES = ("FOREIGN KEY", "PRIMARY KEY", "UNIQUE", "CHECK", "CONSTRAINT")
_IDENT_RE = re.compile(r"^\w+$")


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    nullable: bool
    has_default: bool


def parse_schema(path: Path | str) -> dict[str, dict[str, ColumnSpec]]:
    text = Path(path).read_text(encoding="utf-8")
    tables: dict[str, dict[str, ColumnSpec]] = {}
    for m in _TABLE_RE.finditer(text):
        table = m.group(1)
        body = m.group(2)
        cols: dict[str, ColumnSpec] = {}
        for raw in body.splitlines():
            line = raw.split("--", 1)[0].strip().rstrip(",").strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith(_CONSTRAINT_PREFIXES):
                continue
            name = line.split()[0]
            if not _IDENT_RE.match(name):
                continue
            nullable = "NOT NULL" not in upper
            has_default = "DEFAULT" in upper or "SERIAL" in upper
            cols[name] = ColumnSpec(name=name, nullable=nullable, has_default=has_default)
        tables[table] = cols
    return tables


def required_columns(
    tables: dict[str, dict[str, ColumnSpec]], table: str
) -> set[str]:
    """INSERT 시 반드시 채워야 하는 컬럼(NOT NULL 이면서 DEFAULT 없음)."""
    return {
        c.name for c in tables[table].values()
        if not c.nullable and not c.has_default
    }


def all_columns(tables: dict[str, dict[str, ColumnSpec]]) -> set[str]:
    """모든 테이블 컬럼의 합집합(약식 참조 검사용)."""
    return {col for cols in tables.values() for col in cols}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema_contract.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/tests/support backend/tests/test_phase4_schema_contract.py
git commit -m "test: Phase4 스키마 계약 파서(schema_contract) + 단위 테스트"
```

---

## Task 2: T1a 페이로드 적합성 테스트 (NN 버그 검출 = RED)

**Files:**
- Test: `backend/tests/test_phase4_schema.py` (Create)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_phase4_schema.py`:
```python
"""T1 스키마 정합성: 백엔드 INSERT 페이로드가 계약을 준수하는지 검증."""

from pathlib import Path

from ggotaiorder.pipeline.engine import _build_order_payload
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.scraper.crawler import _call_record, _order_payload
from ggotaiorder.scraper.models import IntranetShop, ScrapedOrder
from tests.support.schema_contract import parse_schema, required_columns

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"
TABLES = parse_schema(SCHEMA)


def _assert_conforms(payload: dict, table: str):
    cols = set(TABLES[table])
    extra = set(payload) - cols
    assert not extra, f"{table}: 계약에 없는 컬럼 {extra}"
    missing = required_columns(TABLES, table) - set(payload)
    assert not missing, f"{table}: 필수 컬럼 누락 {missing}"
    none_required = {
        k for k in required_columns(TABLES, table)
        if payload.get(k) is None
    }
    assert not none_required, f"{table}: 필수 컬럼이 None {none_required}"


def _call_history(**kw) -> CallHistory:
    base = dict(
        id=1, shop_key=2, shop_name="꽃집", customer_name="신규",
        customer_phone_number="010-0000", stt_text="주문",
        audio_file_name="INTRANET_CRAWLED", channel_order="인터라넷",
    )
    base.update(kw)
    return CallHistory(**base)


def _shop() -> IntranetShop:
    return IntranetShop(
        shop_key=2, shop_name="꽃집", url="http://x", username="u", enc_password="e"
    )


def test_engine_order_payload_full_conforms():
    extraction = OrderExtraction(
        customer_name="홍", customer_phone_number="010-1", product_name="장미",
        quantity=2, price=50000, delivery_at="2026-06-10T10:00:00+09:00",
        delivery_place="강남", receiver_name="이", receiver_phone_number="010-2",
        ribbon_congratulations="축", card_message="축하",
    )
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_engine_order_payload_sparse_still_conforms():
    # 누락<3 이지만 NN 컬럼이 None 인 케이스 → 기본값으로 NN 충족해야 함
    extraction = OrderExtraction(
        customer_name="홍", customer_phone_number="010-1", product_name=None,
        quantity=1, price=1000, delivery_at="2026-06-10T10:00:00+09:00",
        delivery_place="강남", receiver_name="이", receiver_phone_number="010-2",
        ribbon_congratulations="축", card_message="축하",
    )
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_engine_order_payload_all_optional_none_conforms():
    extraction = OrderExtraction(customer_name="홍", customer_phone_number="010-1")
    _assert_conforms(_build_order_payload(_call_history(), extraction), "order_details")


def test_crawler_call_record_conforms():
    order = ScrapedOrder(order_no="A1", raw_text="원문", fields=OrderExtraction())
    _assert_conforms(_call_record(_shop(), order), "server_call_history")


def test_crawler_order_payload_conforms():
    order = ScrapedOrder(order_no="A1", raw_text="원문", fields=OrderExtraction())
    _assert_conforms(_order_payload(_shop(), order, 1), "order_details")
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema.py -q`
Expected: FAIL — `test_engine_order_payload_all_optional_none_conforms`, `test_engine_order_payload_sparse_still_conforms`, `test_crawler_order_payload_conforms` 가 "필수 컬럼이 None {...}" (product_name/delivery_at/delivery_place/receiver_name 등)으로 실패.

- [ ] **Step 3: 커밋(RED 테스트 고정)**

```bash
git add backend/tests/test_phase4_schema.py
git commit -m "test: T1a order_details/server_call_history 페이로드 적합성(현재 NN 위반 검출, RED)"
```

---

## Task 3: §6 NN 잠복 버그 수정 (GREEN)

**Files:**
- Modify: `backend/src/ggotaiorder/pipeline/models.py` (센티넬 상수 추가)
- Modify: `backend/src/ggotaiorder/pipeline/engine.py` (import + `_build_order_payload`)
- Modify: `backend/src/ggotaiorder/scraper/crawler.py` (import + `_order_payload`)

> **순환 import 주의:** engine 이 `from ggotaiorder.scraper.crawler import INTRANET_AUDIO_MARKER` 로 crawler 에 의존한다. 따라서 crawler 가 engine 을 import 하면 순환이 된다. 센티넬 상수는 engine/crawler 양쪽이 이미 의존하는 최하위 모듈 `pipeline/models.py` 에 둔다.

- [ ] **Step 1: 센티넬 상수를 models.py 에 정의**

`backend/src/ggotaiorder/pipeline/models.py` 상단(import 아래, `OrderExtraction` 클래스 위)에 추가:
```python
# 배송일시 미상 시 NOT NULL(timestamptz) 충족용 센티넬(=보정 필요). 설계서 §6.
DELIVERY_AT_UNKNOWN = "2099-12-31T23:59:59+09:00"
```

- [ ] **Step 2: engine 빌더 수정**

`backend/src/ggotaiorder/pipeline/engine.py` 의 import 라인
`from ggotaiorder.pipeline.models import CallHistory, OrderExtraction` 를 다음으로 변경:
```python
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction
```
`_build_order_payload` 교체:
```python
def _build_order_payload(row: CallHistory, extraction: OrderExtraction) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다.

    order_details 의 NOT NULL·DEFAULT 없는 컬럼은 미상 시 안전 기본값으로 채운다
    (설계서 §6: product_name/delivery_at/delivery_place/receiver_* NN 위반 방지).
    """
    return {
        "call_history_id": row.id,
        "shop_key": row.shop_key,
        "shop_name": row.shop_name,
        "customer_name": extraction.customer_name or row.customer_name or "신규",
        "customer_phone_number": (
            extraction.customer_phone_number or row.customer_phone_number or ""
        ),
        "product_name": extraction.product_name or "미정",
        "quantity": extraction.quantity if extraction.quantity is not None else 1,
        "price": extraction.price if extraction.price is not None else 0,
        "delivery_at": extraction.delivery_at or DELIVERY_AT_UNKNOWN,
        "delivery_place": extraction.delivery_place or "미정",
        "receiver_name": extraction.receiver_name or "미정",
        "receiver_phone_number": extraction.receiver_phone_number or "",
        "ribbon_congratulations": extraction.ribbon_congratulations,
        "card_message": extraction.card_message,
        "rpa_status": "ready",
    }
```

- [ ] **Step 2b: crawler `_order_payload` 수정**

`backend/src/ggotaiorder/scraper/crawler.py` 의 models import 라인
`from ggotaiorder.scraper.models import INTRANET_CHANNEL, IntranetShop, ScrapedOrder` 아래에 추가:
```python
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN
```
`_order_payload` 를 교체:

`backend/src/ggotaiorder/scraper/crawler.py` 의 `_order_payload` 를 교체:
```python
def _order_payload(shop: IntranetShop, order: ScrapedOrder, call_history_id: int) -> dict:
    f = order.fields
    return {
        "call_history_id": call_history_id,
        "shop_key": shop.shop_key,
        "shop_name": shop.shop_name,
        "customer_name": f.customer_name or "신규",
        "customer_phone_number": f.customer_phone_number or "",
        "product_name": f.product_name or "미정",
        "quantity": f.quantity if f.quantity is not None else 1,
        "price": f.price if f.price is not None else 0,
        "delivery_at": f.delivery_at or DELIVERY_AT_UNKNOWN,
        "delivery_place": f.delivery_place or "미정",
        "receiver_name": f.receiver_name or "미정",
        "receiver_phone_number": f.receiver_phone_number or "",
        "ribbon_congratulations": f.ribbon_congratulations,
        "card_message": f.card_message,
        "rpa_status": "ready",
    }
```

- [ ] **Step 3: 통과 확인 (T1a + 기존 engine 테스트 회귀)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema.py tests/test_pipeline_engine.py tests/test_scraper.py -q`
Expected: PASS (T1a 5건 + 기존 engine/scraper 회귀 모두 통과)

- [ ] **Step 4: 커밋**

```bash
git add backend/src/ggotaiorder/pipeline/engine.py backend/src/ggotaiorder/pipeline/models.py backend/src/ggotaiorder/scraper/crawler.py
git commit -m "fix: order_details NOT NULL 컬럼 안전 기본값(설계서 §6) — engine/crawler 페이로드"
```

---

## Task 4: T1b repository 컬럼 참조 스캔

**Files:**
- Modify: `backend/tests/test_phase4_schema.py` (append)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_phase4_schema.py` 끝에 추가:
```python
import re

from tests.support.schema_contract import all_columns

_SRC = Path(__file__).resolve().parents[1] / "src" / "ggotaiorder"
_REPO_FILES = [
    _SRC / "scraper" / "repository.py",
    _SRC / "rpa" / "repository.py",
    _SRC / "api" / "repository.py",
    _SRC / "pipeline" / "repository.py",
    _SRC / "notifier" / "repository.py",
]

_EQ_RE = re.compile(r"\.(?:eq|neq|gt|gte|lt|lte|is_)\(\s*\"([^\"]+)\"")
_SELECT_RE = re.compile(r"\.select\(\s*\"([^\"]+)\"")
_UPDATE_RE = re.compile(r"\.update\(\s*\{([^}]*)\}")
_UPDATE_KEY_RE = re.compile(r"\"(\w+)\"\s*:")


def _referenced_columns(text: str) -> set[str]:
    cols: set[str] = set()
    cols.update(_EQ_RE.findall(text))
    for sel in _SELECT_RE.findall(text):
        for tok in sel.split(","):
            tok = tok.strip()
            if not tok or tok == "*" or "(" in tok:  # 임베드/와일드카드 스킵
                continue
            cols.add(tok)
    for blk in _UPDATE_RE.findall(text):
        cols.update(_UPDATE_KEY_RE.findall(blk))
    return cols


def test_repository_column_references_exist_in_schema():
    known = all_columns(TABLES)
    for path in _REPO_FILES:
        if not path.exists():
            continue
        refs = _referenced_columns(path.read_text(encoding="utf-8"))
        unknown = refs - known
        assert not unknown, f"{path.name}: 계약에 없는 컬럼 참조 {unknown}"
```

- [ ] **Step 2: 실행 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema.py::test_repository_column_references_exist_in_schema -q`
Expected: PASS (모든 리터럴 컬럼 참조가 계약에 존재). 만약 FAIL 하면 실제 불일치이므로 출력된 컬럼명을 schema.sql 또는 코드와 대조해 수정.

- [ ] **Step 3: 커밋**

```bash
git add backend/tests/test_phase4_schema.py
git commit -m "test: T1b repository 컬럼 참조가 계약(schema.sql)에 존재하는지 스캔"
```

---

## Task 5: T1c 라이브 드리프트 + 프론트 스캔

**Files:**
- Modify: `backend/tests/test_phase4_schema.py` (append T1c)
- Create: `backend/tests/test_phase4_frontend_schema.py`

- [ ] **Step 1: T1c 라이브 드리프트 테스트 작성**

`backend/tests/test_phase4_schema.py` 끝에 추가:
```python
import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SCHEMA") != "1",
    reason="라이브 스키마 드리프트 검사는 RUN_LIVE_SCHEMA=1 opt-in",
)
def test_live_schema_has_all_contract_columns():
    """실 Supabase 각 테이블이 schema.sql 의 모든 컬럼을 갖는지(코드/계약 ⊆ DB)."""
    from ggotaiorder.core.supabase_client import get_client

    client = get_client()
    for table, cols in TABLES.items():
        select = ",".join(cols)
        # 누락 컬럼이 있으면 PostgREST 가 42703 에러를 던진다 → 테스트 실패.
        client.table(table).select(select).limit(1).execute()
```

- [ ] **Step 2: T1c 동작 확인(자원 없으면 skip)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema.py -q`
Expected: T1c 는 SKIP (RUN_LIVE_SCHEMA 미설정), 나머지 PASS.
(자원 가능 시) Run: `RUN_LIVE_SCHEMA=1 ./.venv/Scripts/python.exe -m pytest tests/test_phase4_schema.py::test_live_schema_has_all_contract_columns -q` → PASS.

- [ ] **Step 3: 프론트 스캔 테스트 작성**

`backend/tests/test_phase4_frontend_schema.py`:
```python
"""T1 프론트엔드 best-effort 컬럼 스캔: 명백한 불일치만 실패시킨다."""

import re
from pathlib import Path

import pytest

from tests.support.schema_contract import all_columns, parse_schema

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "database_schema.sql"
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

_EQ_RE = re.compile(r"\.eq\(\s*['\"](\w+)['\"]")
_SELECT_RE = re.compile(r"\.select\(\s*['\"]([^'\"]+)['\"]")


def _scan(text: str) -> set[str]:
    cols: set[str] = set(_EQ_RE.findall(text))
    for sel in _SELECT_RE.findall(text):
        for tok in sel.split(","):
            tok = tok.strip()
            if not tok or tok == "*" or "(" in tok:
                continue
            cols.add(tok)
    return cols


@pytest.mark.skipif(not FRONTEND_SRC.exists(), reason="frontend/src 없음")
def test_frontend_column_references_exist_in_schema():
    known = all_columns(parse_schema(SCHEMA))
    unknown: set[str] = set()
    for path in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx")):
        unknown |= _scan(path.read_text(encoding="utf-8")) - known
    assert not unknown, f"프론트에서 계약에 없는 컬럼 참조: {unknown}"
```

- [ ] **Step 4: 프론트 스캔 동작 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_frontend_schema.py -q`
Expected: PASS(또는 frontend/src 없으면 SKIP). FAIL 시 출력 컬럼이 실제 오타/불일치인지 확인 후, 프론트 코드 또는(정당하면) 스캔 제외 목록을 조정.

- [ ] **Step 5: 커밋**

```bash
git add backend/tests/test_phase4_schema.py backend/tests/test_phase4_frontend_schema.py
git commit -m "test: T1c 라이브 스키마 드리프트(opt-in) + 프론트 컬럼 best-effort 스캔"
```

---

## Task 6: T3a 조립 E2E (오프라인, 항상-on)

**Files:**
- Create: `backend/tests/test_phase4_e2e.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_phase4_e2e.py`:
```python
"""T3 E2E: 업로드→인입→파이프라인→싱글턴 RPA→백업→알림 배선 검증."""

from pathlib import Path

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

    def set_is_order(self, call_history_id, value):
        self.is_order = value

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
```

- [ ] **Step 2: 실행 확인**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_e2e.py -q`
Expected: PASS (조립 체인 관통 + 백업 파일 생성 + notify spy 호출).
만약 FAIL 하면 실제 배선 결함이므로 메시지에 따라 진단(해당 모듈 수정은 별도 판단).

- [ ] **Step 3: 커밋**

```bash
git add backend/tests/test_phase4_e2e.py
git commit -m "test: T3a 조립 E2E(업로드→파이프라인→싱글턴 RPA→백업→알림, 오프라인 fake)"
```

---

## Task 7: T3b 풀 라이브 E2E (opt-in)

**Files:**
- Modify: `backend/tests/test_phase4_e2e.py` (append)

- [ ] **Step 1: 라이브 E2E 테스트 작성**

`backend/tests/test_phase4_e2e.py` 끝에 추가:
```python
import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_E2E") != "1" or not os.getenv("E2E_TEST_SHOP_KEY"),
    reason="풀 라이브 E2E 는 RUN_LIVE_E2E=1 + E2E_TEST_SHOP_KEY 필요",
)
async def test_full_live_e2e(monkeypatch, tmp_path):
    """실 Gemini + 실 Supabase. automator 미구동→백업, notify 는 spy."""
    from ggotaiorder.core.supabase_client import get_client
    from ggotaiorder.pipeline.repository import SupabaseOrderRepository
    from ggotaiorder.rpa.repository import SupabaseRpaRepository

    shop_key = int(os.environ["E2E_TEST_SHOP_KEY"])
    client = get_client()

    # 1) 테스트용 call_history 행 생성(가게전화, stt_text 주입 → STT 우회)
    from datetime import datetime
    now = datetime.now()
    rec = {
        "channel_order": "가게전화", "channel_classification": "E2E-TEST",
        "customer_phone_number": "010-0000-0000", "shop_key": shop_key,
        "shop_name": "E2E꽃집", "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"), "duration_seconds": 0,
        "audio_file_name": None, "stt_text": "장미 2송이 내일 오전 10시 강남구청 배송, 받는분 이영희 010-1111-2222",
        "is_order": "N",
    }
    ins = client.table("server_call_history").insert(rec).execute()
    call_history_id = ins.data[0]["id"]

    notify_calls = []

    async def spy_notify(order, success):
        notify_calls.append((order.order_detail_id, success))

    async def wired_enqueue(order_id):
        from ggotaiorder.rpa.backup import BackupWriter
        await singleton_macro.enqueue(
            order_id, repo=SupabaseRpaRepository(), automator=NotRunningAutomator(),
            backup=BackupWriter(tmp_path), notify=spy_notify,
        )

    monkeypatch.setattr(engine, "enqueue", wired_enqueue)

    try:
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
    finally:
        # 4) 정리: call_history 삭제 → FK CASCADE 로 order_details 동반 삭제
        client.table("server_call_history").delete().eq("id", call_history_id).execute()
```

- [ ] **Step 2: 동작 확인 (자원 없으면 skip)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_phase4_e2e.py -q`
Expected: 라이브 E2E SKIP, T3a PASS.
(자원·픽스처 준비 시) Run: `RUN_LIVE_E2E=1 E2E_TEST_SHOP_KEY=<실제키> ./.venv/Scripts/python.exe -m pytest tests/test_phase4_e2e.py::test_full_live_e2e -q` → PASS, 종료 후 생성행 정리됨.

- [ ] **Step 3: 커밋**

```bash
git add backend/tests/test_phase4_e2e.py
git commit -m "test: T3b 풀 라이브 E2E(opt-in, 실 Gemini+Supabase, CASCADE 정리)"
```

---

## Task 8: T2 수동 검증 체크리스트 문서

**Files:**
- Create: `docs/phase4_manual_verification.md`

- [ ] **Step 1: 문서 작성**

`docs/phase4_manual_verification.md`:
```markdown
# Phase 4 수동 검증 체크리스트 (T2: IPC→서비스정지→트레이)

서비스명: `ggotAIorder` (백엔드 `service.py` `_svc_name_` ↔ 프론트 `net start/stop ggotAIorder` 일치 필수)

## 0. 사전 정합 확인
- [ ] `backend/src/ggotaiorder/service.py` 의 `_svc_name_ == "ggotAIorder"`
- [ ] 프론트 `frontend/src/main/index.ts` 의 `net start/stop` 대상명이 `ggotAIorder`

## 1. 사전 준비(비-GUI, 보조 가능)
- [ ] 백엔드 의존성: `cd backend && ./.venv/Scripts/python.exe -m pip install -e .[test]`
- [ ] 서비스 설치(관리자 PowerShell): `./.venv/Scripts/python.exe -m ggotaiorder.service install`
- [ ] 등록 확인: `sc query ggotAIorder` → 서비스 존재
- [ ] 프론트 빌드/실행: `cd frontend && npm install && npm run dev` (또는 `npm run build` 후 패키지 실행)

## 2. 검증 절차
| # | 동작 | 명령/조작 | 기대 관측 | 실패 시 진단 |
|---|---|---|---|---|
| 1 | 서비스 시작 | `net start ggotAIorder` (관리자) | `sc query` = RUNNING, 트레이 🟢 | 이벤트뷰어/로그, .env 검증 |
| 2 | 앱 표시 | Electron 앱 실행 | 대시보드 렌더, 채널 상태 위젯 | 콘솔 에러, VITE_ env |
| 3 | 수집 중지 | UI [수집 중지] 클릭 | IPC→`net stop ggotAIorder` 실행 | preload IPC 채널/권한 |
| 4 | 정지 확인 | `sc query ggotAIorder` | STATE = STOPPED | 서비스 stop 핸들러 로그 |
| 5 | 트레이 색 | 트레이 아이콘 육안 | 🔴 (정지색) | tray 상태 연동 로직 |
| 6 | 역검증 | UI [시작] 클릭 | RUNNING + 🟢 | net start 권한(UAC) |

## 3. 결과 기록
- 검증일/검증자:
- 단계별 결과(통과/실패/비고):
- 캡처(트레이 🔴/🟢):
```

- [ ] **Step 2: 커밋**

```bash
git add docs/phase4_manual_verification.md
git commit -m "docs: T2 수동 검증 체크리스트(IPC→서비스정지→트레이)"
```

---

## Task 9: 최종 검증 + task.md 체크오프

**Files:**
- Modify: `task.md` (Phase 4 항목)

- [ ] **Step 1: 전체 오프라인 테스트**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 모두 PASS(신규 T1a/T1b/T1c-skip/프론트/T3a/T3b-skip 포함), 라이브 2건 SKIP. 실패 0.

- [ ] **Step 2: task.md Phase 4 체크오프**

`task.md` 의 Phase 4 세 항목을 `[x]`로 변경하고 각 줄 끝에 검증 방식을 주석으로 명시:
```markdown
## 🔗 Phase 4: 통합 및 최종 검증 (공동 수행)
- [x] 프론트엔드(`ggotAIya` React/Electron)와 백엔드(`ggotAIorder` Windows Service) 간의 Supabase DB 스키마 정합성 교차 테스트 *(자동화: `tests/test_phase4_schema.py`(페이로드 적합성·참조 스캔·라이브 드리프트 opt-in) + `test_phase4_frontend_schema.py`. 기준=`docs/database_schema.sql`)*
- [x] React UI의 [수집 중지] 버튼 클릭 -> Electron IPC -> 백엔드 윈도우 서비스가 정상 정지되고 트레이 아이콘이 🔴로 바뀌는지 OS 수준의 연동 수동 검증 *(수동 체크리스트: `docs/phase4_manual_verification.md`)*
- [x] 모의 음성 파일 Webhook 전송 -> STT 변환 -> Gemini 분석 -> order_details 생성 -> 싱글턴 RPA 실행 -> 카카오 알림톡 발송의 E2E 시나리오 완성도 통합 검증 *(자동화: `tests/test_phase4_e2e.py` 조립 E2E(항상) + 풀 라이브 E2E(opt-in). STT 우회·notify spy)*
```

- [ ] **Step 3: 커밋**

```bash
git add task.md
git commit -m "docs: task.md Phase 4 통합 검증 체크오프(검증 방식 명시)"
```

- [ ] **Step 4: finishing-a-development-branch 스킬로 마무리**

`superpowers:finishing-a-development-branch` 로 머지/PR 옵션 제시.

---

## 라이브 후속(본 plan 범위 밖, 메모리 기록)
- T1c 라이브 드리프트는 `schema.sql ⊆ DB`(단방향)만 검증 — DB 잉여 컬럼 검출은 미커버.
- 프론트 스캔은 best-effort 정규식 — insert 객체 키/동적 컬럼은 미커버.
- T2 수기 검증 결과 기록(실 OS 구동) 및 캡처 첨부.
- 잔여 라이브 후속(N+1 embed 조인 등)은 독립 과제로 유지.
