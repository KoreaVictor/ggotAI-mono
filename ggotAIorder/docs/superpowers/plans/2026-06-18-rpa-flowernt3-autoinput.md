# FlowerNT3 RPA 자동입력 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 기반 꽃집 관리 프로그램 FlowerNT3에 주문을 Playwright로 자동 입력·등록하고 `rpa_status`를 `success`로 마킹한다(꽃집별 프로그램은 setting_info로 분기).

**Architecture:** 기존 `ProgramAutomator`(Protocol)/`singleton_macro`/3-state 백업 흐름은 유지하고, (a) 순수 매핑 모듈, (b) 샵 설정 로딩, (c) 어댑터 팩토리, (d) Playwright 기반 `FlowerNt3Automator`를 추가한다. 자동화는 전용 프로필 Chrome에 CDP로 붙었다 떼는 방식(sync Playwright를 `asyncio.to_thread` 워커에서 호출).

**Tech Stack:** Python 3.13, Playwright(sync, `channel="chrome"`), Supabase(Postgres RPC), pytest(asyncio_mode=auto), React/TypeScript(프론트 설정), `core.crypto`(AES-256-CBC).

설계 근거: `docs/superpowers/specs/2026-06-18-rpa-flowernt3-autoinput-design.md`

---

## File Structure

**생성:**
- `backend/src/ggotaiorder/rpa/flowernt3/__init__.py` — 서브패키지
- `backend/src/ggotaiorder/rpa/flowernt3/mapping.py` — 순수 매핑(필드/채널/가격/날짜). 브라우저 불요.
- `backend/src/ggotaiorder/rpa/flowernt3/automator.py` — `FlowerNt3Automator`(Playwright sync)
- `backend/src/ggotaiorder/rpa/program_settings.py` — setting_info → `RpaProgramSettings`(비번 복호)
- `backend/src/ggotaiorder/rpa/adapters.py` — `ManualOnlyAutomator`, `RoseWebAutomator`(스텁)
- `backend/src/ggotaiorder/rpa/factory.py` — `build_automator(settings)`
- `backend/tests/test_rpa_flowernt3_mapping.py`
- `backend/tests/test_rpa_program_settings.py`
- `backend/tests/test_rpa_factory.py`
- `backend/tests/test_rpa_flowernt3_fill.py` — Playwright 통합(크롬 없으면 skip)
- `backend/tests/fixtures/flowernt3_order_form.html` — 폼 스냅샷(통합테스트용)
- `C:\ggotAI\supabase\migrations\20260618000100_rpa_program_settings.sql`

**수정:**
- `backend/pyproject.toml` — `playwright`, `greenlet==3.1.1` 의존성
- `backend/src/ggotaiorder/config.py` — `rpa_profile_dir`, `flowernt_debug_port`
- `backend/src/ggotaiorder/rpa/singleton_macro.py` — 기본 automator를 팩토리로
- `frontend/src/settings/client.ts` — RPA 필드 + 비번 인자
- `frontend/src/views/settings.tsx` — RPA 설정 섹션
- `frontend/src/types/database.ts` / `db.ts` — 타입 동기화

---

## Task 1: 의존성 + config 항목

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/ggotaiorder/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: 의존성 추가**

`backend/pyproject.toml`의 `dependencies` 리스트에 두 줄 추가(기존 `pywin32` 줄 아래):

```toml
    "playwright>=1.60.0",        # rpa.flowernt3 (웹 관리 프로그램 자동입력)
    "greenlet==3.1.1",           # playwright sync API 의존 — 3.5.x는 이 환경서 DLL 로드 실패
```

- [ ] **Step 2: 설치 및 import 검증**

Run: `cd backend && python -m pip install -e . && python -c "from playwright.sync_api import sync_playwright; print('OK')"`
Expected: `OK` (이미 설치되어 있을 수 있음 — 그래도 통과해야 함)

- [ ] **Step 3: config 실패 테스트 추가**

`backend/tests/test_config.py` 끝에 추가:

```python
def test_rpa_profile_dir_and_debug_port_defaults():
    from pathlib import Path
    env = {
        "SUPABASE_URL": "u", "SUPABASE_ANON_KEY": "a",
        "SUPABASE_SERVICE_ROLE_KEY": "s",
        "AES_ENCRYPTION_KEY": "0" * 64, "GEMINI_API_KEY": "g", "SHOP_KEY": "19",
    }
    from ggotaiorder.config import load_config
    cfg = load_config(env)
    assert isinstance(cfg.rpa_profile_dir, Path)
    assert cfg.flowernt_debug_port == 9222


def test_rpa_profile_dir_and_port_from_env():
    env = {
        "SUPABASE_URL": "u", "SUPABASE_ANON_KEY": "a",
        "SUPABASE_SERVICE_ROLE_KEY": "s",
        "AES_ENCRYPTION_KEY": "0" * 64, "GEMINI_API_KEY": "g", "SHOP_KEY": "19",
        "RPA_PROFILE_DIR": r"C:\tmp\prof", "RPA_DEBUG_PORT": "9333",
    }
    from ggotaiorder.config import load_config
    cfg = load_config(env)
    assert str(cfg.rpa_profile_dir).endswith("prof")
    assert cfg.flowernt_debug_port == 9333
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_config.py -k rpa_profile -v`
Expected: FAIL (`Config` 에 `rpa_profile_dir` 없음)

- [ ] **Step 5: config 구현**

`backend/src/ggotaiorder/config.py`의 `Config` 데이터클래스에 필드 추가:

```python
    rpa_backup_dir: Path
    rpa_profile_dir: Path
    flowernt_debug_port: int
```

`load_config` 의 `return Config(...)` 직전에 추가:

```python
    profile_dir = env.get("RPA_PROFILE_DIR")
    rpa_profile_dir = (
        Path(profile_dir) if profile_dir else Path(r"C:\ggotAI\rpa_profile")
    )
    try:
        flowernt_debug_port = int(env.get("RPA_DEBUG_PORT") or 9222)
    except ValueError:
        raise ConfigError("RPA_DEBUG_PORT 는 정수여야 합니다.")
```

그리고 `return Config(...)` 에 인자 추가:

```python
        rpa_backup_dir=rpa_backup_dir,
        rpa_profile_dir=rpa_profile_dir,
        flowernt_debug_port=flowernt_debug_port,
    )
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS (전체)

- [ ] **Step 7: 커밋**

```bash
git add backend/pyproject.toml backend/src/ggotaiorder/config.py backend/tests/test_config.py
git commit -m "feat(rpa): playwright 의존성 + rpa_profile_dir/debug_port config"
```

---

## Task 2: 순수 매핑 모듈 (RpaOrder → FlowerNT3 폼)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/flowernt3/__init__.py`
- Create: `backend/src/ggotaiorder/rpa/flowernt3/mapping.py`
- Test: `backend/tests/test_rpa_flowernt3_mapping.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_rpa_flowernt3_mapping.py`:

