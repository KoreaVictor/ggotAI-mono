# 스마트스토어 커머스API 연동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 커머스API로 스마트스토어 신규주문을 수집해 `order_details`(rpa_status='ready')로 적재하고, FlowerNT RPA 입력 성공 후 자동 발주확인까지 수행하는 `mall/` 모듈을 오프라인 검증 가능하게 구현한다.

**Architecture:** 인터라넷 크롤러(`scraper/`)와 대칭인 새 `mall/` 패키지. `collector.poll_once`(APScheduler 주기 호출)가 수집 오케스트레이션을, 별도 `MallConfirmScanner`가 RPA 성공분 자동 발주확인을 담당한다. 커머스API·DB는 Protocol로 추상화해 fake 주입으로 결정적 오프라인 테스트. 실제 HTTP(OAuth2·주문조회·발주확인)는 client_id/secret 확보 전까지 스텁(`NotImplementedError`), 단 bcrypt 전자서명은 지금 구현·단위테스트.

**Tech Stack:** Python 3.13, pydantic, apscheduler, supabase-py, bcrypt(신규), pytest(`asyncio_mode="auto"`). 설계서: `docs/superpowers/specs/2026-07-04-smartstore-commerce-api-design.md`.

## Global Constraints

- 백엔드 루트: `C:\ggotAI\ggotAIorder\backend`. 패키지 `ggotaiorder`. 모든 pytest·명령은 이 디렉토리에서 실행.
- 테스트 실행: `python -m pytest`. 비동기 테스트는 `asyncio_mode="auto"`(pyproject 기설정) — `async def test_*` 그대로 동작, `@pytest.mark.asyncio` 불필요.
- 채널 상수 정확히: `SMARTSTORE_CHANNEL = "쇼핑몰"`, `SMARTSTORE_AUDIO_MARKER = "SMARTSTORE_API"`, `PROVIDER_SMARTSTORE = "smartstore"`.
- 재사용(신규 구현 금지): `core.crypto.decrypt/encrypt`, `pipeline.extractor.extract_order`, `rpa.singleton_macro.enqueue`, `notifier.sms_sender.send`. `enqueue`/`send`는 `await` 대상 async, repo·client·decrypt·extract 같은 동기 블로킹은 `asyncio.to_thread`로 오프로드.
- notifier 현재 시그니처: `send(shop_key, channel, count, outcome, *, ...)`. 비상 알림은 `outcome="fail"` 사용(설계서 §8의 `success=False`는 낡은 표기 — 무시).
- Supabase 프로젝트 ref: `suylrznbctrkbxbleapb`. 마이그레이션 파일은 `C:\ggotAI\supabase\migrations\`.
- 기존 테스트 전량 회귀 통과가 각 태스크의 암묵 요건. 커밋은 태스크 끝마다.
- 브랜치는 이미 `feature/smartstore-commerce-api` (설계서 커밋 `a84a22f` 위에서 이어감).

---

### Task 1: 스키마 마이그레이션 — mall_credentials 테이블 + order_details 발주확인 컬럼

**Files:**
- Create: `C:\ggotAI\supabase\migrations\20260704000100_mall_credentials.sql`

**Interfaces:**
- Produces: 테이블 `mall_credentials(id, shop_key, provider, client_id, enc_client_secret, extra jsonb, cursor timestamptz, is_active, created_at)`, `UNIQUE(shop_key, provider)`; `order_details.mall_ack_status varchar(20)`, `order_details.mall_ack_attempts int default 0`. 이후 모든 repo 태스크가 이 스키마에 의존.

- [ ] **Step 1: 마이그레이션 SQL 작성**

```sql
-- 스마트스토어(및 향후 쿠팡) 커머스API 연동: 자격증명 테이블 + order_details 발주확인 컬럼.
-- 설계서 2026-07-04-smartstore-commerce-api-design.md §6.

