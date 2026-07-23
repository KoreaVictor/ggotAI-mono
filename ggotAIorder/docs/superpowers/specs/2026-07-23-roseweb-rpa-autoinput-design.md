# RoseWeb RPA 자동입력 설계

작성일: 2026-07-23
관련 코드: `backend/src/ggotaiorder/rpa/` (기존 FlowerNT 어댑터·팩토리·계약)

## Context (왜 하는가)

꽃집들은 주문 관리 프로그램으로 **FlowerNT · RoseWeb · 기타SW 중 하나**를 선택해 쓴다.
현재 ggotAI의 RPA 자동입력은 **FlowerNT(웹 기반)만** 실제 구현돼 있고, RoseWeb는
스텁(`rpa/adapters.py`의 `RoseWebAutomator`)만 있어 항상 `manual` 백업으로 흐른다.

RoseWeb를 쓰는 꽃집도 주문이 자동 입력되게 하려면 RoseWeb 어댑터를 실제로 구현해야 한다.
**RoseWeb는 Windows 데스크톱 앱**이라(웹인 FlowerNT와 근본적으로 다름), Playwright/CDP를
쓸 수 없고 데스크톱 GUI 자동화가 필요하다. 목표: RoseWeb 사용 꽃집에서도 수집된 주문이
사람 손 없이 RoseWeb에 입력되게 한다(FlowerNT와 동일한 파이프라인 하류에 붙는다).

## 요건 (확정)

- RoseWeb = **Windows 데스크톱 앱**. 이 개발 PC에 설치/조사 가능, 테스트 로그인 있음.
- 백엔드가 **실행 → 로그인 → 주문입력**까지 전자동으로 처리(FlowerNT와 동일한 자율성).
- 기존 `ProgramAutomator` 계약·`rpa.factory`·`singleton_macro`·`ManualOnlyAutomator` 백업을
  **그대로 재사용**한다. RoseWeb 어댑터만 채운다.
- 꽃집은 세 프로그램 중 **하나만** 쓰므로 FlowerNT와 RoseWeb가 한 PC에서 동시 구동될 일은 없다.

## 아키텍처

### 재사용하는 기존 계약 (변경 없음)
- `rpa/automator.py` — `ProgramAutomator` Protocol: `is_program_running()` + `input_order(RpaOrder)`.
- `rpa/models.py` — `RpaOrder`(18필드: 고객·상품·수량·가격·배송일시·받는분·주소·리본·카드·sang_divi 등).
- `rpa/adapters.py` — `ManualOnlyAutomator`: 자동화 실패/미지원 시 백업 경로. **RoseWeb 자동화가
  실패하면 여기로 흘러 주문은 유실되지 않는다**(기존 안전망 유지).
- `rpa/factory.py` — `program_type`으로 어댑터 선택(이미 `roseweb` 분기 존재).
- `rpa/singleton_macro.py` — 어댑터 수명주기 관리.

### 신규 구조 (FlowerNT `rpa/flowernt3/`와 대칭)
```
rpa/roseweb/
  __init__.py
  mapping.py     # 순수 로직 시임: RpaOrder → RoseWeb 입력값. 오프라인 TDD 대상.
  automator.py   # RoseWebAutomator: 실행·로그인·주문화면 이동·UIA 값주입·(옵션)등록.
```
- `rpa/adapters.py`의 기존 `RoseWebAutomator` **스텁은 삭제**하고 `rpa/roseweb/automator.py`로 대체
  (FlowerNT가 `flowernt3/automator.py`에 있는 것과 대칭). `ManualOnlyAutomator`는 `adapters.py`에 유지.
- `rpa/factory.py`의 `roseweb` 분기를 신규 `RoseWebAutomator`로 연결하고 **`auto_submit`를 전달**
  (현재 roseweb 분기엔 auto_submit이 빠져 있음).

## 자동화 방식: 스파이크 먼저 → UIA 우선 하이브리드

데스크톱 앱은 컨트롤이 UI Automation(UIA)에 노출되는지에 따라 자동화 성패가 갈린다.
RoseWeb의 실물을 확인하기 전엔 필드 단위 구현을 확정할 수 없으므로, **1단계를 정탐 스파이크**로 둔다.

### Phase 1 — 정탐 스파이크 (산출물 = 조사 문서, 프로덕션 코드 아님)

이 PC에서 RoseWeb를 띄우고 UIA 검사기(Python `uiautomation` / `pywinauto`의
`print_control_identifiers`, 또는 Accessibility Insights)로 다음을 확정한다:

1. UI 기술 스택(.NET WinForms/WPF, 네이티브 Win32, Electron/CEF, 기타)
2. 로그인 창·주문 화면의 컨트롤이 UIA로 **주소지정 가능한지**(name/AutomationId/ControlType).
   불가한 컨트롤은 어느 것인지(이미지 폴백 후보).
