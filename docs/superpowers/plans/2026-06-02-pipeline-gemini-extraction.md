# pipeline Gemini 추출+필터+DB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ggotaiorder.pipeline` 스텁을 실구현으로 — stt_text에서 Gemini 구조화 추출(11필드) → 누락 3개↑ 필터(is_order) → order_details INSERT(rpa_status='ready') → rpa.enqueue. STT는 인터페이스 스텁 유지.

**Architecture:** `engine.process(call_history_id, repo)`가 오케스트레이션. DB는 `OrderRepository` Protocol로 추상화(실제 `SupabaseOrderRepository`, 테스트 `FakeOrderRepository`). Gemini 추출은 `google-genai` 구조화 출력(Pydantic `OrderExtraction` + `response_schema`, model `gemini-2.5-flash`, 엄격한 anti-hallucination system instruction, temperature 0, 503 재시도). 단위테스트는 fake repo + monkeypatch로 결정적, Gemini 실호출은 opt-in 라이브 테스트.

**Tech Stack:** Python 3.13, google-genai, pydantic, pytest, pytest-asyncio.

설계서: `docs/superpowers/specs/2026-06-02-pipeline-gemini-extraction-design.md`
브랜치: `chore/gemini-sdk-swap` (현재 브랜치에서 이어서 작업)

**검증 명령 전제:** 모든 pytest/python은 venv로 실행 — `backend\.venv\Scripts\python.exe ...`. 저장소 루트 `C:\ggotAI\ggotAIorder`에서 실행.

---

## File Structure

| 파일 | 책임 | 유형 |
| --- | --- | --- |
| `backend/requirements.txt` | `pydantic`, `pytest-asyncio` 추가 | 수정 |
| `backend/pyproject.toml` | `asyncio_mode = "auto"` | 수정 |
| `backend/src/ggotaiorder/config.py` | `GEMINI_API_KEY` 필수 추가 | 수정 |
| `backend/tests/test_config.py` | GEMINI_API_KEY 반영 | 수정 |
| `backend/src/ggotaiorder/pipeline/models.py` | `OrderExtraction`(Pydantic 11필드) + `CallHistory`(DTO) | 신규 |
| `backend/src/ggotaiorder/pipeline/stt.py` | `transcribe(audio_file_name)` 인터페이스 스텁 | 신규 |
| `backend/src/ggotaiorder/pipeline/extractor.py` | `extract_order(stt_text)` Gemini 구조화 추출 | 신규 |
| `backend/src/ggotaiorder/pipeline/repository.py` | `OrderRepository`(Protocol) + `SupabaseOrderRepository` | 신규 |
| `backend/src/ggotaiorder/pipeline/engine.py` | `process()` + `count_missing()` + payload 빌더 | 수정(스텁 대체) |
| `backend/tests/test_pipeline_filter.py` | count_missing 단위테스트 | 신규 |
| `backend/tests/test_pipeline_engine.py` | process 경로별 단위테스트(FakeRepository) | 신규 |
| `backend/tests/test_pipeline_stt.py` | transcribe 스텁 테스트 | 신규 |
| `backend/tests/test_pipeline_extractor_live.py` | Gemini 실호출(opt-in) | 신규 |

---

### Task 1: 의존성·pytest-asyncio 구성

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: requirements.txt 에 pydantic·pytest-asyncio 추가**

`backend/requirements.txt`의 `# --- AI 파이프라인 ---` 블록과 `# --- 개발/테스트 ---` 블록을 아래처럼 만든다. AI 블록에 `pydantic`을 추가하고, 개발 블록에 `pytest-asyncio`를 추가한다(기존 줄은 유지).

AI 파이프라인 블록:
```text
# --- AI 파이프라인 ---
faster-whisper
google-genai
pydantic
```
개발/테스트 블록:
```text
# --- 개발/테스트 ---
pytest
pytest-asyncio
```