CREATE TABLE IF NOT EXISTS mall_credentials (
    id SERIAL PRIMARY KEY,
    shop_key INT NOT NULL,
    provider VARCHAR(20) NOT NULL,             -- 'smartstore' | 'coupang'
    client_id VARCHAR(255) NOT NULL,
    enc_client_secret TEXT NOT NULL,           -- core.crypto AES 암호문(iv_hex:ct_b64)
    extra JSONB DEFAULT '{}'::jsonb,           -- store_id 등 provider별 부가정보
    cursor TIMESTAMPTZ DEFAULT NULL,           -- last-changed 조회 커서
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(shop_key, provider),
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

ALTER TABLE order_details
    ADD COLUMN IF NOT EXISTS mall_ack_status VARCHAR(20) DEFAULT NULL,  -- NULL=비쇼핑몰, 'pending'|'confirmed'|'skipped'
    ADD COLUMN IF NOT EXISTS mall_ack_attempts INT DEFAULT 0;           -- 발주확인 재시도 카운트(상한용)
```

- [ ] **Step 2: 라이브 적용 (Supabase MCP)**

`mcp__supabase__apply_migration` 호출 — `project_id="suylrznbctrkbxbleapb"`, `name="20260704000100_mall_credentials"`, `query`=위 SQL 전체.
추가 컬럼·신규 테이블 전부 additive(기존 데이터·동작 불변)이므로 안전.

- [ ] **Step 3: 적용 검증**

`mcp__supabase__list_tables`(project_id 동일)로 `mall_credentials` 존재 확인.
`mcp__supabase__execute_sql` 로 `SELECT column_name FROM information_schema.columns WHERE table_name='order_details' AND column_name IN ('mall_ack_status','mall_ack_attempts');` → 2행 반환 확인.
Expected: 테이블 존재 + 컬럼 2개.

- [ ] **Step 4: Commit**

```bash
git add ../supabase/migrations/20260704000100_mall_credentials.sql
git commit -m "feat(mall): mall_credentials 테이블 + order_details 발주확인 컬럼 마이그레이션"
```

---

### Task 2: mall 패키지 + models.py

**Files:**
- Create: `backend/src/ggotaiorder/mall/__init__.py` (빈 파일)
- Create: `backend/src/ggotaiorder/mall/models.py`
- Test: `backend/tests/test_mall_models.py`

**Interfaces:**
- Produces:
  - 상수 `SMARTSTORE_CHANNEL="쇼핑몰"`, `SMARTSTORE_AUDIO_MARKER="SMARTSTORE_API"`, `PROVIDER_SMARTSTORE="smartstore"`.
  - `MallCredential(shop_key:int, shop_name:str, provider:str, client_id:str, enc_client_secret:str, extra:dict, cursor:str|None=None, client_secret:str|None=None)` — `client_secret`은 런타임 복호화 주입용.
  - `SmartStoreOrder(product_order_id:str, raw_text:str, memo_text:str, fields:OrderExtraction)`.
  - `ConfirmTarget(order_id:int, shop_key:int, product_order_id:str, ack_attempts:int)`.

- [ ] **Step 1: 빈 패키지 파일 생성**

`backend/src/ggotaiorder/mall/__init__.py` 를 빈 내용으로 생성.

- [ ] **Step 2: 실패 테스트 작성**

`backend/tests/test_mall_models.py`:

```python
from ggotaiorder.mall.models import (
    PROVIDER_SMARTSTORE,
    SMARTSTORE_AUDIO_MARKER,
    SMARTSTORE_CHANNEL,
    ConfirmTarget,
    MallCredential,
    SmartStoreOrder,
)
from ggotaiorder.pipeline.models import OrderExtraction


def test_constants():
    assert SMARTSTORE_CHANNEL == "쇼핑몰"
    assert SMARTSTORE_AUDIO_MARKER == "SMARTSTORE_API"
    assert PROVIDER_SMARTSTORE == "smartstore"


def test_credential_defaults():
    cred = MallCredential(
        shop_key=1, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={"store_id": "s1"},
    )
    assert cred.cursor is None
    assert cred.client_secret is None
    assert cred.extra["store_id"] == "s1"


def test_smartstore_order_holds_fields():
    order = SmartStoreOrder(
        product_order_id="PO1", raw_text="원문", memo_text="메모",
        fields=OrderExtraction(product_name="장미", price=30000),
    )
    assert order.fields.product_name == "장미"


def test_confirm_target():
    t = ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=2)
    assert t.order_id == 10 and t.ack_attempts == 2
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_mall_models.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.mall.models`.

- [ ] **Step 4: models.py 구현**

`backend/src/ggotaiorder/mall/models.py`:

```python
"""스마트스토어 커머스API 연동 데이터 모델.

인터라넷 크롤러(scraper.models)와 대칭. server_call_history.channel_order 에는
SMARTSTORE_CHANNEL, audio_file_name 에는 provider 식별 마커 SMARTSTORE_AUDIO_MARKER 를
기록한다(scraper 의 INTRANET_CRAWLED 대칭).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ggotaiorder.pipeline.models import OrderExtraction

# server_call_history.channel_order (수집·중복검증·발주확인 스캐너가 공유하는 단일 출처).
SMARTSTORE_CHANNEL = "쇼핑몰"
# audio_file_name 에 기록하는 provider 식별 마커(발주확인 대상 필터에 사용).
SMARTSTORE_AUDIO_MARKER = "SMARTSTORE_API"
# mall_credentials.provider 값.
PROVIDER_SMARTSTORE = "smartstore"


@dataclass
class MallCredential:
    """mall_credentials 한 행 + 런타임 복호화 secret."""

    shop_key: int
    shop_name: str
    provider: str
    client_id: str
    enc_client_secret: str        # AES 암호문(복호화 전)
    extra: dict = field(default_factory=dict)  # store_id 등 provider별 부가정보
    cursor: str | None = None     # last-changed 조회 커서(ISO8601), 없으면 None
    client_secret: str | None = None  # 복호화된 평문(collector 가 런타임 주입)


@dataclass
class SmartStoreOrder:
    """수집된 단일 스마트스토어 주문."""

    product_order_id: str       # 중복 식별키(server_call_history.channel_classification)
    raw_text: str               # 원문(stt_text 로 저장)
    memo_text: str              # Gemini 에 넣을 자유텍스트(메모+옵션+상품명)
    fields: OrderExtraction     # API 정형값으로 채운 권위 필드(배달일시·리본·카드·분류는 None)


@dataclass
class ConfirmTarget:
    """발주확인 대상(rpa_status='success' && mall_ack_status='pending')."""

    order_id: int
    shop_key: int
    product_order_id: str
    ack_attempts: int
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_mall_models.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ggotaiorder/mall/__init__.py src/ggotaiorder/mall/models.py tests/test_mall_models.py
git commit -m "feat(mall): mall 패키지 + 데이터 모델(MallCredential/SmartStoreOrder/ConfirmTarget)"
```

---

### Task 3: 공용 order_details payload 헬퍼 추출 (pipeline 공유)

**Files:**
- Create: `backend/src/ggotaiorder/pipeline/order_payload.py`
- Modify: `backend/src/ggotaiorder/pipeline/engine.py` (헬퍼 3개를 order_payload로 이관하고 별칭으로 재노출)
- Test: `backend/tests/test_pipeline_order_payload.py`

**Interfaces:**
- Consumes: `pipeline.models.CallHistory`, `OrderExtraction`, `DELIVERY_AT_UNKNOWN`, `STORE_SALE_CHANNEL`.
- Produces: `build_order_payload(row:CallHistory, extraction:OrderExtraction) -> dict`, `normalize_delivery_at(value:str|None) -> str`, `resolve_delivery_at(row:CallHistory, extraction:OrderExtraction) -> str`. Task 6(collector)이 `build_order_payload` 를 재사용.
- 하위호환: `engine._build_order_payload` / `engine._normalize_delivery_at` / `engine._resolve_delivery_at` 는 별칭으로 유지(기존 `test_phase4_schema.py`·`test_pipeline_delivery_at.py`가 참조).

- [ ] **Step 1: 회귀 기준 확인 (현행 통과 스냅샷)**

Run: `python -m pytest tests/test_pipeline_engine.py tests/test_pipeline_delivery_at.py tests/test_phase4_schema.py -q`
Expected: 전부 PASS (리팩터 후 동일해야 함 — 기준선).

- [ ] **Step 2: 신규 헬퍼 테스트 작성**

`backend/tests/test_pipeline_order_payload.py`:

```python
from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction
from ggotaiorder.pipeline.order_payload import (
    build_order_payload,
    normalize_delivery_at,
)


def _row(channel="쇼핑몰"):
    return CallHistory(
        id=1, shop_key=7, shop_name="꽃집", customer_name=None,
        customer_phone_number=None, stt_text="원문", audio_file_name="X",
        channel_order=channel,
    )


def test_normalize_iso_passthrough():
    assert normalize_delivery_at("2026-07-04T15:00:00+09:00") == "2026-07-04T15:00:00+09:00"


def test_normalize_natural_language_falls_back_to_sentinel():
    assert normalize_delivery_at("내일 오후 3시") == DELIVERY_AT_UNKNOWN


def test_build_payload_defaults_and_status():
    p = build_order_payload(_row(), OrderExtraction(product_name="장미", price=30000))
    assert p["product_name"] == "장미"
    assert p["quantity"] == 1          # None → 기본 1
    assert p["delivery_place"] == "미정"
    assert p["delivery_at"] == DELIVERY_AT_UNKNOWN  # 쇼핑몰 채널은 센티넬 유지(매장판매 아님)
    assert p["rpa_status"] == "ready"


def test_engine_aliases_still_exist():
    # 하위호환: 기존 테스트가 참조하는 engine 심볼이 살아있어야 한다.
    from ggotaiorder.pipeline import engine
    assert engine._build_order_payload is build_order_payload
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_pipeline_order_payload.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.pipeline.order_payload`.

- [ ] **Step 4: order_payload.py 생성 (engine에서 헬퍼 이관)**

`backend/src/ggotaiorder/pipeline/order_payload.py`:

```python
"""order_details INSERT payload 조립 (pipeline·mall 공용 단일 출처).

기존 engine 내부 헬퍼를 이관. delivery_at 정규화·센티넬 폴백, 매장판매 배송일=주문일
보정, NOT NULL 안전 기본값 규칙을 한 곳에서 관리한다(설계서 §6). engine 은 이 모듈을
재수출(별칭)해 동작 불변.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, CallHistory, OrderExtraction

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# 매장판매(즉석 판매) 채널. 배송일 미상 시 주문일(오늘 KST)로 채운다.
STORE_SALE_CHANNEL = "가게음성"


def normalize_delivery_at(value: str | None) -> str:
    """배달일시를 유효한 timestamptz 문자열로 정규화한다.

    ISO 8601 이면 그대로, 자연어거나 비어 있으면 센티넬로 폴백해 INSERT(NOT NULL)가
    깨지지 않게 한다(원문은 delivery_at_text 보존).
    """
    if value:
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            logger.info("delivery_at 파싱 불가 — 센티넬 폴백: %r", value)
    return DELIVERY_AT_UNKNOWN


def resolve_delivery_at(row: CallHistory, extraction: OrderExtraction) -> str:
    """배송일시 결정. 매장판매는 배송일 미상 시 주문일(오늘 KST)로 채운다."""
    resolved = normalize_delivery_at(extraction.delivery_at)
    if resolved == DELIVERY_AT_UNKNOWN and row.channel_order == STORE_SALE_CHANNEL:
        return datetime.now(_KST).isoformat()
    return resolved


