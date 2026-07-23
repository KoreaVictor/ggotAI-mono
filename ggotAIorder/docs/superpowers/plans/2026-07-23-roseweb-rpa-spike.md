# RoseWeb RPA — Phase 1 정탐 스파이크 Implementation Plan

> **For agentic workers:** 이 계획은 **대화형 정탐(spike)** 이다. GUI 앱을 띄우고 눈으로 확인하며
> 사장님께 exe 경로/설치본을 받아야 하므로 **인라인 실행(사람과 함께)** 이 맞다. 자율 서브에이전트에
> 넘기지 말 것. 산출물은 코드가 아니라 **조사 문서**다(따라서 RED-GREEN TDD가 아닌 "행동→확인" 단계).

**Goal:** RoseWeb(Windows 데스크톱 앱)의 UI 기술·컨트롤 주소지정 가능성·로그인/주문 흐름·필드
매핑·포커스 강탈 여부를 실물로 확정해, Phase 2(실제 자동입력) 구현 계획을 쓸 수 있게 한다.

**Architecture:** Python UIA 라이브러리(`uiautomation`)로 RoseWeb 창의 컨트롤 트리를 덤프해 조사한다.
프로덕션 코드는 이 단계에서 만들지 않는다(1회용 정탐 스크립트만). 결과는
`docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md` 에 기록한다.

**Tech Stack:** Windows UI Automation, Python `uiautomation`(pip), 기존 backend venv(system Python313).

## Global Constraints

- 기존 FlowerNT RPA·`ProgramAutomator` 계약·factory·`ManualOnlyAutomator` 백업은 **건드리지 않는다**.
- Windows 전용. 백엔드가 도는 이 PC에서 수행한다.
- 프로덕션 의존성 추가는 이 단계에서 `uiautomation` 하나만(정탐 도구 겸 Phase 2 UIA 드라이버 후보).
  `pyautogui`/`opencv-python`(이미지 폴백)은 **추가하지 않는다** — 스파이크가 필요하다고 판정할 때 Phase 2에서.
- 스파이크 스크립트는 `scripts/` 밑 1회용. 실주문/실제 등록(제출) 클릭은 하지 않는다(조사만, 데이터 오염 금지).

---

### Task 1: UIA 정탐 도구 설치·확인

**Files:**
- (없음 — 환경 준비)

**Interfaces:**
- Produces: 이후 태스크가 `import uiautomation` 을 쓸 수 있는 상태.

- [ ] **Step 1: uiautomation 설치**

Run: `python -m pip install uiautomation`
Expected: `Successfully installed uiautomation-...` (또는 이미 설치됨).

- [ ] **Step 2: import·데스크톱 접근 확인**

Run:
```
python -X utf8 -c "import uiautomation as auto; print(auto.GetRootControl().Name)"
```
Expected: 예외 없이 루트(데스크톱) 이름 출력 → UIA가 이 PC에서 동작함.

---

### Task 2: RoseWeb 위치 확인·실행

**Files:**
- (없음 — 사장님 협조 + 실행 확인)

**Interfaces:**
- Produces: RoseWeb exe 절대경로, 실행 중인 창 제목(ClassName/Name) — Task 3~5·findings 문서가 사용.

- [ ] **Step 1: RoseWeb 설치본 찾기**

먼저 흔한 위치를 훑는다:
```
python -X utf8 -c "import glob;[print(p) for p in glob.glob('C:/Program Files*/**/*ose*eb*', recursive=True)[:20]]"
```
없으면 **사장님께 요청**: RoseWeb 실행파일 경로(또는 설치본). 받은 exe 경로를 기록한다.

- [ ] **Step 2: RoseWeb 실행·로그인 화면까지 띄우기**

exe를 실행(수동 또는 `os.startfile(<exe>)`)해 **로그인 창**을 화면에 띄운다.
Expected: 로그인 창이 보인다(아직 자동 로그인 안 함).

- [ ] **Step 3: 최상위 창 식별자 확인**