- [ ] **Step 2: pyproject.toml 에 asyncio_mode 추가**

`backend/pyproject.toml`의 `[tool.pytest.ini_options]` 섹션을 아래로 교체:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: 설치**

Run:
```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```
Expected: `pytest-asyncio` 설치됨(pydantic은 google-genai 의존으로 이미 설치되어 있을 수 있음 — 그래도 OK).

- [ ] **Step 4: 회귀 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: 기존 27 passed 유지.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/pyproject.toml
git commit -m "chore: pydantic·pytest-asyncio 의존성 및 asyncio 테스트 모드 추가"
```

---

### Task 2: config 에 GEMINI_API_KEY 추가 (TDD)

**Files:**
- Modify: `backend/src/ggotaiorder/config.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: 테스트 수정(실패 유도)**

`backend/tests/test_config.py`를 아래로 교체한다(VALID에 GEMINI_API_KEY 추가, 신규 누락 테스트 추가):
```python
import pytest

from ggotaiorder.config import Config, load_config, ConfigError

VALID = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
    "AES_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # 64 hex -> 32 bytes
    "GEMINI_API_KEY": "test-gemini-key",
}


def test_load_config_returns_values():
    cfg = load_config(env=VALID)
    assert isinstance(cfg, Config)
    assert cfg.supabase_url == "https://example.supabase.co"
    assert cfg.supabase_service_role_key == "service-key"
    assert cfg.aes_encryption_key == VALID["AES_ENCRYPTION_KEY"]
    assert cfg.gemini_api_key == "test-gemini-key"


def test_missing_key_raises():
    broken = dict(VALID)
    del broken["SUPABASE_URL"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_missing_gemini_key_raises():
    broken = dict(VALID)
    del broken["GEMINI_API_KEY"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_empty_key_raises():
    broken = dict(VALID, SUPABASE_ANON_KEY="")
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_aes_key_must_be_32_bytes():
    broken = dict(VALID, AES_ENCRYPTION_KEY="0123456789abcdef")  # 유효 hex, 8 bytes
    with pytest.raises(ConfigError):
        load_config(env=broken)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: FAIL — `test_load_config_returns_values`(`cfg.gemini_api_key` 없음/AttributeError) 및 `test_missing_gemini_key_raises` 실패.

- [ ] **Step 3: config.py 수정**

`backend/src/ggotaiorder/config.py`에서 `_REQUIRED_KEYS`, `Config`, `load_config` return 을 수정한다.

`_REQUIRED_KEYS`를 교체:
```python
_REQUIRED_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AES_ENCRYPTION_KEY",
    "GEMINI_API_KEY",
)
```
`Config` 데이터클래스에 필드 추가:
```python
@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    aes_encryption_key: str
    gemini_api_key: str
```
`load_config`의 return 문을 교체:
```python
    return Config(
        supabase_url=env["SUPABASE_URL"],
        supabase_anon_key=env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=env["SUPABASE_SERVICE_ROLE_KEY"],
        aes_encryption_key=aes_key,
        gemini_api_key=env["GEMINI_API_KEY"],
    )
```
(AES 검증 블록 등 나머지는 그대로 둔다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 5: 실제 .env 로딩 확인**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.config import load_config; c=load_config(); print('gemini key len', len(c.gemini_api_key))"
```
Expected: `gemini key len 39` 같은 양수(실제 .env의 GEMINI_API_KEY 길이). 0이거나 에러면 .env를 확인하고 보고.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ggotaiorder/config.py backend/tests/test_config.py
git commit -m "feat: config 에 GEMINI_API_KEY 필수 항목 추가"
```

---

### Task 3: pipeline/models.py — OrderExtraction + CallHistory (TDD)

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/models.py`
- Test: `backend/tests/test_pipeline_models.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_pipeline_models.py`:
```python
from ggotaiorder.pipeline.models import OrderExtraction, CallHistory


def test_order_extraction_has_11_fields():
    assert len(OrderExtraction.model_fields) == 11


def test_order_extraction_defaults_none():
    e = OrderExtraction()
    dumped = e.model_dump()
    assert all(v is None for v in dumped.values())


def test_call_history_dataclass():
    ch = CallHistory(
        id=1, shop_key=2, shop_name="꽃집",
        customer_name="신규", customer_phone_number="010",
        stt_text="텍스트", audio_file_name=None, channel_order="인터라넷",
    )
    assert ch.id == 1 and ch.shop_name == "꽃집"
```