def build_order_payload(row: CallHistory, extraction: OrderExtraction) -> dict:
    """추출 결과 + 수집 이력으로 order_details INSERT payload 를 만든다.

    NOT NULL·DEFAULT 없는 컬럼은 미상 시 안전 기본값으로 채운다(설계서 §6).
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
        "delivery_at": resolve_delivery_at(row, extraction),
        "delivery_at_text": extraction.delivery_at_text,
        "delivery_place": extraction.delivery_place or "미정",
        "receiver_name": extraction.receiver_name or "미정",
        "receiver_phone_number": extraction.receiver_phone_number or "",
        "ribbon_congratulations": extraction.ribbon_congratulations,
        "card_message": extraction.card_message,
        "sang_divi": extraction.sang_divi,
        "rpa_status": "ready",
    }
```

- [ ] **Step 5: engine.py 를 재수출로 전환**

`backend/src/ggotaiorder/pipeline/engine.py` 에서 헬퍼 정의부(현재 73~127행의 `_normalize_delivery_at`, `_resolve_delivery_at`, `_build_order_payload` 함수 본문 전체)를 삭제하고, 대신 상단 import 구역에 다음을 추가한다:

```python
from ggotaiorder.pipeline.order_payload import (
    STORE_SALE_CHANNEL,
    build_order_payload,
    normalize_delivery_at,
    resolve_delivery_at,
)
```

그리고 삭제한 함수 자리(또는 import 바로 아래)에 하위호환 별칭을 둔다:

```python
# 하위호환 별칭(기존 호출부·테스트가 engine._build_order_payload 등을 참조).
_normalize_delivery_at = normalize_delivery_at
_resolve_delivery_at = resolve_delivery_at
_build_order_payload = build_order_payload
```

주의: engine 상단에 이미 있던 `STORE_SALE_CHANNEL = "가게음성"` 정의와 `from ...models import ... OrderExtraction` 는 중복 정의를 피하기 위해 정리한다 — `STORE_SALE_CHANNEL` 은 order_payload 에서 import 한 것을 쓰고(기존 로컬 정의 라인 삭제), `_KST`·`datetime` 등 남은 사용처(`process`/`is_order` 등)가 있으면 기존 import 는 유지한다. `process()` 본문의 `_build_order_payload(row, extraction)` 호출은 별칭이 살아있으므로 수정 불필요.

- [ ] **Step 6: 신규 + 회귀 테스트 통과 확인**

Run: `python -m pytest tests/test_pipeline_order_payload.py tests/test_pipeline_engine.py tests/test_pipeline_delivery_at.py tests/test_phase4_schema.py -q`
Expected: 전부 PASS (Step 1 기준선과 동일 + 신규 4건).

- [ ] **Step 7: Commit**

```bash
git add src/ggotaiorder/pipeline/order_payload.py src/ggotaiorder/pipeline/engine.py tests/test_pipeline_order_payload.py
git commit -m "refactor(pipeline): order_details payload 헬퍼를 order_payload.py로 추출(mall 공유)"
```

---

### Task 4: 저장소 — credentials_repo.py + order_repo.py

**Files:**
- Create: `backend/src/ggotaiorder/mall/credentials_repo.py`
- Create: `backend/src/ggotaiorder/mall/order_repo.py`
- Test: `backend/tests/test_mall_repos.py`

**Interfaces:**
- Produces:
  - `MallCredentialRepository(Protocol)`: `list_credentials(provider:str)->list[MallCredential]`, `update_cursor(shop_key:int, provider:str, cursor:str)->None`.
  - `SupabaseMallCredentialRepository` (구현).
  - `MallOrderRepository(Protocol)`: `order_exists(shop_key:int, product_order_id:str)->bool`, `insert_call_history(record:dict)->int`, `insert_order_details(payload:dict)->int`, `list_confirmable(provider_marker:str)->list[ConfirmTarget]`, `mark_ack(order_id:int, status:str)->None`, `increment_ack_attempts(order_id:int)->int`.
  - `SupabaseMallOrderRepository` (구현).
- 참고: Supabase 구현의 HTTP/DB 부분은 라이브 영역(설계서 §9) — 테스트는 import + Protocol 구조 적합성만. 실제 쿼리 정확성은 라이브 체크리스트에서 검증.

- [ ] **Step 1: 실패 테스트 작성 (import + 구조 적합성)**

`backend/tests/test_mall_repos.py`:

```python
from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.order_repo import (
    MallOrderRepository,
    SupabaseMallOrderRepository,
)


def test_credential_repo_conforms_to_protocol():
    repo = SupabaseMallCredentialRepository()
    assert isinstance(repo, MallCredentialRepository)
    for name in ("list_credentials", "update_cursor"):
        assert callable(getattr(repo, name))


def test_order_repo_conforms_to_protocol():
    repo = SupabaseMallOrderRepository()
    assert isinstance(repo, MallOrderRepository)
    for name in (
        "order_exists", "insert_call_history", "insert_order_details",
        "list_confirmable", "mark_ack", "increment_ack_attempts",
    ):
        assert callable(getattr(repo, name))
```

`MallCredentialRepository`·`MallOrderRepository` 는 `@runtime_checkable` Protocol 이어야 `isinstance` 검사가 동작한다(아래 구현에서 데코레이터 부여).

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mall_repos.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.mall.credentials_repo`.

- [ ] **Step 3: credentials_repo.py 구현**

`backend/src/ggotaiorder/mall/credentials_repo.py`:

```python
"""mall_credentials DB 접근: 자격 목록·커서 갱신."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import MallCredential

logger = logging.getLogger(__name__)


@runtime_checkable
class MallCredentialRepository(Protocol):
    """collector 가 필요로 하는 자격증명 DB 연산 계약."""

    def list_credentials(self, provider: str) -> list[MallCredential]: ...

    def update_cursor(self, shop_key: int, provider: str, cursor: str) -> None: ...


class SupabaseMallCredentialRepository:
    """Supabase 기반 MallCredentialRepository 구현."""

    def list_credentials(self, provider: str) -> list[MallCredential]:
        client = get_client()
        res = (
            client.table("mall_credentials")
            .select("*")
            .eq("provider", provider)
            .eq("is_active", True)
            .execute()
        )
        creds: list[MallCredential] = []
        for row in res.data or []:
            member = (
                client.table("member_info")
                .select("shop_name")
                .eq("id", row["shop_key"])
                .limit(1)
                .execute()
            )
            shop_name = member.data[0]["shop_name"] if member.data else ""
            creds.append(
                MallCredential(
                    shop_key=row["shop_key"],
                    shop_name=shop_name,
                    provider=row["provider"],
                    client_id=row["client_id"],
                    enc_client_secret=row["enc_client_secret"],
                    extra=row.get("extra") or {},
                    cursor=row.get("cursor"),
                )
            )
        return creds

    def update_cursor(self, shop_key: int, provider: str, cursor: str) -> None:
        (
            get_client()
            .table("mall_credentials")
            .update({"cursor": cursor})
            .eq("shop_key", shop_key)
            .eq("provider", provider)
            .execute()
        )