Run:
```
python -X utf8 -c "import uiautomation as auto; [print(w.ControlTypeName, repr(w.Name), w.ClassName) for w in auto.GetRootControl().GetChildren() if w.Name]"
```
Expected: RoseWeb 창이 목록에 보인다 → 창의 Name/ClassName 기록(findings "창 식별자").

---

### Task 3: 컨트롤 트리 덤프 스크립트 작성·로그인 화면 조사

**Files:**
- Create: `backend/scripts/roseweb_inspect.py` (1회용 정탐 도구)

**Interfaces:**
- Consumes: Task 2의 창 Name/ClassName.
- Produces: 임의 창의 컨트롤 트리를 콘솔에 덤프하는 `dump(window_name_substr)` — Task 4가 재사용.

- [ ] **Step 1: 정탐 스크립트 작성**

```python
"""RoseWeb 컨트롤 트리 덤프(1회용 정탐). 사용: python -X utf8 backend/scripts/roseweb_inspect.py "<창이름일부>" """
import sys
import uiautomation as auto


def _find_window(substr: str):
    for w in auto.GetRootControl().GetChildren():
        if substr.lower() in (w.Name or "").lower():
            return w
    return None


def dump(substr: str, max_depth: int = 12) -> None:
    win = _find_window(substr)
    if win is None:
        print(f"[!] '{substr}' 포함 최상위 창을 못 찾음")
        return
    print(f"[창] {win.ControlTypeName} name={win.Name!r} class={win.ClassName}")

    def walk(ctrl, depth):
        if depth > max_depth:
            return
        for c in ctrl.GetChildren():
            print("  " * depth,
                  c.ControlTypeName,
                  "name=", repr(c.Name),
                  "autoId=", repr(c.AutomationId),
                  "class=", c.ClassName)
            walk(c, depth + 1)

    walk(win, 1)


if __name__ == "__main__":
    dump(sys.argv[1] if len(sys.argv) > 1 else "")
```

- [ ] **Step 2: 로그인 창 덤프**

Run: `python -X utf8 backend/scripts/roseweb_inspect.py "<로그인창 이름 일부>"`
Expected: 아이디/비번 Edit 컨트롤과 로그인 Button이 트리에 보인다(name/AutomationId 포함).

- [ ] **Step 3: findings 문서에 로그인 흐름 기록**

`docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md` 의 "로그인" 절에 기록:
exe 경로 · 로그인 창 식별자 · 아이디 Edit(식별자) · 비번 Edit(식별자) · 로그인 Button(식별자) ·
로그인 성공 후 나타나는 창/컨트롤(= 로그인 완료 신호).

---

### Task 4: 주문입력 화면 조사 + RpaOrder 필드 매핑

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md`

**Interfaces:**
- Consumes: Task 3의 `roseweb_inspect.py`.
- Produces: findings 문서의 "필드 매핑" 표 + "미주소지정 컨트롤" 목록.

- [ ] **Step 1: 로그인 후 주문입력 화면 열기**

RoseWeb에 수동 로그인 → 신규 주문 입력 화면으로 이동한다.

- [ ] **Step 2: 주문 화면 컨트롤 덤프**

Run: `python -X utf8 backend/scripts/roseweb_inspect.py "<주문화면 창 이름 일부>"`
Expected: 주문 입력 칸들(Edit/ComboBox/DateTime 등)이 트리에 보인다.

- [ ] **Step 3: RpaOrder 필드 ↔ 컨트롤 매핑표 작성**

findings 문서에 표로 기록. 각 행 = `RpaOrder` 필드 → RoseWeb 컨트롤(식별자·ControlType) →
UIA 주소지정 가능? (Y/N). 대상 필드:
`product_name, quantity, price, delivery_at, delivery_place, receiver_name,
receiver_phone_number, ribbon_sender, ribbon_congratulations, card_message, sang_divi(상품분류)`.
UIA로 못 찾는(N) 칸은 "미주소지정 컨트롤" 목록에 별도 기재(= 이미지 폴백 후보).

---

### Task 5: 값 주입·포커스 강탈·제출 확인

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md`