- [ ] **Step 2: 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_models.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.pipeline.models`.

- [ ] **Step 3: 구현 작성**

`backend/src/ggotaiorder/pipeline/models.py`:
```python
"""파이프라인 데이터 모델: Gemini 추출 스키마 및 수집 이력 DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field


class OrderExtraction(BaseModel):
    """Gemini가 stt_text에서 추출하는 11개 표준 주문 필드(누락은 None)."""

    customer_name: Optional[str] = Field(default=None, description="주문자 이름")
    customer_phone_number: Optional[str] = Field(default=None, description="주문자 전화번호")
    product_name: Optional[str] = Field(default=None, description="상품명")
    quantity: Optional[int] = Field(default=None, description="수량")
    price: Optional[int] = Field(default=None, description="가격(원 단위 정수)")
    delivery_at: Optional[str] = Field(default=None, description="배달 일시")
    delivery_place: Optional[str] = Field(default=None, description="배달 장소")
    receiver_name: Optional[str] = Field(default=None, description="받는 사람 이름")
    receiver_phone_number: Optional[str] = Field(default=None, description="받는 사람 전화번호")
    ribbon_congratulations: Optional[str] = Field(default=None, description="리본 경조사 문구")
    card_message: Optional[str] = Field(default=None, description="카드 메시지")


@dataclass
class CallHistory:
    """server_call_history 한 행의 파이프라인 사용 필드."""

    id: int
    shop_key: int
    shop_name: str
    customer_name: Optional[str]
    customer_phone_number: Optional[str]
    stt_text: Optional[str]
    audio_file_name: Optional[str]
    channel_order: str
```

- [ ] **Step 4: 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/models.py backend/tests/test_pipeline_models.py
git commit -m "feat: pipeline 데이터 모델(OrderExtraction, CallHistory) 추가"
```

---

### Task 4: pipeline/stt.py — STT 인터페이스 스텁 (TDD)

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/stt.py`
- Test: `backend/tests/test_pipeline_stt.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_pipeline_stt.py`:
```python
import pytest

from ggotaiorder.pipeline.stt import transcribe


def test_transcribe_not_implemented():
    with pytest.raises(NotImplementedError):
        transcribe("some_audio.wav")
```

- [ ] **Step 2: 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt.py -v`
Expected: FAIL — `ImportError`/`ModuleNotFoundError`.

- [ ] **Step 3: 구현 작성**

`backend/src/ggotaiorder/pipeline/stt.py`:
```python
"""음성→텍스트(STT) 인터페이스 (faster-whisper 실연동은 다음 증분).

이번 증분에서는 인터페이스만 고정하고, 호출 시 NotImplementedError 를 던진다.
engine.process 는 이 예외를 잡아 해당 건을 건너뛴다(파이프라인 비중단).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def transcribe(audio_file_name: str) -> str:
    """[스텁] 음성 파일을 텍스트로 변환한다.

    TODO(다음 증분): Supabase Storage에서 audio_file_name 다운로드 →
    faster-whisper(한국어)로 STT → 텍스트 반환.
    """
    logger.warning("[STUB] stt.transcribe 미구현: %s", audio_file_name)
    raise NotImplementedError("STT(faster-whisper)는 다음 증분에서 구현됩니다.")
```

- [ ] **Step 4: 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/stt.py backend/tests/test_pipeline_stt.py
git commit -m "feat: STT 인터페이스 스텁(transcribe) 추가"
```