```

- [ ] **Step 4: order_repo.py 구현**

`backend/src/ggotaiorder/mall/order_repo.py`:

```python
"""쇼핑몰 주문 DB 접근: 중복검증·INSERT·발주확인 대상 조회/마킹."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import SMARTSTORE_CHANNEL, ConfirmTarget

logger = logging.getLogger(__name__)


@runtime_checkable
class MallOrderRepository(Protocol):
    """collector·confirm_scanner 가 필요로 하는 주문 DB 연산 계약."""

    def order_exists(self, shop_key: int, product_order_id: str) -> bool: ...

    def insert_call_history(self, record: dict) -> int: ...

    def insert_order_details(self, payload: dict) -> int: ...

    def list_confirmable(self, provider_marker: str) -> list[ConfirmTarget]: ...

    def mark_ack(self, order_id: int, status: str) -> None: ...

    def increment_ack_attempts(self, order_id: int) -> int: ...


class SupabaseMallOrderRepository:
    """Supabase 기반 MallOrderRepository 구현."""

    def order_exists(self, shop_key: int, product_order_id: str) -> bool:
        res = (
            get_client()
            .table("server_call_history")
            .select("id")
            .eq("shop_key", shop_key)
            .eq("channel_order", SMARTSTORE_CHANNEL)
            .eq("channel_classification", product_order_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def insert_call_history(self, record: dict) -> int:
        res = get_client().table("server_call_history").insert(record).execute()
        if not res.data:
            raise RuntimeError("server_call_history INSERT가 행을 반환하지 않았습니다.")
        return res.data[0]["id"]

    def insert_order_details(self, payload: dict) -> int:
        res = get_client().table("order_details").insert(payload).execute()
        if not res.data:
            raise RuntimeError("order_details INSERT가 행을 반환하지 않았습니다.")
        return res.data[0]["id"]

    def list_confirmable(self, provider_marker: str) -> list[ConfirmTarget]:
        """rpa_status='success' && mall_ack_status='pending' 이고, 연결된
        server_call_history.audio_file_name == provider_marker 인 대상 목록."""
        client = get_client()
        rows = (
            client.table("order_details")
            .select("id, shop_key, call_history_id, mall_ack_attempts")
            .eq("rpa_status", "success")
            .eq("mall_ack_status", "pending")
            .execute()
        )
        targets: list[ConfirmTarget] = []
        for row in rows.data or []:
            ch = (
                client.table("server_call_history")
                .select("channel_classification, audio_file_name")
                .eq("id", row["call_history_id"])
                .limit(1)
                .execute()
            )
            if not ch.data:
                continue
            c = ch.data[0]
            if c.get("audio_file_name") != provider_marker:
                continue
            targets.append(
                ConfirmTarget(
                    order_id=row["id"],
                    shop_key=row["shop_key"],
                    product_order_id=c.get("channel_classification") or "",
                    ack_attempts=row.get("mall_ack_attempts") or 0,
                )
            )
        return targets

    def mark_ack(self, order_id: int, status: str) -> None:
        (
            get_client()
            .table("order_details")
            .update({"mall_ack_status": status})
            .eq("id", order_id)
            .execute()
        )

    def increment_ack_attempts(self, order_id: int) -> int:
        """mall_ack_attempts 를 1 증가(읽기-수정-쓰기)하고 새 값을 반환한다."""
        client = get_client()
        cur = (
            client.table("order_details")
            .select("mall_ack_attempts")
            .eq("id", order_id)
            .limit(1)
            .execute()
        )
        attempts = 0
        if cur.data:
            attempts = cur.data[0].get("mall_ack_attempts") or 0
        new_value = attempts + 1
        client.table("order_details").update({"mall_ack_attempts": new_value}).eq(
            "id", order_id
        ).execute()
        return new_value
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_mall_repos.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ggotaiorder/mall/credentials_repo.py src/ggotaiorder/mall/order_repo.py tests/test_mall_repos.py
git commit -m "feat(mall): mall_credentials·주문 저장소(Protocol + Supabase 구현)"
```

---

### Task 5: smartstore_client.py — Protocol + bcrypt 전자서명 + 스텁 HTTP

**Files:**
- Create: `backend/src/ggotaiorder/mall/smartstore_client.py`
- Modify: `backend/pyproject.toml` (dependencies 에 `bcrypt` 추가)
- Test: `backend/tests/test_smartstore_signature.py`

**Interfaces:**
- Consumes: `MallCredential`, `SmartStoreOrder`.
- Produces:
  - `SmartStoreClient(Protocol)`: `fetch_new_orders(cred:MallCredential)->tuple[list[SmartStoreOrder], str]`, `confirm_order(cred:MallCredential, product_order_id:str)->None`.
  - `HttpSmartStoreClient` — `_make_signature(client_id:str, client_secret:str, timestamp_ms:int)->str` (bcrypt, 결정적); `fetch_new_orders`/`confirm_order` 는 `NotImplementedError` 스텁.

- [ ] **Step 1: bcrypt 의존성 추가**

`backend/pyproject.toml` 의 `dependencies = [ ... ]` 배열에 한 줄 추가(httpx 항목 근처):

```toml
    "bcrypt>=4.0.0",            # mall.smartstore_client 네이버 커머스API 전자서명(HMAC 아님, bcrypt)
```

그리고 설치: Run: `python -m pip install "bcrypt>=4.0.0"`
Expected: `Successfully installed bcrypt-...`.

- [ ] **Step 2: 실패 테스트 작성**

`backend/tests/test_smartstore_signature.py`:

```python
import base64

import pytest

from ggotaiorder.mall.models import MallCredential
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient

# 유효한 bcrypt salt(네이버 client_secret 은 이 형식). 결정성 검증용 고정값.
_SALT = "$2b$12$R9h/cIPz0gi.URNNX3kh2O"


def test_signature_is_deterministic_for_fixed_inputs():
    c = HttpSmartStoreClient()
    s1 = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    s2 = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    assert s1 == s2


def test_signature_is_base64():
    c = HttpSmartStoreClient()
    sig = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    # base64 디코딩이 예외 없이 되어야 한다(bcrypt 해시의 base64 인코딩).
    assert base64.b64decode(sig)
    assert isinstance(sig, str)


def test_signature_changes_with_timestamp():
    c = HttpSmartStoreClient()
    a = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    b = c._make_signature("client-abc", _SALT, 1_700_000_000_001)
    assert a != b


def test_fetch_and_confirm_are_stubbed():
    c = HttpSmartStoreClient()
    cred = MallCredential(
        shop_key=1, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )
    with pytest.raises(NotImplementedError):
        c.fetch_new_orders(cred)
    with pytest.raises(NotImplementedError):
        c.confirm_order(cred, "PO1")
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_smartstore_signature.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.mall.smartstore_client`.

- [ ] **Step 4: smartstore_client.py 구현**

`backend/src/ggotaiorder/mall/smartstore_client.py`:

```python
"""네이버 커머스API 클라이언트 추상화.

SmartStoreClient(Protocol)로 계약을 고정하고, 실제 HTTP(OAuth2 토큰·주문조회·발주확인)는
client_id/secret 확보 후 구현(라이브 체크리스트). 단, 전자서명(_make_signature)은 결정적이라
지금 구현·단위테스트한다.

