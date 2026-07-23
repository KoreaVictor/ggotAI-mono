# RoseWeb RPA — Phase 2 구현 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (인라인, 라이브 검증 체크포인트).
> Task 1·4·5·7 은 실물 RoseWeb 구동이 필요한 **라이브** 작업이라 사람과 함께 실행한다(자율 서브에이전트
> 부적합). Task 2·3 은 순수 로직 TDD 라 단독 가능. 스텝은 `- [ ]` 체크박스.

**Goal:** 화원박사 ROSEWeb(Delphi 데스크톱 앱) 주문입력 폼에 수집된 주문(`RpaOrder`)을 자동 입력한다.

**Architecture:** 기존 `ProgramAutomator` 계약·`rpa.factory`·`ManualOnlyAutomator` 백업을 재사용.
신규 `rpa/roseweb/`(`layout.py` 측정 상수 + `mapping.py` 순수 로직 + `locator.py` 필드 찾기 +
`automator.py` 구동). 입력은 **폼 기준 상대좌표로 UIA 컨트롤을 찾아 `SetFocus()`+`SendKeys()`**.
데이터 주도: 필드 키 → 상대좌표 표(`layout.FIELD_POSITIONS`), 필드 키 → 입력값(`mapping.order_to_values`).

**Tech Stack:** Windows UI Automation(`uiautomation`, 설치됨), Python(system Python313 backend venv).

## Global Constraints

- 스파이크 findings 준수: `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md`.
- RoseWeb = 화원박사, exe `C:\Roseweb\prog\roseweb.exe`(WorkingDir=`C:\Roseweb\prog`), 자동 로그인.
  주문폼 창 class `TFmju1inp`, 메인 창 class `TFmMain`, 프로세스명 `roseweb`.
- 쓰기 = 대상 컨트롤 `SetFocus()`→`SendKeys(값)`→커밋키(`{Tab}`/`{Enter}`). `ValuePattern` 불가.
- **auto_submit 기본 N(채우기만).** 저장 클릭은 auto_submit=Y 일 때만. 검증 전엔 절대 저장 금지.
- 자동화 실패/미기동 시 `ManualOnlyAutomator` 백업으로 흘러 주문 유실 없음(기존 계약 유지).
- 기존 FlowerNT RPA 코드는 건드리지 않는다. 이미지 폴백(`pyautogui`/`opencv`) 미추가.
- 필드 식별자(핸들)는 불안정 → 절대 하드코딩 금지. 위치는 `layout.py`(Task 1 측정)에서만 온다.

---

### Task 1: 폼 레이아웃·조작법 실측 → `layout.py` (라이브 측정)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/roseweb/__init__.py` (빈 파일)
- Create: `backend/src/ggotaiorder/rpa/roseweb/layout.py`
- Tool: `backend/scripts/roseweb_inspect.py` (기존, 재사용)

**Interfaces:**
- Produces:
  - `FORM_CLASS = "TFmju1inp"`, `MAIN_CLASS = "TFmMain"`, `PROC_NAME = "roseweb"`,
    `EXE_PATH = r"C:\Roseweb\prog\roseweb.exe"`
  - `FIELD_POSITIONS: dict[str, tuple[int, int]]` — 필드키 → 폼 좌상단 기준 상대(dx, dy) 픽셀.
    필드키: `product_name, unit_price, quantity, delivery_date, delivery_time, delivery_place,
    receiver_name, receiver_phone, ribbon_congrats, ribbon_sender, card, orderer_name, orderer_phone`.
  - `SAVE_BUTTON_POS: tuple[int,int]`, `STATUS_NORMAL_POS: tuple[int,int]`(주문상태 '정상' 라디오).
  - `OPEN_NEW_ORDER: str` — 신규 주문폼 여는 법(메뉴 경로 또는 단축키; Task 1 실측).
  - `PRODUCT_DIRECT_TYPE: bool` — 상품명을 상품명칸에 직접 타이핑 가능(True) / 돋보기 검색 필수(False).

- [ ] **Step 1: RoseWeb 실행·주문폼 열기**

Run(PowerShell): `Start-Process "C:\Roseweb\prog\roseweb.exe" -WorkingDirectory "C:\Roseweb\prog"`
신규 주문폼(`TFmju1inp`)을 연다. 여는 조작(메뉴 클릭/툴바/단축키)을 기록 → `OPEN_NEW_ORDER`.