---

### Task 5: pipeline/extractor.py — Gemini 구조화 추출 (+ opt-in 라이브 테스트)

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/extractor.py`
- Test: `backend/tests/test_pipeline_extractor_live.py`

추출 로직은 외부 API라 단위테스트 대신 **opt-in 라이브 테스트**로 검증한다(기본 실행에서는 skip → 결정적·무비용). 구현 중 1회 수동 실행으로 실제 동작을 확인한다. system instruction/모델/스키마/재시도는 사전 검증된 값이다.

- [ ] **Step 1: 라이브 테스트 작성(기본 skip)**

`backend/tests/test_pipeline_extractor_live.py`:
```python
import os

import pytest
from dotenv import load_dotenv

load_dotenv("backend/.env")

# 기본 실행에서는 skip. 실제 Gemini 호출 검증은 RUN_LIVE_GEMINI=1 일 때만.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMINI") != "1",
    reason="RUN_LIVE_GEMINI=1 일 때만 실제 Gemini 호출 테스트 실행",
)

REAL_ORDER = (
    "내일 오후 3시 강남역 1번출구로 배달해주세요. 김철수 생일 축하 꽃다발 한개 "
    "5만원이고 받는분은 이영희 010-1234-5678. 카드에 생일 축하해 라고 적어주세요."
)
NON_ORDER = "여보세요 거기 중국집이죠? 짜장면 두 그릇 배달돼요?"


def test_real_order_extracts_core_fields():
    from ggotaiorder.pipeline.extractor import extract_order

    e = extract_order(REAL_ORDER)
    assert e.product_name is not None
    assert e.price == 50000
    assert e.receiver_name is not None


def test_non_order_returns_mostly_null():
    from ggotaiorder.pipeline.engine import count_missing
    from ggotaiorder.pipeline.extractor import extract_order

    e = extract_order(NON_ORDER)
    # 꽃 주문이 아니므로 대부분 null → 누락 다수
    assert count_missing(e) >= 9
```

- [ ] **Step 2: 실패 확인(opt-in으로 실행)**

Run: `$env:RUN_LIVE_GEMINI="1"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_order'`. (count_missing은 Task 6에서 생기므로 두 번째 테스트는 ImportError; 첫 테스트도 ImportError.)

- [ ] **Step 3: extractor.py 구현**

`backend/src/ggotaiorder/pipeline/extractor.py`:
```python
"""Gemini 기반 주문 정형화 추출 (google-genai 구조화 출력).

stt_text → OrderExtraction(11필드). 입력에 없는 값은 절대 추측하지 않고 None.
"""

from __future__ import annotations

import logging
import time

from google import genai
from google.genai import types

from ggotaiorder.config import load_config
from ggotaiorder.pipeline.models import OrderExtraction

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

_SYSTEM_INSTRUCTION = (
    "너는 꽃집 주문 통화/텍스트에서 주문 정보를 추출하는 엄격한 추출기다.\n"
    "규칙:\n"
    "1. 입력에 명시적으로 나타난 값만 채운다.\n"
    "2. 언급되지 않았거나 불확실하면 반드시 null. 추측·창작 금지.\n"
    "3. 예시/기본값(홍길동, 010-1234-5678 등)을 임의로 넣지 마라.\n"
    "4. 꽃 주문이 아니면(음식주문/잡담/광고 등) 모든 필드를 null.\n"
    "5. 가격은 '5만원'->50000 처럼 원 단위 정수로 변환."
)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=load_config().gemini_api_key)
    return _client


def extract_order(stt_text: str, *, max_retries: int = 3) -> OrderExtraction:
    """stt_text 에서 11개 주문 필드를 구조화 추출한다.

    일시적 오류(예: 503)는 재시도하며, 끝내 실패하면 RuntimeError.
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=OrderExtraction,
        temperature=0,
    )
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents="입력:\n" + stt_text, config=config
            )
            parsed = resp.parsed
            if isinstance(parsed, OrderExtraction):
                return parsed
            return OrderExtraction.model_validate_json(resp.text)
        except Exception as exc:  # noqa: BLE001 - 외부 API 오류 일괄 처리
            last_error = exc
            logger.warning(
                "Gemini 추출 시도 %s/%s 실패: %s",
                attempt + 1, max_retries, str(exc)[:120],
            )
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini 추출 실패(재시도 {max_retries}회 초과): {last_error}")
```