전자서명 규격(네이버 커머스API): message = f"{client_id}_{timestamp_ms}" 를 client_secret 을
bcrypt salt 로 하여 해시한 뒤 base64 인코딩. client_secret 이 고정 salt 이므로 결정적이다.
"""

from __future__ import annotations

import base64
import logging
from typing import Protocol

import bcrypt

from ggotaiorder.mall.models import MallCredential, SmartStoreOrder

logger = logging.getLogger(__name__)

# OAuth2 토큰 만료 여유(초). 라이브 구현 시 만료시각까지 프로세스 메모리 캐시.
TOKEN_TTL_MARGIN_SEC = 60


class SmartStoreClient(Protocol):
    """스마트스토어 신규주문 수집·발주확인 계약."""

    def fetch_new_orders(
        self, cred: MallCredential
    ) -> tuple[list[SmartStoreOrder], str]:
        """결제완료(PAYED) 신규주문 목록과 다음 커서(ISO8601)를 반환."""
        ...

    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        """발주확인(승인) — 외부 쓰기."""
        ...


class HttpSmartStoreClient:
    """네이버 커머스API 실구현 (초기 스텁).

    TODO(라이브): OAuth2 토큰(_make_signature 서명, ~3h 캐시)
      → last-changed-statuses(lastChangedFrom=cursor, status=PAYED)
      → product-orders/query 상세 → SmartStoreOrder 매핑
      → confirm_order: 발주확인 엔드포인트 호출.
    실제 HTTP 는 client_id/secret 확보 후. fetch/confirm 은 현재 NotImplementedError.
    """

    def _make_signature(
        self, client_id: str, client_secret: str, timestamp_ms: int
    ) -> str:
        """전자서명 생성: bcrypt(f"{client_id}_{ts}", salt=client_secret) → base64.

        client_secret 은 네이버가 발급한 bcrypt salt 문자열($2a$.../$2b$...)이다.
        salt 가 고정이므로 동일 입력에 동일 서명(결정적) → 단위테스트 가능.
        """
        message = f"{client_id}_{timestamp_ms}".encode("utf-8")
        hashed = bcrypt.hashpw(message, client_secret.encode("utf-8"))
        return base64.b64encode(hashed).decode("utf-8")

    def fetch_new_orders(
        self, cred: MallCredential
    ) -> tuple[list[SmartStoreOrder], str]:
        logger.warning("[STUB] HttpSmartStoreClient.fetch_new_orders — 자격증명 미확보")
        raise NotImplementedError(
            "네이버 커머스API 주문조회는 client_id/secret 확보 후 구현됩니다."
        )

    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        logger.warning("[STUB] HttpSmartStoreClient.confirm_order — 자격증명 미확보")
        raise NotImplementedError(
            "네이버 커머스API 발주확인은 client_id/secret 확보 후 구현됩니다."
        )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_smartstore_signature.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ggotaiorder/mall/smartstore_client.py pyproject.toml tests/test_smartstore_signature.py
git commit -m "feat(mall): SmartStoreClient 계약 + bcrypt 전자서명(결정적) + 스텁 HTTP"
```

---

### Task 6: collector.py — poll_once 수집 오케스트레이션

**Files:**
- Create: `backend/src/ggotaiorder/mall/collector.py`
- Test: `backend/tests/test_mall_collector.py`

**Interfaces:**
- Consumes: `MallCredentialRepository`, `MallOrderRepository`, `SmartStoreClient`, `pipeline.extractor.extract_order`, `pipeline.order_payload.build_order_payload`, `core.crypto.decrypt`, `rpa.singleton_macro.enqueue`, `notifier.sms_sender.send`.
- Produces: `async poll_once(*, cred_repo=None, order_repo=None, client=None, notify=None, extract=None) -> None`. 모듈 수준 `_failure_counts: dict[int,int]`, 상수 `_FAILURE_THRESHOLD=3`. 헬퍼 `_merge_fields`, `_call_record`, `_order_payload`. Task 8(orchestrator)이 `poll_once` 를 스케줄.

- [ ] **Step 1: 실패 테스트 작성 (test_scraper.py 스타일 fakes)**

`backend/tests/test_mall_collector.py`:

```python
import ggotaiorder.mall.collector as collector_mod
from ggotaiorder.mall.collector import poll_once
from ggotaiorder.mall.models import MallCredential, SmartStoreOrder
from ggotaiorder.pipeline.models import OrderExtraction


def _cred(shop_key=1):
    return MallCredential(
        shop_key=shop_key, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )


def _order(product_order_id="PO1"):
    # API 권위값: 상품명·수량·가격·받는사람 등만 채우고 배달/리본/카드/분류는 None.
    return SmartStoreOrder(
        product_order_id=product_order_id,
        raw_text="원문 배송메모",
        memo_text="내일 오후 3시 축하합니다 김철수",
        fields=OrderExtraction(
            product_name="장미꽃다발", quantity=2, price=50000,
            receiver_name="박영희", receiver_phone_number="01011112222",
            delivery_place="서울시 강남구",
        ),
    )


class FakeCredRepo:
    def __init__(self, creds):
        self._creds = creds
        self.cursor_updates = []

    def list_credentials(self, provider):
        return list(self._creds)

    def update_cursor(self, shop_key, provider, cursor):
        self.cursor_updates.append((shop_key, provider, cursor))


class FakeOrderRepo:
    def __init__(self, existing=None):
        self._existing = set(existing or [])
        self.calls = []
        self._next_id = 100

    def order_exists(self, shop_key, product_order_id):
        return (shop_key, product_order_id) in self._existing

    def insert_call_history(self, record):
        self.calls.append(("call", record))
        self._next_id += 1
        return self._next_id

    def insert_order_details(self, payload):
        self.calls.append(("order", payload))
        self._next_id += 1
        return self._next_id


class FakeClient:
    def __init__(self, orders_by_shop=None, raises=False, cursor="C-NEXT"):
        self._orders_by_shop = orders_by_shop or {}
        self._raises = raises
        self._cursor = cursor

    def fetch_new_orders(self, cred):
        if self._raises:
            raise RuntimeError("commerce api failed")
        return list(self._orders_by_shop.get(cred.shop_key, [])), self._cursor

    def confirm_order(self, cred, product_order_id):  # 미사용(수집 경로)
        raise AssertionError("collector 는 confirm 하지 않는다")


def _fake_extract_factory(soft):
    def _extract(text):
        return soft
    return _extract


def _make_notify(notified):
    async def _notify(shop_key):
        notified.append(shop_key)
    return _notify


def _patch_common(monkeypatch):
    enqueued = []

    async def fake_enqueue(order_id):
        enqueued.append(order_id)

    monkeypatch.setattr(collector_mod, "enqueue", fake_enqueue)
    monkeypatch.setattr(collector_mod, "decrypt", lambda enc, key: "plain-secret")
    return enqueued


async def test_new_order_inserts_enqueues_and_updates_cursor(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo()
    client = FakeClient({1: [_order("PO1")]}, cursor="C-NEXT")
    soft = OrderExtraction(
        delivery_at="2026-07-05T15:00:00+09:00", delivery_at_text="내일 오후 3시",
        ribbon_congratulations="축 개업", card_message="축하합니다", sang_divi="생화",
        product_name="무시되어야함", price=999,  # API 권위값이 이겨야 함
    )

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_fake_extract_factory(soft),
    )

    kinds = [c[0] for c in order_repo.calls]
    assert "call" in kinds and "order" in kinds
    call_record = next(c[1] for c in order_repo.calls if c[0] == "call")
    assert call_record["channel_order"] == "쇼핑몰"
    assert call_record["channel_classification"] == "PO1"
    assert call_record["audio_file_name"] == "SMARTSTORE_API"
    assert call_record["stt_text"] == "원문 배송메모"
    order_payload = next(c[1] for c in order_repo.calls if c[0] == "order")
    # 하이브리드: API 권위값 유지
    assert order_payload["product_name"] == "장미꽃다발"
    assert order_payload["price"] == 50000
    assert order_payload["receiver_name"] == "박영희"
    # soft 에서 취한 필드
    assert order_payload["delivery_at"] == "2026-07-05T15:00:00+09:00"
    assert order_payload["ribbon_congratulations"] == "축 개업"
    assert order_payload["card_message"] == "축하합니다"
    assert order_payload["sang_divi"] == "생화"
    # 상태 플래그
    assert order_payload["rpa_status"] == "ready"
    assert order_payload["mall_ack_status"] == "pending"
    assert len(enqueued) == 1
    assert cred_repo.cursor_updates == [(1, "smartstore", "C-NEXT")]


async def test_duplicate_order_skipped(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo(existing={(1, "PO1")})
    client = FakeClient({1: [_order("PO1")]})

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_fake_extract_factory(OrderExtraction()),
    )

    assert order_repo.calls == []
    assert enqueued == []
    # 중복이어도 커서는 갱신(그 shop 처리 완료)
    assert cred_repo.cursor_updates == [(1, "smartstore", "C-NEXT")]


async def test_gemini_failure_still_loads_authoritative_fields(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    cred_repo = FakeCredRepo([_cred()])
    order_repo = FakeOrderRepo()
    client = FakeClient({1: [_order("PO1")]})

    def _boom(text):
        raise RuntimeError("gemini down")

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify([]), extract=_boom,
    )

    order_payload = next(c[1] for c in order_repo.calls if c[0] == "order")
    assert order_payload["product_name"] == "장미꽃다발"  # 유실 없음
    assert order_payload["delivery_at_text"] is None       # soft 없음
    assert len(enqueued) == 1


async def test_three_consecutive_fetch_failures_notify(monkeypatch):
    _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred_repo = FakeCredRepo([_cred()])
    order_repo = FakeOrderRepo()
    client = FakeClient(raises=True)
    notify = _make_notify(notified)
    kw = dict(cred_repo=cred_repo, order_repo=order_repo, client=client,
              notify=notify, extract=_fake_extract_factory(OrderExtraction()))

    await poll_once(**kw)
    await poll_once(**kw)
    assert notified == []
    await poll_once(**kw)
    assert notified == [1]
    # 실패 시 커서 미갱신
    assert cred_repo.cursor_updates == []


async def test_success_resets_failure_counter(monkeypatch):
    _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred = _cred()
    cred_repo = FakeCredRepo([cred])
    order_repo = FakeOrderRepo()
    failing = FakeClient(raises=True)
    ok = FakeClient({1: []})
    notify = _make_notify(notified)
    empty = _fake_extract_factory(OrderExtraction())

    async def run(client):
        await poll_once(cred_repo=cred_repo, order_repo=order_repo, client=client,
                        notify=notify, extract=empty)

    await run(failing)
    await run(failing)
    await run(ok)       # 리셋
    await run(failing)
    await run(failing)
    assert notified == []


async def test_multiple_shops_isolated(monkeypatch):
    enqueued = _patch_common(monkeypatch)
    collector_mod._failure_counts.clear()
    notified = []
    cred_repo = FakeCredRepo([_cred(1), _cred(2)])
    order_repo = FakeOrderRepo()
    # shop 1 은 예외를 던지는 게 아니라, 둘 다 주문 1건씩 정상.
    client = FakeClient({1: [_order("PO1")], 2: [_order("PO2")]})

    await poll_once(
        cred_repo=cred_repo, order_repo=order_repo, client=client,
        notify=_make_notify(notified), extract=_fake_extract_factory(OrderExtraction()),
    )

    order_payloads = [c[1] for c in order_repo.calls if c[0] == "order"]
    assert {p["shop_key"] for p in order_payloads} == {1, 2}
    assert len(enqueued) == 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mall_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.mall.collector`.

- [ ] **Step 3: collector.py 구현**

`backend/src/ggotaiorder/mall/collector.py`:

```python
"""스마트스토어 신규주문 정기 폴링 수집 (오케스트레이션).