- [ ] **Step 2: 입력칸 좌표 덤프(2회, 안정성 확인)**

Run: `python -X utf8 backend/scripts/roseweb_inspect.py edits TFmju1inp`
폼을 닫았다 다시 열어 한 번 더 실행한다. 두 번의 (top,left) 목록이 **동일하면** 좌표 안정.
각 목표 필드의 스크린 (top,left)에서 폼 좌상단(BoundingRectangle.left/top)을 빼 **상대(dx,dy)** 계산.

- [ ] **Step 3: 상품명 직접 타이핑 가능 여부 확인**

상품명 칸에 `SetFocus()`+`SendKeys('장미꽃다발')` 시도(저장 안 함) → 값이 들어가고 유지되면
`PRODUCT_DIRECT_TYPE=True`. 돋보기 검색창이 강제로 뜨거나 값이 사라지면 False(→ Task 5에서 검색 처리).
확인 후 `{Ctrl}a{Delete}` 로 삭제.

- [ ] **Step 4: `layout.py` 작성(측정값 기입)**

```python
"""RoseWeb(화원박사 TFmju1inp) 폼 레이아웃 실측 상수.

식별자(핸들)가 불안정해 필드는 '폼 좌상단 기준 상대좌표'로 찾는다(locator 참조).
값은 2026-07-23 스파이크/Task1 실측(build 208.5.1, 1076x854). 폼 크기/버전이 바뀌면 재측정.
"""
from __future__ import annotations

EXE_PATH = r"C:\Roseweb\prog\roseweb.exe"
WORKDIR = r"C:\Roseweb\prog"
PROC_NAME = "roseweb"
MAIN_CLASS = "TFmMain"
FORM_CLASS = "TFmju1inp"

# 신규 주문폼 여는 법(Task1 실측: 예 "{F2}" 또는 메뉴 경로 문자열). 실측값으로 대체.
OPEN_NEW_ORDER = "<Task1 실측>"
PRODUCT_DIRECT_TYPE = True  # Task1 실측 결과로 대체

# 필드키 → 폼 좌상단 기준 상대 (dx, dy). Task1 실측값으로 채운다.
FIELD_POSITIONS: dict[str, tuple[int, int]] = {
    # "product_name": (dx, dy), ... 13개 필드
}
SAVE_BUTTON_POS: tuple[int, int] = (0, 0)      # 저장 버튼 상대좌표(실측)
STATUS_NORMAL_POS: tuple[int, int] = (0, 0)    # 주문상태 '정상' 라디오(실측)
```
`FIELD_POSITIONS` 는 Step 2 계산값으로 13개 필드 모두 채운다. `<...>`/`(0,0)` 플레이스홀더가
남지 않게 실측값으로 완전히 대체한다.

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/roseweb/__init__.py backend/src/ggotaiorder/rpa/roseweb/layout.py
git commit -m "feat(rpa/roseweb): 폼 레이아웃 실측 상수(layout.py)"
```

---

### Task 2: `mapping.py` — RpaOrder → 필드값 (순수 로직 TDD)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/roseweb/mapping.py`
- Test: `backend/tests/rpa/roseweb/test_mapping.py`

**Interfaces:**
- Consumes: `ggotaiorder.rpa.models.RpaOrder`.
- Produces:
  - `normalize_price(price: object) -> str`
  - `split_delivery(delivery_at: str | None) -> tuple[str, str]`  # ('YYYY-MM-DD', 'HH:MM')
  - `order_to_values(order: RpaOrder) -> dict[str, str]`  # 필드키 → 타이핑할 문자열(빈값이면 키 생략)

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/rpa/roseweb/test_mapping.py
from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.roseweb import mapping


def _order(**kw):
    base = dict(order_detail_id=1, shop_key=19, shop_name="꽃집", channel="쇼핑몰",
                customer_name="김발주", customer_phone_number="01011112222",
                product_name="장미꽃다발", quantity=1, price=55000,
                delivery_at="2026-07-25T14:30:00", delivery_place="서울 강남구 논현로 1",
                receiver_name="이받는", receiver_phone_number="01033334444",
                ribbon_sender="김발주", ribbon_congratulations="축 개업",
                card_message="번창하세요")
    base.update(kw)
    return RpaOrder(**base)