- [ ] **Step 4: 라이브 테스트 통과 확인(opt-in)**

Run: `$env:RUN_LIVE_GEMINI="1"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v`
Expected: 2 passed (Task 6의 count_missing이 아직 없으면 두 번째 테스트는 ImportError이므로, **이 Step은 Task 6 완료 후 재실행**한다. Task 5 시점에는 첫 테스트 `test_real_order_extracts_core_fields`만 실행해 통과를 확인: `... -k test_real_order_extracts_core_fields`). 503으로 실패 시 잠시 후 재실행. 통과를 확인하면 `$env:RUN_LIVE_GEMINI=""`로 해제.

- [ ] **Step 5: 기본 스위트가 라이브 테스트를 skip 하는지 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v`
Expected: 2 skipped (RUN_LIVE_GEMINI 미설정).

- [ ] **Step 6: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/extractor.py backend/tests/test_pipeline_extractor_live.py
git commit -m "feat: Gemini 구조화 주문 추출기(extractor) 추가"
```

---

### Task 6: pipeline/repository.py — DB 추상화

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/repository.py`

`SupabaseOrderRepository`는 실 DB 연동(통합 영역)이라 단위테스트하지 않는다. 계약(Protocol)을 고정하고 import 가능 여부만 확인한다. engine 단위테스트는 Task 7에서 FakeOrderRepository로 한다.

- [ ] **Step 1: 구현 작성**

`backend/src/ggotaiorder/pipeline/repository.py`:
```python
"""주문 파이프라인 DB 접근 추상화.

OrderRepository(Protocol)로 계약을 고정하고, 실제 구현은 Supabase를 사용한다.
테스트는 FakeOrderRepository(tests)로 대체해 결정적으로 검증한다.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.pipeline.models import CallHistory

logger = logging.getLogger(__name__)


class OrderRepository(Protocol):
    """파이프라인이 필요로 하는 DB 연산 계약."""

    def get_call_history(self, call_history_id: int) -> CallHistory: ...

    def update_stt_text(self, call_history_id: int, text: str) -> None: ...

    def set_is_order(self, call_history_id: int, value: str) -> None: ...

    def insert_order_details(self, payload: dict) -> int: ...

    def delete_audio(self, audio_file_name: Optional[str]) -> None: ...


class SupabaseOrderRepository:
    """Supabase 기반 OrderRepository 구현."""

    def get_call_history(self, call_history_id: int) -> CallHistory:
        res = (
            get_client()
            .table("server_call_history")
            .select("*")
            .eq("id", call_history_id)
            .single()
            .execute()
        )
        row = res.data
        return CallHistory(
            id=row["id"],
            shop_key=row["shop_key"],
            shop_name=row["shop_name"],
            customer_name=row.get("customer_name"),
            customer_phone_number=row.get("customer_phone_number"),
            stt_text=row.get("stt_text"),
            audio_file_name=row.get("audio_file_name"),
            channel_order=row.get("channel_order", "기타"),
        )

    def update_stt_text(self, call_history_id: int, text: str) -> None:
        get_client().table("server_call_history").update(
            {"stt_text": text}
        ).eq("id", call_history_id).execute()

    def set_is_order(self, call_history_id: int, value: str) -> None:
        get_client().table("server_call_history").update(
            {"is_order": value}
        ).eq("id", call_history_id).execute()

    def insert_order_details(self, payload: dict) -> int:
        res = get_client().table("order_details").insert(payload).execute()
        return res.data[0]["id"]

    def delete_audio(self, audio_file_name: Optional[str]) -> None:
        if not audio_file_name:
            return
        # TODO(다음 증분): Supabase Storage 버킷에서 실제 파일 삭제.
        logger.warning("[부분구현] delete_audio 미연동(no-op): %s", audio_file_name)
```

- [ ] **Step 2: import 확인**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository; print('repo ok')"
```
Expected: `repo ok` (네트워크 호출 없음 — 메서드 호출 전까지 get_client 미실행).

- [ ] **Step 3: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/repository.py
git commit -m "feat: 주문 파이프라인 DB 추상화(OrderRepository) 추가"
```

---

### Task 7: pipeline/engine.py — process 오케스트레이션 + count_missing (TDD)

**Files:**
- Modify: `backend/src/ggotaiorder/pipeline/engine.py` (스텁 대체)
- Test: `backend/tests/test_pipeline_filter.py`
- Test: `backend/tests/test_pipeline_engine.py`

- [ ] **Step 1: count_missing 실패 테스트 작성**

`backend/tests/test_pipeline_filter.py`:
```python
from ggotaiorder.pipeline.engine import count_missing
from ggotaiorder.pipeline.models import OrderExtraction


def test_all_present_zero_missing():
    e = OrderExtraction(
        customer_name="a", customer_phone_number="b", product_name="c",
        quantity=1, price=1000, delivery_at="d", delivery_place="e",
        receiver_name="f", receiver_phone_number="g",
        ribbon_congratulations="h", card_message="i",
    )
    assert count_missing(e) == 0


def test_all_none_counts_eleven():
    assert count_missing(OrderExtraction()) == 11


def test_blank_string_counts_as_missing():
    e = OrderExtraction(product_name="   ", receiver_name="")
    # product_name 공백, receiver_name 빈문자 → 둘 다 누락. 나머지 9 None.
    assert count_missing(e) == 11


def test_two_missing_below_threshold():
    e = OrderExtraction(
        customer_name="a", customer_phone_number="b", product_name="c",
        quantity=1, price=1000, delivery_at="d", delivery_place="e",
        receiver_name="f", receiver_phone_number="g",
        # ribbon_congratulations, card_message 누락 = 2
    )
    assert count_missing(e) == 2
```

- [ ] **Step 2: 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_filter.py -v`
Expected: FAIL — `ImportError: cannot import name 'count_missing'`.

- [ ] **Step 3: engine.py 작성(스텁 전체 교체)**

`backend/src/ggotaiorder/pipeline/engine.py` 전체를 아래로 교체:
```python
"""AI 데이터 정형화 파이프라인.