커머스API 신규주문(결제완료) → server_call_history + order_details(rpa_status='ready',
mall_ack_status='pending') 직접 적재 → rpa.enqueue. API 정형값을 권위로 두고, 자유텍스트
(메모+옵션)만 Gemini 로 병합(배달일시·리본·카드·상품분류). 연속 3회 수집 실패 시 비상 알림.
실제 커머스API 상호작용은 SmartStoreClient(Protocol) 뒤로 추상화(테스트는 fake 주입).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import decrypt
from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.models import (
    PROVIDER_SMARTSTORE,
    SMARTSTORE_AUDIO_MARKER,
    SMARTSTORE_CHANNEL,
    MallCredential,
    SmartStoreOrder,
)
from ggotaiorder.mall.order_repo import MallOrderRepository, SupabaseMallOrderRepository
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient, SmartStoreClient
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.pipeline.extractor import extract_order
from ggotaiorder.pipeline.models import CallHistory, OrderExtraction
from ggotaiorder.pipeline.order_payload import build_order_payload
from ggotaiorder.rpa.singleton_macro import enqueue

logger = logging.getLogger(__name__)

# 연속 수집 실패가 이 값에 도달하면 비상 알림(scraper 와 동일 관례).
_FAILURE_THRESHOLD = 3

# shop_key -> 연속 실패 횟수
_failure_counts: dict[int, int] = {}

# API 권위값을 덮지 않고 Gemini soft 에서만 취하는 필드(설계서 §4).
_SOFT_FIELDS = (
    "delivery_at",
    "delivery_at_text",
    "ribbon_congratulations",
    "card_message",
    "sang_divi",
)


async def _default_notify(shop_key: int) -> None:
    """기본 비상 알림: notifier 실패 문구로 발송(전용 문구는 후속)."""
    await notifier_send(shop_key, channel=SMARTSTORE_CHANNEL, count=0, outcome="fail")


def _merge_fields(order: SmartStoreOrder, extract) -> OrderExtraction:
    """API 권위값(order.fields) 위에 Gemini soft 필드만 덮어 병합한다.

    soft 추출이 실패해도 정형값은 유효하므로 예외를 흡수하고 API 값만으로 진행한다
    (주문 유실 방지). soft 에서 취하는 건 배달일시·리본·카드·상품분류뿐.
    """
    try:
        soft = extract(order.memo_text)
    except Exception:
        logger.exception("메모 Gemini 추출 실패 — 정형값만으로 진행 po=%s", order.product_order_id)
        return order.fields
    updates = {name: getattr(soft, name) for name in _SOFT_FIELDS}
    return order.fields.model_copy(update=updates)


def _call_record(cred: MallCredential, order: SmartStoreOrder) -> dict:
    now = datetime.now()
    f = order.fields
    return {
        "channel_order": SMARTSTORE_CHANNEL,
        "channel_classification": order.product_order_id,
        "shop_key": cred.shop_key,
        "shop_name": cred.shop_name,
        "customer_name": f.customer_name or "신규",
        "customer_phone_number": f.customer_phone_number or "",
        "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"),
        "duration_seconds": 0,
        "audio_file_name": SMARTSTORE_AUDIO_MARKER,
        "stt_text": order.raw_text,
        "is_order": "Y",
    }


def _order_payload(
    cred: MallCredential, order: SmartStoreOrder, merged: OrderExtraction, call_id: int
) -> dict:
    """공용 build_order_payload 로 조립한 뒤 발주확인 상태(pending)를 덧붙인다."""
    row = CallHistory(
        id=call_id,
        shop_key=cred.shop_key,
        shop_name=cred.shop_name,
        customer_name=merged.customer_name,
        customer_phone_number=merged.customer_phone_number,
        stt_text=order.raw_text,
        audio_file_name=SMARTSTORE_AUDIO_MARKER,
        channel_order=SMARTSTORE_CHANNEL,
    )
    payload = build_order_payload(row, merged)
    payload["mall_ack_status"] = "pending"
    return payload


async def _handle_failure(shop_key: int, notify) -> None:
    count = _failure_counts.get(shop_key, 0) + 1
    _failure_counts[shop_key] = count
    logger.warning("스마트스토어 수집 실패 shop_key=%s (연속 %s회)", shop_key, count)
    if count >= _FAILURE_THRESHOLD:
        await notify(shop_key)
        _failure_counts[shop_key] = 0