**Interfaces:**
- Consumes: Task 4의 매핑표(주소지정 가능한 Edit 하나).
- Produces: findings 문서의 "값 주입 방식 · 포커스 강탈 · 제출/다이얼로그" 절.

- [ ] **Step 1: UIA로 한 칸에 값 주입 시도(마우스 안 건드리고)**

주소지정 가능한 Edit 하나를 골라 시도(예):
```
python -X utf8 -c "import uiautomation as auto; e=auto.EditControl(searchDepth=99, AutomationId='<id>'); e.GetValuePattern().SetValue('테스트'); print('OK')"
```
Expected: 해당 칸에 값이 들어감. `ValuePattern` 이 없으면 `SendKeys` 로 대체 가능한지 기록.

- [ ] **Step 2: 포커스 강탈 여부 관찰**

Step 1 실행 중 물리 마우스/포커스가 이동하는지 관찰해 기록(UIA ValuePattern은 보통 안 뺏음 →
사장님 PC 병행 사용 가능성 판정).

- [ ] **Step 3: 제출 버튼·확인 다이얼로그 식별**

주문 등록(제출) 버튼의 식별자와, 클릭 시 뜨는 확인 다이얼로그 유무·그 다이얼로그의 버튼
식별자를 기록. **실제로 등록 클릭은 하지 않는다**(조사만).

- [ ] **Step 4: is_program_running 신호 확정**

"RoseWeb가 로그인돼 주문입력 가능 상태"를 코드가 어떻게 판정할지 기록
(예: 특정 창/컨트롤 존재 여부).

---

### Task 6: findings 문서 마무리·방식 결정·커밋

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md`

**Interfaces:**
- Consumes: Task 1~5 기록 전체.
- Produces: Phase 2 계획 작성에 필요한 확정 정보 + 방식 결정(UIA 단독 / 하이브리드).

- [ ] **Step 1: 방식 결정 기록**

findings 문서 상단에 결론: 모든 대상 필드가 UIA 주소지정 가능 → **UIA 단독**.
일부 N → **하이브리드**(어느 칸이 이미지 폴백인지 명시). 포커스 강탈 여부도 결론에 포함.

- [ ] **Step 2: 미해결/리스크 기록**

DPI/해상도 의존, 앱 버전 변화 취약점, 자동 로그인 난이도 등 Phase 2가 주의할 점 기재.

- [ ] **Step 3: 커밋**

```bash
git add backend/scripts/roseweb_inspect.py docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md
git commit -m "spike(rpa): RoseWeb 컨트롤 트리·로그인/주문 흐름·필드매핑 정탐 결과"
```
(브랜치 `feature/roseweb-rpa`)

---

## 다음 단계 (이 계획 밖)

스파이크 완료 후 **Phase 2 구현 계획**(`docs/superpowers/plans/2026-07-23-roseweb-rpa-phase2.md`)을
작성한다. 그 계획은 findings 문서의 컨트롤 식별자·필드 매핑을 근거로:
`rpa/roseweb/mapping.py`(순수 로직 TDD) + `rpa/roseweb/automator.py`(UIA 우선 구현) +
factory/singleton/config 배선 + auto_submit=N 라이브 E2E 를 다룬다. **findings 없이는 그 계획을
구체적으로 쓸 수 없으므로 지금 쓰지 않는다.**

## Self-Review

- **Spec coverage:** 이 계획은 스펙의 "Phase 1 — 정탐 스파이크" 7개 조사항목을 Task 2~6에 전부 매핑
  (UI기술=Task3~4 관찰, 주소지정 가능성=Task4, 로그인 흐름=Task3, 필드매핑=Task4, is_program_running=Task5,
  제출/다이얼로그=Task5, 포커스 강탈=Task5). 스펙 Phase 2는 의도적으로 후속 계획으로 분리(범위 정직성).
- **Placeholder scan:** `<로그인창 이름 일부>` 등은 스파이크가 채우는 실측값이라 placeholder가 아니라
  "현장에서 확인할 입력". 코드 스텝(스크립트)은 전체 코드를 포함.
- **Type consistency:** 정탐 스크립트의 `dump()`/`_find_window()` 시그니처 일관.