stt_text → Gemini 11필드 추출 → 누락 3개 이상이면 주문 아님(is_order='N'),
아니면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
STT(음성→텍스트)는 stt.transcribe 인터페이스로 위임(현재 스텁).
"""

from __future__ import annotations

import logging

from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.pipeline.repository import OrderRepository, SupabaseOrderRepository
from ggotaiorder.pipeline.stt import transcribe
from ggotaiorder.rpa.singleton_macro import enqueue
from ggotaiorder.scraper.crawler import INTRANET_AUDIO_MARKER

logger = logging.getLogger(__name__)

# Gemini가 추출하는 11개 표준 주문서 필드 (OrderExtraction과 동일)
ORDER_FIELDS = tuple(OrderExtraction.model_fields.keys())

# 누락이 이 값 이상이면 꽃 주문이 아닌 것으로 판별 (PRD 6-4)
_MISSING_THRESHOLD = 3


def count_missing(extraction: OrderExtraction) -> int:
    """11필드 중 None 또는 공백 문자열인 항목 수를 센다."""
    missing = 0
    for value in extraction.model_dump().values():
        if value is None:
            missing += 1
        elif isinstance(value, str) and value.strip() == "":
            missing += 1
    return missing


def _build_order_payload(row: CallHistory, extraction: OrderExtraction) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다."""
    return {
        "call_history_id": row.id,
        "shop_key": row.shop_key,
        "shop_name": row.shop_name,
        "customer_name": extraction.customer_name or row.customer_name or "신규",
        "customer_phone_number": (
            extraction.customer_phone_number or row.customer_phone_number or ""
        ),
        "product_name": extraction.product_name,
        "quantity": extraction.quantity or 1,
        "price": extraction.price or 0,
        "delivery_at": extraction.delivery_at,
        "delivery_place": extraction.delivery_place,
        "receiver_name": extraction.receiver_name,
        "receiver_phone_number": extraction.receiver_phone_number,
        "ribbon_congratulations": extraction.ribbon_congratulations,
        "card_message": extraction.card_message,
        "rpa_status": "ready",
    }