def test_normalize_price_digits_only():
    assert mapping.normalize_price("55,000원") == "55000"
    assert mapping.normalize_price(55000) == "55000"


def test_split_delivery_date_and_time():
    assert mapping.split_delivery("2026-07-25T14:30:00") == ("2026-07-25", "14:30")


def test_split_delivery_none_is_empty():
    assert mapping.split_delivery(None) == ("", "")


def test_order_to_values_maps_core_fields():
    v = mapping.order_to_values(_order())
    assert v["product_name"] == "장미꽃다발"
    assert v["unit_price"] == "55000"
    assert v["quantity"] == "1"
    assert v["delivery_date"] == "2026-07-25"
    assert v["delivery_time"] == "14:30"
    assert v["delivery_place"] == "서울 강남구 논현로 1"
    assert v["receiver_name"] == "이받는"
    assert v["receiver_phone"] == "01033334444"
    assert v["ribbon_congrats"] == "축 개업"
    assert v["ribbon_sender"] == "김발주"
    assert v["card"] == "번창하세요"
    assert v["orderer_name"] == "김발주"
    assert v["orderer_phone"] == "01011112222"


def test_order_to_values_omits_empty_optionals():
    v = mapping.order_to_values(_order(card_message=None, ribbon_sender=None))
    assert "card" not in v
    assert "ribbon_sender" not in v
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest backend/tests/rpa/roseweb/test_mapping.py -q`
Expected: FAIL (`ModuleNotFoundError: ...roseweb.mapping`).

- [ ] **Step 3: 최소 구현**

```python
# backend/src/ggotaiorder/rpa/roseweb/mapping.py
from __future__ import annotations

import re

from ggotaiorder.rpa.models import RpaOrder


def normalize_price(price: object) -> str:
    digits = re.sub(r"[^0-9]", "", str(price or ""))
    return digits or "0"


def split_delivery(delivery_at: str | None) -> tuple[str, str]:
    if not delivery_at:
        return ("", "")
    s = delivery_at.strip().replace("T", " ")
    date_part = s[:10]
    time_part = ""
    if len(s) >= 16:
        time_part = s[11:16]
    return (date_part, time_part)


def order_to_values(order: RpaOrder) -> dict[str, str]:
    date_str, time_str = split_delivery(order.delivery_at)
    raw = {
        "product_name": order.product_name,
        "unit_price": normalize_price(order.price),
        "quantity": str(order.quantity or 1),
        "delivery_date": date_str,
        "delivery_time": time_str or (order.delivery_at_text or ""),
        "delivery_place": order.delivery_place,
        "receiver_name": order.receiver_name,
        "receiver_phone": order.receiver_phone_number,
        "ribbon_congrats": order.ribbon_congratulations,
        "ribbon_sender": order.ribbon_sender,
        "card": order.card_message,
        "orderer_name": order.customer_name,
        "orderer_phone": order.customer_phone_number,
    }
    return {k: str(v) for k, v in raw.items() if v not in (None, "")}
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest backend/tests/rpa/roseweb/test_mapping.py -q`
Expected: PASS (전부).

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/roseweb/mapping.py backend/tests/rpa/roseweb/test_mapping.py
git commit -m "feat(rpa/roseweb): RpaOrder→필드값 매핑(mapping.py) TDD"
```

---

### Task 3: `locator.py` — 상대좌표로 컨트롤 찾기 (순수 로직 TDD)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/roseweb/locator.py`
- Test: `backend/tests/rpa/roseweb/test_locator.py`

**Interfaces:**
- Produces: `nearest_edit(edits: list, rel_x: int, rel_y: int, origin_x: int, origin_y: int) -> object | None`
  — 각 edit 의 `BoundingRectangle`(top/left) 을 폼 origin 기준 상대좌표로 환산해 (rel_x,rel_y) 에
  가장 가까운 컨트롤 반환(허용 반경 밖이면 None).

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/rpa/roseweb/test_locator.py
from ggotaiorder.rpa.roseweb import locator


class _Rect:
    def __init__(self, left, top):
        self.left, self.top = left, top