async def poll_once(
    *,
    cred_repo: MallCredentialRepository | None = None,
    order_repo: MallOrderRepository | None = None,
    client: SmartStoreClient | None = None,
    notify=None,
    extract=None,
) -> None:
    """스마트스토어를 1회 폴링한다 (APScheduler 가 주기 호출)."""
    cred_repo = cred_repo or SupabaseMallCredentialRepository()
    order_repo = order_repo or SupabaseMallOrderRepository()
    client = client or HttpSmartStoreClient()
    notify = notify or _default_notify
    extract = extract or extract_order

    cfg = load_config()
    creds = await asyncio.to_thread(cred_repo.list_credentials, PROVIDER_SMARTSTORE)

    for cred in creds:
        try:
            cred.client_secret = decrypt(cred.enc_client_secret, cfg.aes_encryption_key)
            orders, next_cursor = await asyncio.to_thread(client.fetch_new_orders, cred)
        except Exception:
            logger.exception("스마트스토어 수집 실패 shop_key=%s", cred.shop_key)
            await _handle_failure(cred.shop_key, notify)
            continue

        _failure_counts[cred.shop_key] = 0

        for order in orders:
            try:
                if await asyncio.to_thread(
                    order_repo.order_exists, cred.shop_key, order.product_order_id
                ):
                    continue
                merged = _merge_fields(order, extract)
                call_id = await asyncio.to_thread(
                    order_repo.insert_call_history, _call_record(cred, order)
                )
                order_id = await asyncio.to_thread(
                    order_repo.insert_order_details,
                    _order_payload(cred, order, merged, call_id),
                )
                await enqueue(order_id)
            except Exception:
                logger.exception(
                    "스마트스토어 주문 적재 실패 shop_key=%s po=%s",
                    cred.shop_key, order.product_order_id,
                )

        await asyncio.to_thread(
            cred_repo.update_cursor, cred.shop_key, PROVIDER_SMARTSTORE, next_cursor
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_mall_collector.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ggotaiorder/mall/collector.py tests/test_mall_collector.py
git commit -m "feat(mall): collector.poll_once 수집 오케스트레이션(하이브리드 병합·실패알림)"
```

---

### Task 7: confirm_scanner.py — RPA 성공분 자동 발주확인

**Files:**
- Create: `backend/src/ggotaiorder/mall/confirm_scanner.py`
- Test: `backend/tests/test_mall_confirm_scanner.py`

**Interfaces:**
- Consumes: `MallOrderRepository`(`list_confirmable`/`increment_ack_attempts`/`mark_ack`), `MallCredentialRepository`(`list_credentials`), `SmartStoreClient`(`confirm_order`), `mall.models.ConfirmTarget`/`SMARTSTORE_AUDIO_MARKER`/`PROVIDER_SMARTSTORE`.
- Produces: `MallConfirmScanner` with `async scan_once(*, order_repo=None, client=None, cred_repo=None) -> int` (처리 시도 건수 반환). 상수 `_ACK_MAX_ATTEMPTS=5`. Task 8(orchestrator)이 스캔을 스케줄.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_mall_confirm_scanner.py`:

```python
from ggotaiorder.mall.confirm_scanner import MallConfirmScanner
from ggotaiorder.mall.models import ConfirmTarget, MallCredential


def _cred(shop_key=1):
    return MallCredential(
        shop_key=shop_key, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )


class FakeCredRepo:
    def __init__(self, creds):
        self._creds = creds

    def list_credentials(self, provider):
        return list(self._creds)


class FakeOrderRepo:
    def __init__(self, targets):
        self._targets = targets
        self.acks = []
        self.increments = []
        self._attempts = {t.order_id: t.ack_attempts for t in targets}

    def list_confirmable(self, provider_marker):
        return list(self._targets)

    def increment_ack_attempts(self, order_id):
        self._attempts[order_id] = self._attempts.get(order_id, 0) + 1
        self.increments.append(order_id)
        return self._attempts[order_id]

    def mark_ack(self, order_id, status):
        self.acks.append((order_id, status))


class FakeClient:
    def __init__(self, raises=False):
        self._raises = raises
        self.confirmed = []

    def confirm_order(self, cred, product_order_id):
        if self._raises:
            raise RuntimeError("confirm failed")
        self.confirmed.append((cred.shop_key, product_order_id))

    def fetch_new_orders(self, cred):  # 미사용
        raise AssertionError("scanner 는 fetch 하지 않는다")


async def test_confirms_success_pending_target():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient()
    scanner = MallConfirmScanner()

    n = await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert n == 1
    assert client.confirmed == [(1, "PO1")]
    assert order_repo.acks == [(10, "confirmed")]


async def test_confirm_failure_retries_until_cap_then_skips():
    # ack_attempts=4 → increment 로 5(=상한) 도달, confirm 예외 → skipped
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=4)])
    client = FakeClient(raises=True)
    scanner = MallConfirmScanner()

    await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert order_repo.acks == [(10, "skipped")]


async def test_confirm_failure_below_cap_no_skip():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=1, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient(raises=True)
    scanner = MallConfirmScanner()

    await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert order_repo.acks == []  # 아직 상한 미만 → 다음 주기 재시도


async def test_missing_cred_shop_skipped():
    order_repo = FakeOrderRepo([ConfirmTarget(order_id=10, shop_key=99, product_order_id="PO1", ack_attempts=0)])
    client = FakeClient()
    scanner = MallConfirmScanner()

    n = await scanner.scan_once(
        order_repo=order_repo, client=client, cred_repo=FakeCredRepo([_cred(1)])
    )

    assert client.confirmed == []
    assert order_repo.acks == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mall_confirm_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: ggotaiorder.mall.confirm_scanner`.

- [ ] **Step 3: confirm_scanner.py 구현**

`backend/src/ggotaiorder/mall/confirm_scanner.py`:

```python
"""RPA 입력 성공분 자동 발주확인 스캐너.

RPA 내부에 결합하지 않고, rpa_status='success' && mall_ack_status='pending' 인
스마트스토어 주문(audio_file_name=SMARTSTORE_API)을 폴링해 커머스API 발주확인을 호출한다.
외부 쓰기(발주확인)는 RPA 성공이 DB 에 확정된 뒤에만 일어난다. 재시도 상한 초과 시
'skipped'로 마킹해 무한 재시도를 막고 수동 확인 대상으로 남긴다.
"""

from __future__ import annotations

import asyncio
import logging

from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.models import PROVIDER_SMARTSTORE, SMARTSTORE_AUDIO_MARKER
from ggotaiorder.mall.order_repo import MallOrderRepository, SupabaseMallOrderRepository
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient, SmartStoreClient

logger = logging.getLogger(__name__)

# 발주확인 최대 재시도 횟수. 초과 시 'skipped'(수동 확인 대상)로 마킹.
_ACK_MAX_ATTEMPTS = 5


class MallConfirmScanner:
    """발주확인 대상을 한 번 스캔해 커머스API 승인을 시도한다.

    order_repo/client/cred_repo 미지정 시 실제 구현을 쓴다(테스트는 fake 주입).
    """

    async def scan_once(
        self,
        *,
        order_repo: MallOrderRepository | None = None,
        client: SmartStoreClient | None = None,
        cred_repo: MallCredentialRepository | None = None,
    ) -> int:
        order_repo = order_repo or SupabaseMallOrderRepository()
        client = client or HttpSmartStoreClient()
        cred_repo = cred_repo or SupabaseMallCredentialRepository()

        targets = await asyncio.to_thread(
            order_repo.list_confirmable, SMARTSTORE_AUDIO_MARKER
        )
        if not targets:
            return 0

        creds = await asyncio.to_thread(cred_repo.list_credentials, PROVIDER_SMARTSTORE)
        creds_by_shop = {c.shop_key: c for c in creds}

        processed = 0
        for t in targets:
            cred = creds_by_shop.get(t.shop_key)
            if cred is None:
                logger.warning("발주확인 자격증명 없음 — 스킵 shop_key=%s", t.shop_key)
                continue
            processed += 1
            attempts = await asyncio.to_thread(
                order_repo.increment_ack_attempts, t.order_id
            )
            try:
                await asyncio.to_thread(client.confirm_order, cred, t.product_order_id)
                await asyncio.to_thread(order_repo.mark_ack, t.order_id, "confirmed")
            except Exception:
                logger.exception("발주확인 실패 order_id=%s", t.order_id)
                if attempts >= _ACK_MAX_ATTEMPTS:
                    await asyncio.to_thread(order_repo.mark_ack, t.order_id, "skipped")
        return processed
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_mall_confirm_scanner.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ggotaiorder/mall/confirm_scanner.py tests/test_mall_confirm_scanner.py
git commit -m "feat(mall): MallConfirmScanner — RPA 성공분 자동 발주확인(재시도 상한)"
```

---

### Task 8: orchestrator 배선 — smartstore_poll + mall_confirm

**Files:**
- Modify: `backend/src/ggotaiorder/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py` (기존 파일에 케이스 추가)

**Interfaces:**
- Consumes: `mall.collector.poll_once`, `mall.confirm_scanner.MallConfirmScanner`.
- Produces: orchestrator 인스턴스 필드 `self._mall_confirm`, 스케줄 메서드 `_scheduled_mall_poll`/`_scheduled_mall_confirm`(둘 다 paused 시 스킵), 상수 `_SMARTSTORE_INTERVAL_MIN=10`, `_MALL_CONFIRM_INTERVAL_MIN=5`. start() 에 잡 4개 등록(poll interval, confirm boot+interval).

- [ ] **Step 1: 실패 테스트 추가 (기존 test_orchestrator.py 하단에)**

```python
import ggotaiorder.orchestrator as orch_mod  # (이미 상단에 있음 — 중복 import 금지, 기존 것 사용)
from ggotaiorder.orchestrator import Orchestrator  # (동일)


def test_smartstore_interval_constants():
    assert orch_mod._SMARTSTORE_INTERVAL_MIN == 10
    assert orch_mod._MALL_CONFIRM_INTERVAL_MIN == 5


async def test_scheduled_mall_poll_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"poll": False}

    async def fake_poll():
        called["poll"] = True

    monkeypatch.setattr(orch_mod, "mall_poll_once", fake_poll)
    await orch._scheduled_mall_poll()
    assert called["poll"] is False


async def test_scheduled_mall_poll_runs_when_active(monkeypatch):
    orch = Orchestrator()
    called = {"poll": False}

    async def fake_poll():
        called["poll"] = True

    monkeypatch.setattr(orch_mod, "mall_poll_once", fake_poll)
    await orch._scheduled_mall_poll()
    assert called["poll"] is True


async def test_scheduled_mall_confirm_skips_when_paused(monkeypatch):
    orch = Orchestrator()
    orch.pause()
    called = {"scan": False}

    async def fake_scan():
        called["scan"] = True
        return 0

    monkeypatch.setattr(orch._mall_confirm, "scan_once", fake_scan)
    await orch._scheduled_mall_confirm()
    assert called["scan"] is False
```

주의: `test_orchestrator.py` 상단에 이미 `import ggotaiorder.orchestrator as orch_mod` 와 `from ggotaiorder.orchestrator import Orchestrator` 가 있으므로 위 블록의 import 두 줄은 추가하지 말고 함수들만 파일 하단에 붙인다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_SMARTSTORE_INTERVAL_MIN'` / `mall_poll_once`.

- [ ] **Step 3: orchestrator.py 수정 — import + 상수**

상단 import 구역(`from ggotaiorder.scraper.crawler import poll_once` 아래)에 추가:

```python
from ggotaiorder.mall.collector import poll_once as mall_poll_once
from ggotaiorder.mall.confirm_scanner import MallConfirmScanner
```

상수 구역(`_RPA_RETRY_INTERVAL_MIN = 5` 아래)에 추가:

```python
# 스마트스토어 커머스API 폴링 주기(분). 후속: setting_info 값으로 동적화.
_SMARTSTORE_INTERVAL_MIN = 10

# 발주확인 스캔 주기(분). RPA 성공분을 이 간격으로 승인한다.
_MALL_CONFIRM_INTERVAL_MIN = 5
```

- [ ] **Step 4: orchestrator.py 수정 — 인스턴스 필드 + 스케줄 메서드**

`__init__` 의 `self._rpa_retry = RpaRetryScanner()` 아래에 추가:

```python
        self._mall_confirm = MallConfirmScanner()
```

`_scheduled_rpa_retry` 메서드 아래(그리고 `_heartbeat` 위)에 추가:

```python
    async def _scheduled_mall_poll(self) -> None:
        """일시정지가 아니면 스마트스토어를 1회 폴링한다."""
        if self._paused:
            logger.debug("paused 상태 — 스마트스토어 폴링 스킵")
            return
        try:
            await mall_poll_once()
        except Exception:
            logger.exception("스마트스토어 폴링 실패(다음 주기에 재시도)")

    async def _scheduled_mall_confirm(self) -> None:
        """일시정지가 아니면 발주확인 스캔을 1회 수행한다."""
        if self._paused:
            logger.debug("paused 상태 — 발주확인 스킵")
            return
        try:
            await self._mall_confirm.scan_once()
        except Exception:
            logger.exception("발주확인 스캔 실패(다음 주기에 재시도)")
```

- [ ] **Step 5: orchestrator.py 수정 — start() 잡 등록**

`start()` 의 rpa_retry 잡 등록 블록 아래(`heartbeat_boot` 위)에 추가:

```python
        # 스마트스토어 커머스API 폴링(신규주문 수집).
        self._scheduler.add_job(
            self._scheduled_mall_poll,
            "interval",
            minutes=_SMARTSTORE_INTERVAL_MIN,
            id="smartstore_poll",
            max_instances=1,
            coalesce=True,
        )
        # 발주확인: 부팅 1회 + 주기적으로(RPA 성공분 승인).
        self._scheduler.add_job(self._scheduled_mall_confirm, "date", id="mall_confirm_boot")
        self._scheduler.add_job(
            self._scheduled_mall_confirm,
            "interval",
            minutes=_MALL_CONFIRM_INTERVAL_MIN,
            id="mall_confirm",
            max_instances=1,
            coalesce=True,
        )
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: 기존 케이스 + 신규 4건 모두 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ggotaiorder/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(mall): 오케스트레이터에 smartstore_poll·mall_confirm 잡 배선"
```

---

### Task 9: seed_mall_credential.py — 초기 자격증명 시드 스크립트

**Files:**
- Create: `backend/scripts/seed_mall_credential.py`

**Interfaces:**
- Consumes: `config.load_config`, `core.crypto.encrypt`, `core.supabase_client.get_client`, `mall.models.PROVIDER_SMARTSTORE`.
- Produces: CLI `python -m scripts.seed_mall_credential --shop 19 --client-id X --client-secret Y [--store-id Z] [--provider smartstore]`. client_secret 은 AES 암호화해 `mall_credentials` upsert.

- [ ] **Step 1: 스크립트 작성**

`backend/scripts/seed_mall_credential.py`:

```python
"""mall_credentials 에 커머스API 자격증명을 시드한다(초기 주입/갱신).

client_secret 은 core.crypto.encrypt 로 iv:ct 포맷 암호화 저장. (shop_key, provider)
UNIQUE 이므로 이미 있으면 갱신(upsert). enable_rpa_shop.py 와 동일한 운영 스크립트 방식.

사용 예:
    python -m scripts.seed_mall_credential --shop 19 \
        --client-id abcd1234 --client-secret '$2a$04$....' --store-id 100200
"""

from __future__ import annotations

import argparse
import sys

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import encrypt
from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import PROVIDER_SMARTSTORE


def main() -> int:
    ap = argparse.ArgumentParser(description="커머스API 자격증명 시드")
    ap.add_argument("--shop", type=int, required=True, help="shop_key (예: 19)")
    ap.add_argument("--client-id", required=True, help="커머스API application id")
    ap.add_argument("--client-secret", required=True, help="application secret(bcrypt salt) — 암호화 저장")
    ap.add_argument("--provider", default=PROVIDER_SMARTSTORE, help="기본 smartstore")
    ap.add_argument("--store-id", default=None, help="스마트스토어 채널/스토어 식별자(extra.store_id)")
    args = ap.parse_args()

    cfg = load_config()
    enc_secret = encrypt(args.client_secret, cfg.aes_encryption_key)
    extra: dict = {}
    if args.store_id:
        extra["store_id"] = args.store_id

    row = {
        "shop_key": args.shop,
        "provider": args.provider,
        "client_id": args.client_id,
        "enc_client_secret": enc_secret,
        "extra": extra,
        "is_active": True,
    }
    client = get_client()
    res = (
        client.table("mall_credentials")
        .upsert(row, on_conflict="shop_key,provider")
        .execute()
    )
    if not res.data:
        print("업서트 응답이 비었습니다 — 실패 가능", file=sys.stderr)
        return 1
    print(f"OK: mall_credentials 시드 shop={args.shop} provider={args.provider}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 임포트/파싱 스모크 검증 (실 DB 접속 없이)**

Run: `python -c "import ast,sys; ast.parse(open('scripts/seed_mall_credential.py',encoding='utf-8').read()); print('syntax-ok')"`
Expected: `syntax-ok`.
Run: `python -m scripts.seed_mall_credential --help`
Expected: usage 출력(인자 파서 정상; DB 호출 전 종료).

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_mall_credential.py
git commit -m "feat(mall): 커머스API 자격증명 시드 스크립트(client_secret AES 암호화 upsert)"
```

---

### Task 10: 전량 회귀 + 브랜치 정리

**Files:** (없음 — 검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `python -m pytest -q`
Expected: 기존 통과분 + 신규(models 4, order_payload 4, repos 2, signature 4, collector 6, confirm 4, orchestrator +4) = 전부 PASS, 실패 0.

- [ ] **Step 2: mall 신규 테스트만 요약 확인**

Run: `python -m pytest tests/test_mall_models.py tests/test_mall_repos.py tests/test_smartstore_signature.py tests/test_mall_collector.py tests/test_mall_confirm_scanner.py tests/test_pipeline_order_payload.py -v`
Expected: 24 passed.

- [ ] **Step 3: 요청 코드리뷰**

`superpowers:requesting-code-review` 로 브랜치 전체 diff 리뷰. Minor 반영 후 재확정.

- [ ] **Step 4: 진행 상태 메모 갱신 (선택)**

`ggotai-current-state` 메모에 스마트스토어 구현 완료·라이브 체크리스트(client_id/secret 발급, seed 실행, HttpSmartStoreClient HTTP 구현)를 남긴다. 상세는 설계서 §10 참조.

---

## 라이브 구동 체크리스트 (코드 외 — 사장님/후속 세션)

설계서 §10 요약. 오프라인 구현 완료 후 실가동에 필요한 것:

1. 네이버 커머스API센터에서 애플리케이션 등록 → client_id/client_secret 발급.
2. `HttpSmartStoreClient` 의 OAuth2 토큰(만료 캐시)·주문조회(last-changed-statuses PAYED → product-orders/query)·발주확인 HTTP 구현. (`_make_signature` 는 완료·테스트됨.)
3. `python -m scripts.seed_mall_credential --shop <k> --client-id .. --client-secret .. --store-id ..` 로 자격증명 주입.
4. 백엔드 재시작 → `smartstore_poll` 1회 → 결제완료 신규주문 수집·중복 skip·order_details 생성 확인.
5. RPA 성공 후 `mall_confirm` → 발주확인 반영 확인. 연속 3회 수집 실패 시 비상 알림 확인.