```python
from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.flowernt3 import mapping as m


def _order(**kw):
    base = dict(
        order_detail_id=1, shop_key=19, shop_name="테스트꽃집", channel="전화",
        customer_name="홍길동", customer_phone_number="01011112222",
        product_name="장미 꽃다발", quantity=1, price=50000,
        delivery_at="2026-06-20T15:30:00", delivery_place="서울시 강남구 1-2",
        receiver_name="김영희", receiver_phone_number="01033334444",
        ribbon_sender="홍길동", ribbon_congratulations="축 개업",
        card_message="축하합니다", delivery_at_text="모레 오후 3시 반",
    )
    base.update(kw)
    return RpaOrder(**base)


def test_channel_to_order_divi_known():
    assert m.channel_to_order_divi("전화") == "전화"
    assert m.channel_to_order_divi("가게전화") == "전화"
    assert m.channel_to_order_divi("핸드폰") == "전화"
    assert m.channel_to_order_divi("가게음성") == "매장판매"
    assert m.channel_to_order_divi("쇼핑몰") == "홈페이지"
    assert m.channel_to_order_divi("인터라넷") == "프로그램간"


def test_channel_to_order_divi_unknown_is_etc():
    assert m.channel_to_order_divi("") == "기타"
    assert m.channel_to_order_divi("알수없음") == "기타"


def test_normalize_price_digits_only():
    assert m.normalize_price(50000) == "50000"
    assert m.normalize_price("50,000원") == "50000"
    assert m.normalize_price(None) == ""


def test_split_delivery_datetime():
    assert m.split_delivery_datetime("2026-06-20T15:30:00") == ("2026-06-20", "15:30")
    assert m.split_delivery_datetime("2026-06-20 09:05") == ("2026-06-20", "09:05")
    assert m.split_delivery_datetime("2026-06-20") == ("2026-06-20", "")
    assert m.split_delivery_datetime(None) == ("", "")


def test_order_to_fields():
    fields = m.order_to_fields(_order())
    assert fields["customer_name"] == "홍길동"
    assert fields["customer_hp"] == "01011112222"
    assert fields["sang_name"] == "장미 꽃다발"
    assert fields["sang_money"] == "50000"
    assert fields["receive_name"] == "김영희"
    assert fields["receive_hp"] == "01033334444"
    assert fields["receive_address1"] == "서울시 강남구 1-2"
    assert fields["hope_date"] == "2026-06-20"
    assert fields["hope_time"] == "15:30"
    assert fields["msg_text"] == "축하합니다"
    assert "축 개업" in fields["event_txt"]
    assert "홍길동" in fields["event_txt"]


def test_order_to_fields_omits_empty_optional():
    fields = m.order_to_fields(_order(
        delivery_at=None, delivery_place=None, receiver_name=None,
        receiver_phone_number=None, ribbon_sender=None,
        ribbon_congratulations=None, card_message=None,
    ))
    assert fields["receive_name"] == ""
    assert fields["event_txt"] == ""
    assert fields["msg_text"] == ""
    assert "hope_date" not in fields
    assert "hope_time" not in fields
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_rpa_flowernt3_mapping.py -v`
Expected: FAIL (`ModuleNotFoundError: ggotaiorder.rpa.flowernt3`)

- [ ] **Step 3: 패키지 + 매핑 구현**

`backend/src/ggotaiorder/rpa/flowernt3/__init__.py`:

```python
"""FlowerNT3(웹) 관리 프로그램 RPA 어댑터 패키지."""
```

`backend/src/ggotaiorder/rpa/flowernt3/mapping.py`:

```python
"""RpaOrder → FlowerNT3 주문폼(order_form2) 순수 매핑.

브라우저 의존성이 없어 단위테스트로 전부 검증한다. 실제 입력은 automator가
이 dict를 받아 DOM에 채운다.
"""

from __future__ import annotations

import re

from ggotaiorder.rpa.models import RpaOrder

# channel(server_call_history.channel_order) → FlowerNT3 주문구분(order_divi) 라벨.
# 정확한 라디오 라벨/순서는 라이브 폼에서 확정하되, 매핑 의도는 고정.
CHANNEL_TO_ORDER_DIVI = {
    "전화": "전화",
    "가게전화": "전화",
    "핸드폰": "전화",
    "가게음성": "매장판매",
    "쇼핑몰": "홈페이지",
    "인터라넷": "프로그램간",
}
DEFAULT_ORDER_DIVI = "기타"


def channel_to_order_divi(channel: str | None) -> str:
    return CHANNEL_TO_ORDER_DIVI.get((channel or "").strip(), DEFAULT_ORDER_DIVI)


def normalize_price(price: object) -> str:
    """숫자만 남긴 문자열. None/빈값은 ''."""
    if price is None:
        return ""
    return re.sub(r"[^0-9]", "", str(price))


def split_delivery_datetime(delivery_at: str | None) -> tuple[str, str]:
    """ISO/공백구분 일시를 (YYYY-MM-DD, HH:MM)로 분리. 시각 없으면 ('date','')."""
    if not delivery_at:
        return ("", "")
    s = str(delivery_at).strip().replace("T", " ")
    parts = s.split(" ", 1)
    date = parts[0]
    time = ""
    if len(parts) > 1 and parts[1].strip():
        hm = parts[1].strip().split(":")
        if len(hm) >= 2:
            time = f"{hm[0].zfill(2)}:{hm[1].zfill(2)}"
    return (date, time)


def _ribbon_text(order: RpaOrder) -> str:
    """경조문구 + 보내는분을 합쳐 event_txt 한 칸에. 둘 다 없으면 ''."""
    parts = [p for p in (order.ribbon_congratulations, order.ribbon_sender) if p]
    return "  ".join(parts)


def order_to_fields(order: RpaOrder) -> dict[str, str]:
    """order_form2 의 text/textarea name → 값. (radio order_divi는 별도)"""
    fields: dict[str, str] = {
        "customer_name": order.customer_name or "",
        "customer_hp": order.customer_phone_number or "",
        "sang_name": order.product_name or "",
        "sang_money": normalize_price(order.price),
        "receive_name": order.receiver_name or "",
        "receive_hp": order.receiver_phone_number or "",
        "receive_address1": order.delivery_place or "",
        "event_txt": _ribbon_text(order),
        "msg_text": order.card_message or "",
    }
    date, time = split_delivery_datetime(order.delivery_at)
    if date:
        fields["hope_date"] = date
    if time:
        fields["hope_time"] = time
    return fields
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_rpa_flowernt3_mapping.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/flowernt3/__init__.py backend/src/ggotaiorder/rpa/flowernt3/mapping.py backend/tests/test_rpa_flowernt3_mapping.py
git commit -m "feat(rpa): FlowerNT3 순수 필드/채널 매핑 모듈"
```