async def process(call_history_id: int, repo: OrderRepository | None = None) -> None:
    """단일 수집 건을 정형화 처리한다.

    repo 미지정 시 SupabaseOrderRepository 를 사용한다(테스트는 fake 주입).
    """
    repo = repo or SupabaseOrderRepository()

    try:
        row = repo.get_call_history(call_history_id)
    except Exception:
        logger.exception("수집 이력 조회 실패 id=%s", call_history_id)
        return

    stt_text = row.stt_text
    if not stt_text:
        if row.audio_file_name and row.audio_file_name != INTRANET_AUDIO_MARKER:
            try:
                stt_text = transcribe(row.audio_file_name)
                repo.update_stt_text(call_history_id, stt_text)
            except NotImplementedError:
                logger.warning("STT 미구현 — 건너뜀 id=%s", call_history_id)
                return
        else:
            logger.warning("stt_text 없음 — 건너뜀 id=%s", call_history_id)
            return

    try:
        extraction = extract_order(stt_text)
    except Exception:
        logger.exception("Gemini 추출 실패 id=%s", call_history_id)
        return

    missing = count_missing(extraction)
    if missing >= _MISSING_THRESHOLD:
        repo.set_is_order(call_history_id, "N")
        repo.delete_audio(row.audio_file_name)
        logger.info("주문 아님 판별 id=%s (누락 %s개)", call_history_id, missing)
        return

    repo.set_is_order(call_history_id, "Y")
    order_id = repo.insert_order_details(_build_order_payload(row, extraction))
    logger.info("order_details 생성 id=%s order_id=%s", call_history_id, order_id)
    await enqueue(order_id)
```

- [ ] **Step 4: count_missing 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_filter.py -v`
Expected: 4 passed.

- [ ] **Step 5: engine process 경로별 테스트 작성**

`backend/tests/test_pipeline_engine.py`:
```python
import pytest

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


async def test_non_order_path_sets_N_and_no_insert(monkeypatch):
    repo = FakeRepo(_row(audio_file_name="call_001.wav"))
    # 누락 11개(전부 None) → 주문 아님
    monkeypatch.setattr(engine, "extract_order", lambda text: OrderExtraction())
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("set_is_order", 1, "N") in repo.calls
    assert "insert" not in kinds
    assert ("delete_audio", "call_001.wav") in repo.calls


async def test_stt_needed_but_stub_skips(monkeypatch):
    # stt_text 없음 + 실제 음성 → transcribe(NotImplementedError) → skip
    repo = FakeRepo(_row(stt_text=None, audio_file_name="call_002.wav"))
    called = {"extract": False}

    def boom(text):
        called["extract"] = True
        return _full_extraction()

    monkeypatch.setattr(engine, "extract_order", boom)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert "insert" not in kinds
    assert called["extract"] is False  # 추출까지 가지 않고 skip
```