class _Ctrl:
    def __init__(self, name, left, top):
        self.name = name
        self.BoundingRectangle = _Rect(left, top)


def test_nearest_edit_picks_closest_by_relative_pos():
    # 폼 origin (421,113). 목표 상대 (120, 50) → 스크린 (541,163) 근처.
    a = _Ctrl("date", 540, 165)     # 상대 (119,52) — 가장 가까움
    b = _Ctrl("far", 900, 500)
    got = locator.nearest_edit([a, b], 120, 50, 421, 113)
    assert got is a


def test_nearest_edit_none_when_all_out_of_radius():
    b = _Ctrl("far", 900, 500)
    got = locator.nearest_edit([b], 120, 50, 421, 113, radius=40)
    assert got is None
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest backend/tests/rpa/roseweb/test_locator.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: 최소 구현**

```python
# backend/src/ggotaiorder/rpa/roseweb/locator.py
from __future__ import annotations


def nearest_edit(edits, rel_x, rel_y, origin_x, origin_y, radius: int = 60):
    best = None
    best_d2 = None
    for e in edits:
        r = e.BoundingRectangle
        dx = (r.left - origin_x) - rel_x
        dy = (r.top - origin_y) - rel_y
        d2 = dx * dx + dy * dy
        if best_d2 is None or d2 < best_d2:
            best, best_d2 = e, d2
    if best is None or best_d2 > radius * radius:
        return None
    return best
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest backend/tests/rpa/roseweb/test_locator.py -q`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/roseweb/locator.py backend/tests/rpa/roseweb/test_locator.py
git commit -m "feat(rpa/roseweb): 상대좌표 컨트롤 로케이터(locator.py) TDD"
```

---

### Task 4: `RoseWebAutomator` — is_program_running + 실행 (라이브 검증)

**Files:**
- Create: `backend/src/ggotaiorder/rpa/roseweb/automator.py`

**Interfaces:**
- Consumes: `rpa/roseweb/layout.py`.
- Produces: `RoseWebAutomator(url, login_id, login_password, auto_submit)` with
  `is_program_running() -> bool`, `input_order(order: RpaOrder) -> None`(Task5에서 완성).

- [ ] **Step 1: 실행·감지 구현**

```python
# backend/src/ggotaiorder/rpa/roseweb/automator.py
from __future__ import annotations

import logging
import subprocess
import time

import uiautomation as auto

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.roseweb import layout

logger = logging.getLogger(__name__)