---

## Task 3: 샵 RPA 설정 로딩 (program_settings)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/program_settings.py`
- Test: `backend/tests/test_rpa_program_settings.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_rpa_program_settings.py`:

```python
from ggotaiorder.core.crypto import encrypt
from ggotaiorder.rpa.program_settings import RpaProgramSettings, parse_settings_row

KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_parse_full_row_decrypts_password():
    row = {
        "rpa_program_type": "flowernt",
        "rpa_program_url": "https://www.flowernt.com",
        "rpa_login_id": "shop01",
        "rpa_login_password": encrypt("pw123!", KEY),
        "rpa_enabled": "Y",
        "rpa_auto_submit": "Y",
    }
    s = parse_settings_row(row, KEY)
    assert s == RpaProgramSettings(
        program_type="flowernt", url="https://www.flowernt.com",
        login_id="shop01", login_password="pw123!",
        enabled=True, auto_submit=True,
    )


def test_parse_disabled_and_no_password():
    row = {
        "rpa_program_type": "", "rpa_program_url": None, "rpa_login_id": None,
        "rpa_login_password": None, "rpa_enabled": "N", "rpa_auto_submit": "N",
    }
    s = parse_settings_row(row, KEY)
    assert s.enabled is False
    assert s.auto_submit is False
    assert s.login_password is None


def test_parse_none_row():
    assert parse_settings_row(None, KEY) is None


def test_parse_bad_password_is_none_not_crash():
    row = {"rpa_program_type": "flowernt", "rpa_enabled": "Y",
           "rpa_login_password": "not-a-valid-blob"}
    s = parse_settings_row(row, KEY)
    assert s.login_password is None  # 복호 실패는 조용히 None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_rpa_program_settings.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`backend/src/ggotaiorder/rpa/program_settings.py`:

```python
"""setting_info → RpaProgramSettings 로딩(비밀번호 복호는 백엔드 내부에서만)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ggotaiorder.core.crypto import decrypt
from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RpaProgramSettings:
    program_type: str          # 'flowernt' | 'roseweb' | 'etc' | ''
    url: str | None
    login_id: str | None
    login_password: str | None  # 복호된 평문(백엔드 내부)
    enabled: bool
    auto_submit: bool


def parse_settings_row(row: dict | None, aes_key: str) -> RpaProgramSettings | None:
    if not row:
        return None
    pw_blob = row.get("rpa_login_password")
    login_password = None
    if pw_blob:
        try:
            login_password = decrypt(pw_blob, aes_key)
        except Exception:
            logger.warning("rpa_login_password 복호 실패 — 자격증명 없음으로 처리")
            login_password = None
    return RpaProgramSettings(
        program_type=(row.get("rpa_program_type") or "").strip(),
        url=row.get("rpa_program_url") or None,
        login_id=row.get("rpa_login_id") or None,
        login_password=login_password,
        enabled=(row.get("rpa_enabled") or "N") == "Y",
        auto_submit=(row.get("rpa_auto_submit") or "Y") == "Y",
    )


def load_program_settings(shop_key: int, aes_key: str) -> RpaProgramSettings | None:
    """setting_info 한 행을 읽어 RpaProgramSettings로 변환."""
    res = (
        get_client()
        .table("setting_info")
        .select(
            "rpa_program_type, rpa_program_url, rpa_login_id, "
            "rpa_login_password, rpa_enabled, rpa_auto_submit"
        )
        .eq("shop_key", shop_key)
        .limit(1)
        .execute()
    )
    row = res.data[0] if res.data else None
    return parse_settings_row(row, aes_key)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_rpa_program_settings.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/program_settings.py backend/tests/test_rpa_program_settings.py
git commit -m "feat(rpa): 샵 RPA 프로그램 설정 로딩(setting_info, 비번 복호)"
```

---

## Task 4: 어댑터 팩토리 + ManualOnly/RoseWeb 스텁

**Files:**
- Create: `backend/src/ggotaiorder/rpa/adapters.py`
- Create: `backend/src/ggotaiorder/rpa/factory.py`
- Test: `backend/tests/test_rpa_factory.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_rpa_factory.py`:

```python
from ggotaiorder.rpa.adapters import ManualOnlyAutomator, RoseWebAutomator
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings


def _s(**kw):
    base = dict(program_type="flowernt", url="https://www.flowernt.com",
                login_id="id", login_password="pw", enabled=True, auto_submit=True)
    base.update(kw)
    return RpaProgramSettings(**base)


def test_none_settings_is_manual_only():
    a = build_automator(None, debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)
    assert a.is_program_running() is False


def test_disabled_is_manual_only():
    a = build_automator(_s(enabled=False), debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)


def test_flowernt_builds_flowernt_automator():
    a = build_automator(_s(program_type="flowernt"), debug_port=9222)
    assert isinstance(a, FlowerNt3Automator)


def test_roseweb_is_stub_manual():
    a = build_automator(_s(program_type="roseweb"), debug_port=9222)
    assert isinstance(a, RoseWebAutomator)
    assert a.is_program_running() is False


def test_unknown_type_is_manual_only():
    a = build_automator(_s(program_type="etc"), debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_rpa_factory.py -v`
Expected: FAIL (`ModuleNotFoundError: ggotaiorder.rpa.adapters`)

- [ ] **Step 3: 어댑터 스텁 구현**

`backend/src/ggotaiorder/rpa/adapters.py`:

```python
"""RPA 백업 폴백 어댑터: 항상 미구동으로 보고해 'manual' 백업 경로로 흐른다."""

from __future__ import annotations

import logging

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class ManualOnlyAutomator:
    """RPA 비활성/미지원 프로그램용. is_program_running 항상 False."""

    def is_program_running(self) -> bool:
        return False

    def input_order(self, order: RpaOrder) -> None:  # pragma: no cover - 호출 안 됨
        raise RuntimeError("ManualOnlyAutomator.input_order 는 호출되면 안 됩니다.")


class RoseWebAutomator:
    """Roseweb 어댑터(스텁). 실제 입력 로직은 후속 과제 — 현재는 백업 폴백."""

    def __init__(self, url: str | None, login_id: str | None,
                 login_password: str | None, debug_port: int) -> None:
        self._url = url
        self._login_id = login_id
        self._login_password = login_password
        self._debug_port = debug_port

    def is_program_running(self) -> bool:
        logger.info("RoseWebAutomator 미구현 — 백업(manual) 경로로 처리")
        return False

    def input_order(self, order: RpaOrder) -> None:  # pragma: no cover
        raise NotImplementedError("Roseweb 자동입력은 후속 구현 예정입니다.")
```

`backend/src/ggotaiorder/rpa/factory.py`:

```python
"""샵 RPA 설정으로부터 알맞은 ProgramAutomator를 생성한다."""

from __future__ import annotations

from ggotaiorder.rpa.adapters import ManualOnlyAutomator, RoseWebAutomator
from ggotaiorder.rpa.automator import ProgramAutomator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings


def build_automator(
    settings: RpaProgramSettings | None, *, debug_port: int
) -> ProgramAutomator:
    if settings is None or not settings.enabled:
        return ManualOnlyAutomator()
    if settings.program_type == "flowernt":
        return FlowerNt3Automator(
            url=settings.url,
            login_id=settings.login_id,
            login_password=settings.login_password,
            auto_submit=settings.auto_submit,
            debug_port=debug_port,
        )
    if settings.program_type == "roseweb":
        return RoseWebAutomator(
            url=settings.url, login_id=settings.login_id,
            login_password=settings.login_password, debug_port=debug_port,
        )
    return ManualOnlyAutomator()
```

> 이 단계는 `FlowerNt3Automator` 가 import 가능해야 한다. Task 5에서 본구현 전, **임시로** 최소 골격을 먼저 만든다(다음 스텝).

- [ ] **Step 4: FlowerNt3Automator 최소 골격(임시)**

`backend/src/ggotaiorder/rpa/flowernt3/automator.py` (Task 5에서 본구현으로 교체):

```python
"""FlowerNt3Automator — Task 5에서 Playwright 본구현. 우선 import 가능한 골격."""

from __future__ import annotations

from ggotaiorder.rpa.models import RpaOrder


class FlowerNt3Automator:
    def __init__(self, *, url, login_id, login_password, auto_submit, debug_port):
        self.url = url
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port

    def is_program_running(self) -> bool:
        return False

    def input_order(self, order: RpaOrder) -> None:
        raise NotImplementedError
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_rpa_factory.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/adapters.py backend/src/ggotaiorder/rpa/factory.py backend/src/ggotaiorder/rpa/flowernt3/automator.py backend/tests/test_rpa_factory.py
git commit -m "feat(rpa): 어댑터 팩토리 + ManualOnly/RoseWeb 스텁"
```

---

## Task 5: FlowerNt3Automator 본구현 (Playwright)

**Files:**
- Modify: `backend/src/ggotaiorder/rpa/flowernt3/automator.py`
- Create: `backend/tests/fixtures/flowernt3_order_form.html`
- Test: `backend/tests/test_rpa_flowernt3_fill.py`

이 태스크는 실 브라우저가 필요하다. 입력 로직을 **`fill_order_form(frame, order)`** 순수-ish 함수로 분리해
로컬 HTML 스냅샷에 대해 검증한다(라이브/실주문 없음). 세션·로그인 코드는 라이브에서 최종 점검(Task 8).

- [ ] **Step 1: 폼 스냅샷 픽스처 작성**

`backend/tests/fixtures/flowernt3_order_form.html` — order_form2의 핵심 칸만 재현(실 name 사용):

```html
<!doctype html><html><head><meta charset="utf-8"></head><body>
<form name="order_form2">
  <label><input type="radio" name="order_divi" value="A">전화</label>
  <label><input type="radio" name="order_divi" value="B">매장판매</label>
  <label><input type="radio" name="order_divi" value="C">홈페이지</label>
  <label><input type="radio" name="order_divi" value="D">프로그램간</label>
  <label><input type="radio" name="order_divi" value="E">기타</label>
  <input type="text" name="customer_name">
  <input type="text" name="customer_hp">
  <input type="text" name="sang_name">
  <input type="text" name="sang_money">
  <input type="text" name="hope_date">
  <input type="text" name="hope_time">
  <input type="text" name="receive_name">
  <input type="text" name="receive_hp">
  <input type="text" name="receive_address1">
  <input type="text" name="event_txt">
  <textarea name="msg_text"></textarea>
  <script>function submit_reg(){ document.title = "REG_CALLED"; }</script>
</form></body></html>
```

- [ ] **Step 2: 실패 통합테스트 작성**

`backend/tests/test_rpa_flowernt3_fill.py`:

```python
import shutil
from pathlib import Path

import pytest

from ggotaiorder.rpa.models import RpaOrder

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _chrome_ok() -> bool:
    return any(Path(p).exists() for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ])


pytestmark = pytest.mark.skipif(not _chrome_ok(), reason="시스템 Chrome 필요")

FIXTURE = Path(__file__).parent / "fixtures" / "flowernt3_order_form.html"


def _order():
    return RpaOrder(
        order_detail_id=1, shop_key=19, shop_name="t", channel="쇼핑몰",
        customer_name="홍길동", customer_phone_number="01011112222",
        product_name="장미", quantity=1, price=50000,
        delivery_at="2026-06-20T15:30:00", delivery_place="서울 강남",
        receiver_name="김영희", receiver_phone_number="01033334444",
        ribbon_sender="홍길동", ribbon_congratulations="축 개업",
        card_message="축하", delivery_at_text=None,
    )


def test_fill_order_form_populates_fields():
    from ggotaiorder.rpa.flowernt3.automator import fill_order_form
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto(FIXTURE.as_uri())
        fill_order_form(page.main_frame, _order(), auto_submit=True)
        val = lambda n: page.eval_on_selector(f"[name={n}]", "e=>e.value")
        assert val("customer_name") == "홍길동"
        assert val("sang_money") == "50000"
        assert val("hope_date") == "2026-06-20"
        assert val("hope_time") == "15:30"
        assert val("receive_address1") == "서울 강남"
        # 채널 '쇼핑몰' → '홈페이지' 라디오 선택
        checked = page.eval_on_selector(
            "input[name=order_divi]:checked", "e=>e.parentElement.innerText.trim()")
        assert "홈페이지" in checked
        # auto_submit=True 면 submit_reg() 호출됨
        assert page.title() == "REG_CALLED"
        browser.close()
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_rpa_flowernt3_fill.py -v`
Expected: FAIL (`ImportError: cannot import name 'fill_order_form'`) — Chrome 없으면 SKIP

- [ ] **Step 4: automator 본구현**

`backend/src/ggotaiorder/rpa/flowernt3/automator.py` 전체 교체:

```python
"""FlowerNt3Automator — 전용 프로필 Chrome(CDP)에 붙어 주문폼을 채우고 등록한다.