- [ ] **Step 6: engine 테스트 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_engine.py -v`
Expected: 3 passed (asyncio_mode=auto 로 async 테스트 실행).

- [ ] **Step 7: 스모크 호환 확인(ORDER_FIELDS 11 유지)**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_smoke.py -v`
Expected: 기존 smoke 전부 pass (`test_pipeline_has_11_fields` 포함 — ORDER_FIELDS 길이 11 유지).

- [ ] **Step 8: Commit**

```bash
git add backend/src/ggotaiorder/pipeline/engine.py backend/tests/test_pipeline_filter.py backend/tests/test_pipeline_engine.py
git commit -m "feat: pipeline engine 실구현(추출·필터·DB기록·RPA큐) + 경로별 테스트"
```

---

### Task 8: 전체 검증 + 라이브 스모크 + README

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: 전체 스위트 실행(라이브 제외)**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: 모두 pass. 신규(config 5 갱신, models 3, stt 1, filter 4, engine 3, extractor_live 2 skipped) + 기존(crypto 6, orchestrator 2, smoke 15) = 39 passed, 2 skipped. 실제 합계를 보고.

- [ ] **Step 2: 라이브 Gemini 스모크 1회 수동 실행**

Run:
```powershell
$env:RUN_LIVE_GEMINI="1"; $env:PYTHONIOENCODING="utf-8"
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v
$env:RUN_LIVE_GEMINI=""
```
Expected: 2 passed (실제 Gemini 호출 — 503 발생 시 재시도/재실행). 통과를 확인하고 보고. **이 결과는 커밋에 영향 없음**(테스트 코드 변경 없음).

- [ ] **Step 3: README 에 pipeline 라이브 테스트 안내 추가**

`backend/README.md`의 `## 테스트` 섹션 바로 아래에 다음 단락을 추가:
```markdown
### Gemini 라이브 테스트 (선택)

실제 Gemini API를 호출하는 추출 테스트는 기본적으로 skip됩니다. 실제 호출로 검증하려면:
```powershell
$env:RUN_LIVE_GEMINI="1"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v
```
`GEMINI_API_KEY`가 `backend/.env`에 있어야 합니다.
```

- [ ] **Step 4: Commit**

```bash
git add backend/README.md
git commit -m "docs: pipeline Gemini 라이브 테스트 실행법 README 추가"
```

---

## Self-Review 결과

- **Spec 커버리지**: 범위/STT인터페이스(Task4) · Gemini 구조화추출+anti-hallucination+재시도(Task5) · 모듈분해(models3·extractor5·stt4·repository6·engine7) · 데이터흐름 process(Task7) · 11필드/누락규칙(Task3·7) · config GEMINI_API_KEY(Task2) · 에러처리(engine try/except, extractor 재시도) · 테스트(filter·engine 경로별·라이브 opt-in, Task1 pytest-asyncio) · 의존성(Task1) — 설계서 9개 절 모두 매핑.
- **Placeholder 스캔**: stt/repository의 `TODO(다음 증분)`는 설계서가 명시한 의도적 비범위 표식(실동작 스텁/부분구현)이며 빈 placeholder 아님.
- **타입 일관성**: `OrderExtraction`(11필드), `CallHistory`(8필드), `OrderRepository` 메서드(get_call_history/update_stt_text/set_is_order/insert_order_details/delete_audio), `extract_order(stt_text)->OrderExtraction`, `transcribe(audio_file_name)->str`, `count_missing(OrderExtraction)->int`, `process(call_history_id, repo)`, `enqueue(order_id)` — Task 간 시그니처 일치.
- **검증 가능성**: 단위테스트 결정적(fake repo + monkeypatch), 라이브는 opt-in + 사전 검증된 프롬프트. 기존 27 회귀 유지.
- **주의(통합 영역)**: `SupabaseOrderRepository.insert_order_details`는 order_details의 NOT NULL 컬럼(product_name 등)이 비면 실패할 수 있음 — 실 DB 연동(api/realtime 배선) 증분에서 기본값/검증 보강 필요. 이번 증분은 fake repo로 로직만 검증.