3. 실행 → 로그인 순서: exe 경로, 창 제목, 아이디/비번 입력 칸, 로그인 버튼.
4. 주문입력 화면 흐름과 **각 컨트롤 ↔ `RpaOrder` 필드 매핑**
   (상품명·수량·가격·배송일시·받는분·받는분 연락처·배송지·리본(보내는분/경조사)·카드메시지·상품분류).
5. `is_program_running()` 판정 신호(로그인됨 + 주문화면 진입 가능 상태).
6. 등록(제출) 컨트롤과 확인 다이얼로그 유무.
7. **UIA가 물리 포커스/마우스를 뺏지 않고 동작하는지**(사장님 PC 병행 사용 가능성 판정).

산출물: `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md`.
이 결과로 Phase 2의 UIA 단독 여부 / 이미지 폴백 범위 / 필드 매핑이 확정된다.

### Phase 2 — 구현

`rpa/roseweb/mapping.py` (순수 로직, TDD)
- `RpaOrder`를 RoseWeb 입력값으로 변환: 상품분류/채널 매핑, 가격 정규화, 배송일시 분해,
  각 필드의 문자열화. FlowerNT `flowernt3/mapping.py`(`order_to_fields`, `resolve_sang_divi`,
  `normalize_price`, `split_delivery_datetime`)와 같은 역할·같은 테스트 방식.

`rpa/roseweb/automator.py` (`RoseWebAutomator`, UIA 우선)
- `is_program_running()`: RoseWeb 프로세스/창 존재 + 로그인·주문화면 도달 가능 판정.
  미기동이면 exe를 실행(스파이크가 정한 경로)하고 자동 로그인, 실패 시 False(→ manual 백업).
- `input_order(order)`: 주문화면으로 이동 → `mapping`이 만든 값을 **UIA로 컨트롤에 주입**
  (`ValuePattern.SetValue`/`InvokePattern` 등 물리 마우스 없이). UIA로 안 되는 칸만 이미지/키보드
  폴백. `auto_submit`이면 등록 컨트롤 클릭(+ 확인 다이얼로그 처리), 아니면 채우기까지만.

### 설정·배선
- 신규 config: RoseWeb exe 경로·창 식별자 등(스파이크 결과 반영). `flowernt_debug_port`·
  `rpa_profile_dir`·`rpa_chrome_path`(CDP 전용)는 RoseWeb엔 무의미하므로 factory/singleton에서
  program_type에 맞는 파라미터만 넘기도록 정리.
- `setting_info.rpa_*`(program_type='roseweb', url, login_id, login_password, enabled, auto_submit)는
  **기존 스키마 그대로** 사용(로그인 자격증명은 이미 암호화 저장됨).

## 안전장치 (FlowerNT 관례 승계)

- **auto_submit 기본 N(채우기만)** 으로 출발 → 실주문으로 검증 후 사장님이 Y 전환(단계적 롤아웃).
- 자동화 실패/미기동 → `ManualOnlyAutomator` 백업(기존). 주문 유실 없음.
- 포커스 강탈 최소화: UIA 우선(값 주입은 물리 마우스 미사용), 이미지 폴백은 꼭 필요한 칸으로 국한.
  이미지 폴백이 넓게 필요하다고 스파이크가 판정하면, 사장님 PC 병행 사용 충돌을 별도 논의.

## 테스트 전략

- `rpa/roseweb/mapping.py` → **오프라인 단위테스트**(FlowerNT mapping 테스트와 동일).
- `rpa/roseweb/automator.py`(실제 UIA 구동) → **이 PC에서 라이브 E2E**(FlowerNT도 동일하게
  단위테스트 불가 영역이라 라이브로 검증). 스파이크 문서의 컨트롤 식별자를 근거로 채운다.

## 의존성

- UIA 드라이버: `uiautomation`(또는 `pywinauto`) 추가. Windows 전용(백엔드가 Windows라 OK).
- 이미지 폴백 필요 시(스파이크 판정): `pyautogui` + `opencv-python`. **필요 확정 전엔 추가하지 않음.**

## 범위 밖 (YAGNI)

- 기타SW(etc) 자동화는 이번 범위 아님(계속 ManualOnly).
- 멀티 프로그램 동시 구동(한 꽃집은 하나만 씀).
- RoseWeb 자격증명 입력 UI 신설(기존 ggotAIya 환경설정 화면 재사용).

## 검증 (완료 기준)

- Phase 1: 스파이크 문서에 위 7개 항목이 모두 채워짐(특히 UIA 주소지정 가능 여부·필드 매핑·
  포커스 강탈 여부).
- Phase 2:
  - `mapping.py` 단위테스트 통과(백엔드 전체 그린 유지).
  - 이 PC 라이브 E2E: RoseWeb 미기동 상태에서 `input_order` 호출 → 실행·로그인·주문화면·
    전 필드 채움까지 관통(auto_submit=N). 이어 auto_submit=Y로 등록까지 1건 확인.
  - 자동화 강제 실패 시 `manual` 백업으로 흐르는지 확인(주문 유실 없음).