singleton_macro가 asyncio.to_thread로 동기 호출하므로 sync Playwright를 쓰며,
매 호출마다 connect_over_cdp로 연결→작업→해제를 완결한다(스레드 귀속 회피).
"""

from __future__ import annotations

import logging

from ggotaiorder.rpa.flowernt3 import mapping
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

ORDER_FRAME_MARK = "order/order3.asp"
ORDER_PATH = "/order/order3.asp"


def _cdp_url(debug_port: int) -> str:
    return f"http://localhost:{debug_port}"


def fill_order_form(frame, order: RpaOrder, *, auto_submit: bool) -> None:
    """order_form2 프레임에 주문을 채우고, auto_submit이면 등록까지 실행한다."""
    # 1) 주문구분 라디오: 라벨 텍스트로 선택(인코딩 안전)
    target = mapping.channel_to_order_divi(order.channel)
    frame.evaluate(
        """(label) => {
            const radios = Array.from(document.getElementsByName('order_divi'));
            for (const r of radios) {
                const t = (r.parentElement?.innerText || '').trim();
                if (t.includes(label)) { r.click(); return true; }
            }
            return false;
        }""",
        target,
    )
    # 2) text/textarea 채움
    for name, value in mapping.order_to_fields(order).items():
        if value == "":
            continue
        sel = f"[name={name}]"
        el = frame.query_selector(sel)
        if el is None:
            logger.debug("FlowerNT3 필드 없음(스킵): %s", name)
            continue
        el.fill(value)
    # 3) 등록
    if auto_submit:
        frame.evaluate("() => { if (typeof submit_reg === 'function') submit_reg(); }")


class FlowerNt3Automator:
    def __init__(self, *, url, login_id, login_password, auto_submit, debug_port):
        self.url = url or "https://www.flowernt.com"
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port

    # --- 세션 ---
    def _connect(self, p):
        return p.chromium.connect_over_cdp(_cdp_url(self.debug_port))

    def _logged_in(self, page) -> bool:
        """로그인 페이지로 튕기지 않으면 로그인 상태로 간주."""
        url = (page.url or "").lower()
        return "login" not in url and "flowernt.com" in url

    def _order_frame(self, page):
        for f in page.frames:
            if ORDER_FRAME_MARK in (f.url or ""):
                return f
        return None

    def is_program_running(self) -> bool:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = self._connect(p)
                ctx = browser.contexts[0] if browser.contexts else None
                if ctx is None or not ctx.pages:
                    page = (ctx or browser.new_context()).new_page()
                else:
                    page = ctx.pages[0]
                if not self._logged_in(page):
                    ok = self._try_login(page)
                    browser.close()
                    return ok
                browser.close()
                return True
        except Exception:
            logger.info("FlowerNT3 CDP 연결 실패 — 미구동으로 처리(백업)")
            return False

    def _try_login(self, page) -> bool:
        """저장된 자격증명으로 로그인 시도. 실패/자격증명 없음이면 False."""
        if not (self.login_id and self.login_password):
            return False
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            # FlowerNT 로그인 폼 필드명은 라이브에서 확정(Task 8). 가능한 후보 시도.
            page.fill("input[name=member_id], input[name=user_id], input[name=id]",
                      self.login_id)
            page.fill("input[type=password]", self.login_password)
            page.keyboard.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            return self._logged_in(page)
        except Exception:
            logger.warning("FlowerNT3 자동 로그인 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = self._connect(p)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            # 주문입력 프레임을 신규폼으로 새로고침
            frame = self._order_frame(page)
            if frame is not None:
                frame.goto(self.url.rstrip("/") + ORDER_PATH,
                           wait_until="domcontentloaded")
                frame = self._order_frame(page)
            else:
                page.goto(self.url.rstrip("/") + ORDER_PATH,
                          wait_until="domcontentloaded")
                frame = self._order_frame(page) or page.main_frame
            fill_order_form(frame, order, auto_submit=self.auto_submit)
            page.wait_for_timeout(800)  # 등록 처리 대기
            browser.close()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_rpa_flowernt3_fill.py -v`
Expected: PASS (Chrome 있으면) / SKIP (없으면)

- [ ] **Step 6: 매핑·팩토리 회귀 확인**

Run: `cd backend && python -m pytest tests/test_rpa_flowernt3_mapping.py tests/test_rpa_factory.py -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/flowernt3/automator.py backend/tests/test_rpa_flowernt3_fill.py backend/tests/fixtures/flowernt3_order_form.html
git commit -m "feat(rpa): FlowerNt3Automator 본구현(CDP 연결+폼 입력+등록)"
```

---

## Task 6: singleton_macro 배선 (팩토리 사용)

**Files:**
- Modify: `backend/src/ggotaiorder/rpa/singleton_macro.py`
- Test: `backend/tests/test_rpa_singleton.py`

기존 테스트는 `automator`/`backup`/`notify`를 주입하므로 변경 없이 통과해야 한다.
기본값(주입 없을 때)만 팩토리 결과로 바꾼다.

- [ ] **Step 1: 기본 automator가 설정에서 만들어지는 테스트 추가**

`backend/tests/test_rpa_singleton.py` 끝에 추가:

```python
async def test_default_automator_built_from_settings(monkeypatch):
    import ggotaiorder.rpa.singleton_macro as sm
    from ggotaiorder.rpa.adapters import ManualOnlyAutomator

    captured = {}

    def fake_load(shop_key, aes_key):
        captured["shop_key"] = shop_key
        return None  # → ManualOnly

    built = {}
    real_build = sm.build_automator

    def fake_build(settings, *, debug_port):
        a = real_build(settings, debug_port=debug_port)
        built["type"] = type(a).__name__
        return a

    monkeypatch.setattr(sm, "load_program_settings", fake_load)
    monkeypatch.setattr(sm, "build_automator", fake_build)

    repo = FakeRepo(_order())
    backup = FakeBackup()
    calls, notify = _spy_notify()
    # automator 미주입 → 팩토리 경로
    await sm.enqueue(7, repo=repo, backup=backup, notify=notify)

    assert built["type"] == "ManualOnlyAutomator"
    assert repo.statuses == [(7, "manual")]
    assert backup.written == [7]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/test_rpa_singleton.py -k default_automator -v`
Expected: FAIL (`singleton_macro` 에 `load_program_settings`/`build_automator` 없음)

- [ ] **Step 3: singleton_macro 수정**

`backend/src/ggotaiorder/rpa/singleton_macro.py` import 교체 및 기본 automator 변경.

import 블록에서 `from ggotaiorder.rpa.automator import ProgramAutomator, WindowsProgramAutomator` 를:

```python
from ggotaiorder.rpa.automator import ProgramAutomator
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.program_settings import load_program_settings
```

`enqueue` 안의 기본값 라인 `automator = automator or WindowsProgramAutomator()` 를:

```python
    cfg = load_config()
    repo = repo or SupabaseRpaRepository()
    if automator is None:
        settings = await asyncio.to_thread(
            load_program_settings, cfg.shop_key, cfg.aes_encryption_key
        )
        automator = build_automator(settings, debug_port=cfg.flowernt_debug_port)
    backup = backup or BackupWriter(cfg.rpa_backup_dir)
    notify = notify or _default_notify
```

> 주의: 기존 코드의 `repo = repo or ...`, `backup = backup or BackupWriter(load_config()...)`,
> `automator = automator or ...` 세 줄을 위 블록으로 통합 교체한다(`load_config()` 1회 호출).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/test_rpa_singleton.py -v`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/singleton_macro.py backend/tests/test_rpa_singleton.py
git commit -m "feat(rpa): enqueue 기본 automator를 샵 설정 팩토리로 배선"
```

---

## Task 7: DB 마이그레이션 + get/save_settings RPC 확장

**Files:**
- Create: `C:\ggotAI\supabase\migrations\20260618000100_rpa_program_settings.sql`
- Test: 적용 후 SQL 수동 검증(아래 Step)

- [ ] **Step 1: 마이그레이션 작성**

`C:\ggotAI\supabase\migrations\20260618000100_rpa_program_settings.sql`:

```sql
-- 2026-06-18 RPA 멀티 프로그램: 꽃집별 관리 프로그램 자동입력 설정.
-- setting_info 에 프로그램 종류/주소/계정 추가. 비밀번호는 암호화(iv:ct) 저장하며
-- get_settings 는 평문 대신 has_rpa_login_password 불리언만 노출한다.

alter table setting_info
  add column if not exists rpa_program_type varchar(20) default '',
  add column if not exists rpa_program_url  text,
  add column if not exists rpa_login_id     varchar(100),
  add column if not exists rpa_login_password text,
  add column if not exists rpa_enabled      varchar(1) default 'N',
  add column if not exists rpa_auto_submit  varchar(1) default 'Y';

-- get_settings: RPA 필드 추가(비번은 has_ 불리언만)
create or replace function get_settings(p_shop_key int, p_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_set    setting_info%rowtype;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  select * into v_set from setting_info where shop_key = p_shop_key limit 1;
  if not found then
    return json_build_object('ok', true, 'settings', null);
  end if;

  return json_build_object('ok', true, 'settings', json_build_object(
    'use_notification', v_set.use_notification,
    'notification_phone_number', v_set.notification_phone_number,
    'rpa_success_message', v_set.rpa_success_message,
    'rpa_manual_message', v_set.rpa_manual_message,
    'rpa_fail_message', v_set.rpa_fail_message,
    'order_hp_1', v_set.order_hp_1,
    'order_hp_2', v_set.order_hp_2,
    'order_landline_1', v_set.order_landline_1,
    'order_landline_2', v_set.order_landline_2,
    'shopping_mall_url', v_set.shopping_mall_url,
    'shopping_mall_id', v_set.shopping_mall_id,
    'intranet_url', v_set.intranet_url,
    'intranet_id', v_set.intranet_id,
    'shopping_mall_check_interval', v_set.shopping_mall_check_interval,
    'intranet_check_interval', v_set.intranet_check_interval,
    'has_shopping_mall_password', coalesce(v_set.shopping_mall_password,'') <> '',
    'has_intranet_password', coalesce(v_set.intranet_password,'') <> '',
    'rpa_program_type', v_set.rpa_program_type,
    'rpa_program_url', v_set.rpa_program_url,
    'rpa_login_id', v_set.rpa_login_id,
    'rpa_enabled', v_set.rpa_enabled,
    'rpa_auto_submit', v_set.rpa_auto_submit,
    'has_rpa_login_password', coalesce(v_set.rpa_login_password,'') <> ''
  ));
end;
$$;

-- save_settings: rpa_login_password 별도 인자(미전달 시 기존값 보존), 나머지는 jsonb
create or replace function save_settings(
  p_shop_key int,
  p_token    text,
  p_settings jsonb,
  p_shopping_mall_password text default null,
  p_intranet_password      text default null,
  p_rpa_login_password     text default null
) returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_count int;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  if coalesce(nullif(p_settings->>'order_hp_1',''), '') = '' then
    return json_build_object('ok', false, 'reason', 'order_hp_1_required');
  end if;

  update setting_info set
    use_notification = coalesce(p_settings->>'use_notification','Y'),
    notification_phone_number = nullif(p_settings->>'notification_phone_number',''),
    rpa_success_message = p_settings->>'rpa_success_message',
    rpa_manual_message = coalesce(p_settings->>'rpa_manual_message', rpa_manual_message),
    rpa_fail_message = p_settings->>'rpa_fail_message',
    order_hp_1 = p_settings->>'order_hp_1',
    order_hp_2 = nullif(p_settings->>'order_hp_2',''),
    order_landline_1 = nullif(p_settings->>'order_landline_1',''),
    order_landline_2 = nullif(p_settings->>'order_landline_2',''),
    shopping_mall_url = nullif(p_settings->>'shopping_mall_url',''),
    shopping_mall_id  = nullif(p_settings->>'shopping_mall_id',''),
    intranet_url = nullif(p_settings->>'intranet_url',''),
    intranet_id  = nullif(p_settings->>'intranet_id',''),
    shopping_mall_check_interval = coalesce((p_settings->>'shopping_mall_check_interval')::int, 10),
    intranet_check_interval      = coalesce((p_settings->>'intranet_check_interval')::int, 30),
    shopping_mall_password = coalesce(p_shopping_mall_password, shopping_mall_password),
    intranet_password      = coalesce(p_intranet_password, intranet_password),
    rpa_program_type = coalesce(p_settings->>'rpa_program_type', rpa_program_type),
    rpa_program_url  = nullif(p_settings->>'rpa_program_url',''),
    rpa_login_id     = nullif(p_settings->>'rpa_login_id',''),
    rpa_enabled      = coalesce(p_settings->>'rpa_enabled', rpa_enabled),
    rpa_auto_submit  = coalesce(p_settings->>'rpa_auto_submit', rpa_auto_submit),
    rpa_login_password = coalesce(p_rpa_login_password, rpa_login_password)
  where shop_key = p_shop_key;
  get diagnostics v_count = row_count;

  if v_count = 0 then
    insert into setting_info(
      shop_key, use_notification, notification_phone_number,
      rpa_success_message, rpa_manual_message, rpa_fail_message,
      order_hp_1, order_hp_2, order_landline_1, order_landline_2,
      shopping_mall_url, shopping_mall_id, shopping_mall_password,
      intranet_url, intranet_id, intranet_password,
      shopping_mall_check_interval, intranet_check_interval,
      rpa_program_type, rpa_program_url, rpa_login_id, rpa_login_password,
      rpa_enabled, rpa_auto_submit)
    values(
      p_shop_key,
      coalesce(p_settings->>'use_notification','Y'),
      nullif(p_settings->>'notification_phone_number',''),
      p_settings->>'rpa_success_message',
      coalesce(p_settings->>'rpa_manual_message',
               '[ggotAI] {channel} 주문 {count}건 접수 — 관리 프로그램에 직접 입력해 주세요.'),
      p_settings->>'rpa_fail_message',
      p_settings->>'order_hp_1',
      nullif(p_settings->>'order_hp_2',''),
      nullif(p_settings->>'order_landline_1',''),
      nullif(p_settings->>'order_landline_2',''),
      nullif(p_settings->>'shopping_mall_url',''),
      nullif(p_settings->>'shopping_mall_id',''),
      p_shopping_mall_password,
      nullif(p_settings->>'intranet_url',''),
      nullif(p_settings->>'intranet_id',''),
      p_intranet_password,
      coalesce((p_settings->>'shopping_mall_check_interval')::int, 10),
      coalesce((p_settings->>'intranet_check_interval')::int, 30),
      coalesce(p_settings->>'rpa_program_type',''),
      nullif(p_settings->>'rpa_program_url',''),
      nullif(p_settings->>'rpa_login_id',''),
      p_rpa_login_password,
      coalesce(p_settings->>'rpa_enabled','N'),
      coalesce(p_settings->>'rpa_auto_submit','Y'));
  end if;

  return json_build_object('ok', true);
end;
$$;

grant execute on function get_settings(int, text) to anon;
grant execute on function save_settings(int, text, jsonb, text, text, text) to anon;
```

> 주의: `save_settings` 시그니처에 인자가 1개 추가된다. 기존 5인자 버전이 남아 오버로드 충돌이
> 나면 적용 전 `drop function if exists save_settings(int, text, jsonb, text, text);` 를 선행한다.

- [ ] **Step 2: 마이그레이션 적용**

라이브 적용은 사용자 승인 후. Supabase MCP `apply_migration`(name=`rpa_program_settings`) 또는
`supabase db push`. 적용 후 검증:

Run(SQL): `select column_name from information_schema.columns where table_name='setting_info' and column_name like 'rpa_%';`
Expected: `rpa_program_type, rpa_program_url, rpa_login_id, rpa_login_password, rpa_enabled, rpa_auto_submit` + 기존 rpa_* 메시지 컬럼

- [ ] **Step 3: RPC 라운드트립 검증(수동)**

`save_settings` 로 `rpa_program_type='flowernt'`, 비번 인자 1건 저장 후 `get_settings` 호출 →
`has_rpa_login_password=true`, 평문 미노출 확인.

- [ ] **Step 4: 커밋**

```bash
git add ggotAIorder/../supabase/migrations/20260618000100_rpa_program_settings.sql
git commit -m "feat(db): setting_info RPA 프로그램 설정 컬럼 + get/save_settings 확장"
```
> 경로 주의: 마이그레이션은 리포 루트 `supabase/migrations` 아래다(`git add supabase/migrations/2026...`).

---

## Task 8: 프론트엔드 설정 UI + 타입

**Files:**
- Modify: `frontend/src/settings/client.ts`
- Modify: `frontend/src/views/settings.tsx`
- Modify: `frontend/src/types/database.ts`, `frontend/src/types/db.ts`
- Test: `frontend/src/settings/client.test.ts`

기존 `intranet` 비밀번호 패턴을 그대로 복제한다.

- [ ] **Step 1: client.ts 타입/인자 확장**

`SettingsData` 인터페이스에 추가:

```typescript
  rpa_program_type: string;
  rpa_program_url: string | null;
  rpa_login_id: string | null;
  rpa_enabled: string;
  rpa_auto_submit: string;
  has_rpa_login_password: boolean;
```

`saveSettings` 시그니처/호출에 비번 인자 추가:

```typescript
export async function saveSettings(
  rpc: DashRpc, shopKey: number, token: string,
  settings: SettingsData,
  shoppingMallPassword: string | null,
  intranetPassword: string | null,
  rpaLoginPassword: string | null,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await rpc('save_settings', {
    p_shop_key: shopKey, p_token: token, p_settings: settings,
    p_shopping_mall_password: shoppingMallPassword,
    p_intranet_password: intranetPassword,
    p_rpa_login_password: rpaLoginPassword,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true };
}
```

- [ ] **Step 2: client.test.ts 갱신**

`saveSettings` 를 호출하는 기존 테스트에 6번째 인자(`null` 또는 `'pw'`)를 추가하고,
`p_rpa_login_password` 가 RPC로 전달되는지 검증하는 케이스를 추가한다(기존 intranet 케이스 복제).

Run: `cd frontend && npm test -- client.test`
Expected: PASS

- [ ] **Step 3: settings.tsx — 상태/초기값/저장 배선**

`DEFAULT`(20~28행 근처)에 추가:

```typescript
  rpa_program_type: '',
  rpa_program_url: '',
  rpa_login_id: '',
  rpa_enabled: 'N',
  rpa_auto_submit: 'Y',
  has_rpa_login_password: false,
```

`intranetPassword` 상태 옆에:

```typescript
  const [rpaLoginPassword, setRpaLoginPassword] = useState('');
```

로드 매핑(73~77행 근처)에 추가:

```typescript
          rpa_program_type: r.settings.rpa_program_type ?? '',
          rpa_program_url: r.settings.rpa_program_url ?? '',
          rpa_login_id: r.settings.rpa_login_id ?? '',
          rpa_enabled: r.settings.rpa_enabled ?? 'N',
          rpa_auto_submit: r.settings.rpa_auto_submit ?? 'Y',
```

저장부(97~117행 근처)에 추가:

```typescript
    const rpaPw = rpaLoginPassword.trim() ? encryptPassword(rpaLoginPassword.trim()) : null;
```

`saveSettings(...)` 호출에 `rpaPw` 를 6번째 인자로 추가하고, 낙관적 갱신에:

```typescript
      has_rpa_login_password: prev.has_rpa_login_password || rpaPw !== null,
```

- [ ] **Step 4: settings.tsx — UI 섹션 추가**

인트라넷 섹션과 동일 구조로 "관리 프로그램(RPA)" 섹션을 추가:

```tsx
<fieldset>
  <legend>관리 프로그램 (자동입력)</legend>
  <label>프로그램 종류
    <select name="rpa_program_type" value={settings.rpa_program_type}
            onChange={handleInputChange}>
      <option value="">선택 안 함</option>
      <option value="flowernt">FlowerNT</option>
      <option value="roseweb">Roseweb</option>
      <option value="etc">기타</option>
    </select>
  </label>
  <label>웹 주소
    <input type="url" name="rpa_program_url" placeholder="https://www.flowernt.com"
           value={settings.rpa_program_url ?? ''} onChange={handleInputChange} />
  </label>
  <label>아이디
    <input type="text" name="rpa_login_id" placeholder="로그인 아이디"
           value={settings.rpa_login_id ?? ''} onChange={handleInputChange} />
  </label>
  <label>비밀번호 <PwBadge set={settings.has_rpa_login_password} />
    <input type="password" placeholder="수정할 때만 입력"
           value={rpaLoginPassword} onChange={(e) => setRpaLoginPassword(e.target.value)} />
  </label>
  <label>RPA 사용
    <select name="rpa_enabled" value={settings.rpa_enabled} onChange={handleInputChange}>
      <option value="Y">사용</option><option value="N">미사용</option>
    </select>
  </label>
  <label>자동 등록
    <select name="rpa_auto_submit" value={settings.rpa_auto_submit} onChange={handleInputChange}>
      <option value="Y">등록까지 자동</option><option value="N">채우기만</option>
    </select>
  </label>
</fieldset>
```

- [ ] **Step 5: 타입 동기화**

`frontend/src/types/database.ts` / `db.ts` 의 `setting_info` Row/Insert/Update 에
신규 컬럼(`rpa_program_type`, `rpa_program_url`, `rpa_login_id`, `rpa_login_password`,
`rpa_enabled`, `rpa_auto_submit`)을 추가한다. types-in-sync 가드 테스트가 있으면 통과시킨다.

Run: `cd frontend && npm run build && npm test`
Expected: PASS (빌드 + 테스트)

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/settings/client.ts frontend/src/settings/client.test.ts frontend/src/views/settings.tsx frontend/src/types/database.ts frontend/src/types/db.ts
git commit -m "feat(frontend): RPA 관리 프로그램 설정 UI(종류/주소/계정/비번/사용/자동등록)"
```

---

## Task 9: 라이브 E2E 검증 + 라디오/리본/로그인 최종 확정

**Files:**
- 코드 수정은 라이브 확인 결과에 따라(automator의 라디오 라벨/로그인 셀렉터/리본 매핑)

이 태스크는 실제 FlowerNT3에 대해 수행한다. 쓰레기 주문 방지를 위해 1건만, 신중히.

- [ ] **Step 1: 전용 프로필 Chrome 기동 + 로그인**

```powershell
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -ArgumentList "--remote-debugging-port=9222","--user-data-dir=C:\ggotAI\rpa_profile",`
  "--no-first-run","--no-default-browser-check"
```
FlowerNT3 로그인 후 메인까지.

- [ ] **Step 2: 라디오 라벨/순서 확정**

`order/order3.asp` 의 `order_divi` 라디오 실제 라벨을 읽어 `mapping.CHANNEL_TO_ORDER_DIVI`
우변 값(전화/매장판매/홈페이지/프로그램간/기타)이 실제 라벨과 일치하는지 확인. 다르면 매핑 우변 보정.

- [ ] **Step 3: 리본/카드 칸 확정**

`event_txt`(경조문구)와 `msg_text`(카드) 칸이 의도대로인지 라이브에서 확인. 보내는분 전용 칸이
따로 있으면 `_ribbon_text`/`order_to_fields` 매핑을 보정하고 Task 2 테스트도 갱신.

- [ ] **Step 4: 로그인 셀렉터 확정**

로그아웃 상태에서 `_try_login` 의 아이디/비번 input 셀렉터가 실제 로그인 폼과 맞는지 확인·보정.

- [ ] **Step 5: 실주문 1건 E2E**

`rpa_enabled='Y'`, `rpa_auto_submit='N'`(우선 채우기만)로 설정 후 테스트 통화 1건 →
폼이 올바르게 채워지는지 눈으로 확인 → 이상 없으면 `rpa_auto_submit='Y'`로 1건 등록까지 검증 →
`order_details.rpa_status='success'` + 알림 success 확인.

- [ ] **Step 6: 보정 커밋(있으면)**

```bash
git add backend/src/ggotaiorder/rpa/flowernt3/
git commit -m "fix(rpa): 라이브 FlowerNT3 라디오/리본/로그인 셀렉터 확정"
```

- [ ] **Step 7: 메모리 업데이트**

`ggotai-bug-audit-2026-06`의 P0-1(RPA 미구현) 해소, `ggotai-current-state` 갱신.

---

## Self-Review (작성자 점검 결과)

- **Spec 커버리지:** §3 아키텍처→Task 4·6, §3.1 세션→Task 5, §4 매핑→Task 2, §4.1 채널맵→Task 2,
  §5 마이그레이션/RPC→Task 7, §6 프론트→Task 8, §7 에러흐름→기존 singleton(Task 6 보존), §8 테스트→각 Task,
  §9 의존성→Task 1, §10 순서→Task 1~9. 누락 없음.
- **타입 일관성:** `RpaProgramSettings`(program_type/url/login_id/login_password/enabled/auto_submit),
  `build_automator(settings, *, debug_port)`, `fill_order_form(frame, order, *, auto_submit)`,
  `load_program_settings(shop_key, aes_key)`, `parse_settings_row(row, aes_key)` — Task 간 시그니처 일치.
- **순서 의존:** Task 4가 `FlowerNt3Automator` import를 요구하므로 골격을 Task 4 Step 4에서 먼저 두고
  Task 5에서 본구현으로 교체(전방참조 해소). Task 6은 Task 3·4에 의존, Task 8은 Task 7 RPC에 의존.
- **Placeholder:** 라이브 확정(라디오 라벨/로그인 셀렉터/리본)은 Task 9에서 실폼으로 검증 — 의도적 보류이며
  기본값으로 동작 가능. 코드/테스트 스텝은 모두 실제 코드 포함.