class RoseWebAutomator:
    def __init__(self, url=None, login_id=None, login_password=None, auto_submit=False):
        self._auto_submit = auto_submit  # url/login 은 화원박사 자동로그인이라 미사용(계약 호환용)

    def _main_window(self):
        root = auto.GetRootControl()
        for w in root.GetChildren():
            if w.ClassName == layout.MAIN_CLASS:
                return w
        return None

    def _ensure_running(self, timeout_s: float = 25.0) -> bool:
        if self._main_window() is not None:
            return True
        logger.info("RoseWeb 미기동 — 실행")
        subprocess.Popen([layout.EXE_PATH], cwd=layout.WORKDIR)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._main_window() is not None:
                return True
            time.sleep(1.0)
        logger.warning("RoseWeb 기동 확인 실패(%.0fs)", timeout_s)
        return False

    def is_program_running(self) -> bool:
        try:
            return self._ensure_running()
        except Exception:
            logger.exception("RoseWeb is_program_running 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        raise NotImplementedError  # Task 5
```

- [ ] **Step 2: 라이브 검증 — 미기동에서 자동 실행**

RoseWeb 종료 상태에서:
`python -X utf8 -c "from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator as A; print(A().is_program_running())"`
Expected: RoseWeb 가 뜨고(자동 로그인) `True` 출력. 이미 떠 있으면 즉시 `True`.

- [ ] **Step 3: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/roseweb/automator.py
git commit -m "feat(rpa/roseweb): RoseWebAutomator 실행·감지(is_program_running)"
```

---

### Task 5: `input_order` — 폼 열기·필드 채우기·(옵션)저장 (라이브 검증)

**Files:**
- Modify: `backend/src/ggotaiorder/rpa/roseweb/automator.py`

**Interfaces:**
- Consumes: `layout`(위치/조작), `mapping.order_to_values`, `locator.nearest_edit`.

- [ ] **Step 1: input_order 구현**

`_main_window()` 확인 → `layout.OPEN_NEW_ORDER` 로 신규 주문폼(`TFmju1inp`) 열기 →
그 폼의 origin(left/top) 과 edit 목록 수집 → `mapping.order_to_values(order)` 의 각 키에 대해
`locator.nearest_edit(edits, *layout.FIELD_POSITIONS[key], origin_x, origin_y)` 로 컨트롤 찾기 →
`ctrl.SetFocus(); auto.SendKeys(value); auto.SendKeys('{Tab}')`. 날짜/시간은 형식대로 타이핑 후 `{Tab}`.
`auto_submit` 이면 `STATUS_NORMAL_POS` 확인 후 `SAVE_BUTTON_POS` 클릭(그리고 뜨는 확인 다이얼로그
처리) — **auto_submit=False 면 저장 안 함**. 폼/필드 미발견 시 `RuntimeError`(→ manual 백업).

```python
    def input_order(self, order: RpaOrder) -> None:
        from ggotaiorder.rpa.roseweb import locator, mapping
        if not self._ensure_running():
            raise RuntimeError("RoseWeb 미기동 — 자동입력 불가")
        self._open_new_order()                     # layout.OPEN_NEW_ORDER 사용
        form = self._order_form()                  # TFmju1inp 대기·반환
        if form is None:
            raise RuntimeError("RoseWeb 주문폼(TFmju1inp) 미검출")
        r = form.BoundingRectangle
        edits = self._collect_edits(form)
        values = mapping.order_to_values(order)
        for key, value in values.items():
            pos = layout.FIELD_POSITIONS.get(key)
            if pos is None:
                continue
            ctrl = locator.nearest_edit(edits, pos[0], pos[1], r.left, r.top)
            if ctrl is None:
                logger.warning("RoseWeb 필드 미발견 key=%s", key)
                continue
            ctrl.SetFocus()
            auto.SendKeys(value, waitTime=0.02)
            auto.SendKeys("{Tab}", waitTime=0.02)
        if self._auto_submit:
            self._save(form)                        # 정상 라디오 확인 + 저장 클릭 + 다이얼로그
        else:
            logger.info("RoseWeb auto_submit=N — 채우기만 완료(저장 안 함)")
```

(`_open_new_order`, `_order_form`, `_collect_edits`, `_save` 는 layout 상수를 쓰는 보조 메서드로 함께
구현. `_collect_edits` 는 스파이크 `roseweb_inspect.cmd_edits` 의 순회 로직과 동일.)

- [ ] **Step 2: 라이브 검증 — 채우기(auto_submit=N)**

테스트 `RpaOrder` 1건으로:
`RoseWebAutomator(auto_submit=False).input_order(test_order)` 실행 → RoseWeb 주문폼에 상품명·단가·
수량·배달일자/시간·배달장소·받는분·전화·경조사어·보내는이·카드가 **정확히** 채워졌는지 눈으로 확인.
**저장하지 않고** `취소` 로 닫는다.

- [ ] **Step 3: 라이브 검증 — 저장(auto_submit=Y) 1건**

사장님 입회 하에 `auto_submit=True` 로 1건 실행 → `저장`까지 되고 화원박사에 주문이 등록되는지 확인.
(등록되면 화원박사에서 그 테스트 주문 삭제.)

- [ ] **Step 4: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/roseweb/automator.py
git commit -m "feat(rpa/roseweb): input_order — 폼 채우기·auto_submit 저장"
```

---

### Task 6: 배선 — factory·config, 스텁 제거

**Files:**
- Modify: `backend/src/ggotaiorder/rpa/factory.py:30-34`
- Modify: `backend/src/ggotaiorder/rpa/adapters.py` (RoseWebAutomator 스텁 제거, ManualOnly 유지)
- Modify: `backend/src/ggotaiorder/config.py` (필요시 ROSEWEB_EXE_PATH; 기본은 layout 상수라 선택)
- Test: `backend/tests/rpa/test_factory.py`(있으면 확장, 없으면 생성)

**Interfaces:**
- Consumes: `rpa/roseweb/automator.RoseWebAutomator`.

- [ ] **Step 1: 실패 테스트 — roseweb 선택 시 신규 automator 반환**

```python
# backend/tests/rpa/test_factory.py (해당 케이스 추가)
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings
from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator


def test_factory_builds_roseweb_with_auto_submit():
    s = RpaProgramSettings(program_type="roseweb", url=None, login_id="x",
                           login_password="y", enabled=True, auto_submit=True)
    a = build_automator(s, debug_port=0)
    assert isinstance(a, RoseWebAutomator)
    assert a._auto_submit is True
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest backend/tests/rpa/test_factory.py -q`
Expected: FAIL (factory 가 adapters 스텁을 쓰거나 auto_submit 미전달).

- [ ] **Step 3: factory 배선 수정 + 스텁 제거**

`factory.py` 의 roseweb 분기를 신규 automator 로 교체하고 `auto_submit` 전달:
```python
    from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator
    if settings.program_type == "roseweb":
        return RoseWebAutomator(
            url=settings.url, login_id=settings.login_id,
            login_password=settings.login_password, auto_submit=settings.auto_submit,
        )
```
`adapters.py` 에서 기존 `RoseWebAutomator` 클래스(스텁) 삭제(`ManualOnlyAutomator` 유지). factory
import 를 `adapters` → `roseweb.automator` 로 변경.

- [ ] **Step 4: 통과 확인 + 회귀**

Run: `python -m pytest backend/tests/rpa/ -q`  → PASS
Run: `python -m pytest -q`  → 기존 전체 그린 유지.

- [ ] **Step 5: 커밋**

```bash
git add backend/src/ggotaiorder/rpa/factory.py backend/src/ggotaiorder/rpa/adapters.py backend/tests/rpa/test_factory.py
git commit -m "feat(rpa/roseweb): factory 배선·스텁 제거"
```

---

### Task 7: 종단 라이브 E2E + 백업 폴백 확인

**Files:** (검증 전용, 코드 변경 없음)

- [ ] **Step 1: 관통 확인(auto_submit=N)**

setting_info(shop) 를 program_type='roseweb', enabled='Y', auto_submit='N' 로 두고, 실제 수집 주문
1건이 `enqueue` → RoseWeb 폼 채우기까지 관통하는지 확인(저장 안 됨).

- [ ] **Step 2: 백업 폴백 확인**

RoseWeb 를 종료한 상태로 주문 1건 → `is_program_running()`=False → `ManualOnlyAutomator` 백업
경로('manual')로 흐르고 주문이 유실되지 않는지 확인.

- [ ] **Step 3: (검증 통과 시) auto_submit=Y 전환은 사장님 결정**

FlowerNT 관례대로, 채우기 검증이 충분히 쌓인 뒤 사장님이 auto_submit=Y 로 전환.

---

## Self-Review

- **Spec coverage:** 스펙의 Phase 2 항목 매핑 — mapping(Task2)/automator UIA구동(Task4·5)/factory·config
  배선(Task6)/auto_submit=N 라이브 E2E(Task7)/manual 백업(Task7 Step2). findings의 "탭순서 아닌
  좌표 addressing"은 Task1(layout)+Task3(locator)로 구현.
- **Placeholder scan:** Task1 의 `<Task1 실측>`·`(0,0)` 은 **측정 후 실값으로 대체하라는 명시 지시**이며
  Step4에 "플레이스홀더가 남지 않게"라고 못박음. 이후 코드는 `layout.FIELD_POSITIONS[key]` 심볼만
  참조하므로 미지수 하드코딩 없음.
- **Type consistency:** 필드키 집합(`product_name, unit_price, quantity, delivery_date, delivery_time,
  delivery_place, receiver_name, receiver_phone, ribbon_congrats, ribbon_sender, card, orderer_name,
  orderer_phone`)이 mapping.order_to_values·layout.FIELD_POSITIONS·input_order 에서 일치.
  `nearest_edit` 시그니처 Task3 정의 = Task5 호출 일치.
- **Risk(문서화):** SendKeys 포커스 점유(사장님 동시조작), Delphi lookup(상품/고객) 직접타이핑 여부는
  Task1 Step3 가 판정 — False 면 Task5 에 상품검색 처리 스텝을 추가한다(findings 반영).
