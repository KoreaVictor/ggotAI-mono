# RoseWeb RPA — Phase 1 정탐 스파이크 결과

수행일: 2026-07-23. 대상 PC에서 실물 조사(조사만, 주문 저장/등록 안 함).
도구: `uiautomation`(설치 완료), `backend/scripts/roseweb_inspect.py`.

## 결론 (Phase 2 방식 결정)

- **RoseWeb = 화원박사 ROSEWeb Network build(208.5.1)** (벤더 (주)뉴런시스템).
  **Delphi VCL + DevExpress(dx*) + RxLib** 데스크톱 앱. 상단 배너만 내장 IE, **주문 폼은 네이티브 Delphi**.
- **자동화 방식 = UIA로 필드 찾기 + `SetFocus()`+`SendKeys()`로 입력.** (하이브리드지만 이미지 폴백은
  현재 불필요 — 모든 입력칸이 UIA에 보임.) `ValuePattern.SetValue`는 불가(칸이 PaneControl로 노출).
- **주의: SendKeys는 실제 키 입력이라 입력 순간 키보드 포커스를 점유**한다(FlowerNT의 CDP처럼
  완전 백그라운드는 아님). 사장님이 동시에 타이핑하면 충돌. 주문 처리 순간(수 초)만.
- **식별자 불안정** → 필드 addressing 은 ID/Name 이 아니라 **좌표(폼 기준) 또는 탭순서**로 잡아야 한다.
  Phase 2에서 탭순서 매핑을 실측으로 고정할 것.

## 1. 실행·로그인

- exe: `C:\Roseweb\prog\roseweb.exe` (WorkingDir=`C:\Roseweb\prog` 로 실행 — OCX/DLL 로드).
- **자동 로그인**(관리자). 별도 로그인 입력 불필요.
- 메인 창: class `TFmMain`, 상단 바(1920x245). 상태바에 IP `192.168.0.5`, 사용자 `박선희/01077051674`,
  `관리자`, 벤더 표기. CTI 박스 = `AfxOleControl42`(ActiveX, UIA 불투명). 상단 배너 = 내장 IE
  (`Internet Explorer_Server`, `http://swinfo.roseweb.co.kr/top_banner.htm`).
- `is_program_running` 신호 후보: PID의 `TFmMain` 창 존재(로그인 완료 = 관리자 표기). 주문 가능 상태는
  `TFmju1inp` 창을 열 수 있는지로 판정.

## 2. 주문 입력 폼

- 메뉴로 신규 주문 → 창 **`주문판매관리 세부내역` (class `TFmju1inp`, ~1076x854)** 이 열림.
  (동시에 `주문판매관리 (전체보기)` `TFmJumun` 목록 창도 뜸.)
- UIA 가시성: **EditControl 35 + 체크박스 3 + 라디오 3 + 버튼 3**. 컨트롤 클래스: `TdxDBEdit`,
  `TdxDBPickEdit`(돋보기 검색), `TdxDBLookupEdit`, `TdxDBDateEdit`, `TdxCurrencyEdit`,
  `TRxDBCalcEdit`(금액 계산), `TdxDBMemo`(카드/요구사항), `TEdit`/`TdxEdit`.
- Name 대부분 비어 있음(있으면 현재 값). AutomationId = 숫자 핸들(재실행 시 불안정).

## 3. 필드 매핑 (화면 캡처 기준 → RpaOrder)

| RoseWeb 화면 항목 | RpaOrder 필드 | 비고 |
|---|---|---|
| 상품명 (상품 그리드 1행) | product_name | 상품코드 돋보기=상품검색. 직접 타이핑 가능성 Phase2 확인 |
| 단가 | price | 금액=단가×수량 자동계산(TRxDBCalcEdit) |
| 수량 | quantity | |
| 배달일자 + 배달시간 | delivery_at / delivery_at_text | TdxDBDateEdit + 시간칸 |
| 배달장소 | delivery_place | 우편번호·신주소검색 별도 |
| 받는분 | receiver_name | |
| 핸드폰 / 배달전화 | receiver_phone_number | |
| 경조사어 | ribbon_congratulations | 漢/SMS/경조사어복사 버튼 있음 |
| 보내는이 | ribbon_sender | |
| 카드내용 (TdxDBMemo) | card_message | |
| 발주자 / 휴대폰 | customer_name / customer_phone_number | 회사명·일반고객·대표자 |
| (상품분류) | sang_divi | 매출구분 또는 상품코드 검색으로 결정 — Phase2 확인 |

- 주문상태 라디오: 정상/보류/취소. 하단 버튼: **저장 / 저장&입금 / 저장&발주 / 취소**.
- 제출은 `저장`(또는 `저장&발주`). auto_submit=N 이면 채우기까지, Y 면 저장 클릭까지. **스파이크에선 저장 안 함.**

## 4. 쓰기(입력) 검증

- 카드내용 메모(class `TdxDBMemo`, UIA=PaneControl)에 `SetFocus()`+`SendKeys('RPA_WRITE_TEST')`
  → 값 입력 확인 → `{Ctrl}a`+`{Delete}` 로 삭제 확인. **ValuePattern은 미지원**(PaneControl).
- 즉 입력 경로 = 대상 컨트롤 `SetFocus()` → `SendKeys(값)` → 필요시 `{Tab}`/`{Enter}` 로 커밋.

## 5. Phase 2 가 주의할 점 / 미해결

- **식별자 불안정**: 좌표는 폼 이동/해상도에 취약. 가장 견고한 후보 = **탭순서 순회**
  (첫 칸에 SetFocus → 알려진 순서로 Tab+SendKeys). 탭순서를 실측 매핑해야 함(Phase2 첫 태스크).
- **DevExpress 돋보기/lookup**(상품코드·고객): 자유 타이핑이 아니라 검색창을 열어 선택해야 할 수 있음.
  상품명을 상품명 칸에 직접 타이핑해도 되는지 Phase2에서 확인.
- **DB-aware 커밋**: 텍스트는 SendKeys 로 들어가나, 날짜/금액/lookup 은 `{Tab}`/`{Enter}` 로
  확정해야 반영될 수 있음.
- **포커스/키보드 점유**: 입력 순간 사장님 PC 조작과 충돌 가능(운영 트레이드오프).
- **자동 실행 창 정리**: 신규주문 시 목록 창(`TFmJumun`)도 열림 — 어느 창을 대상으로 할지(활성
  `TFmju1inp`) 명확히 잡을 것.

## 6. 아키텍처 반영 (Phase 2 구현 방향)

- 신규 `rpa/roseweb/`:
  - `mapping.py`(순수 로직 TDD): RpaOrder → 각 칸에 넣을 문자열(가격/날짜/시간 포맷, 상품분류 결정).
  - `automator.py`(`RoseWebAutomator`): exe 실행·`is_program_running`(TFmMain/TFmju1inp 판정)·
    주문 폼 열기·**탭순서(또는 좌표) 기반 SetFocus+SendKeys 입력**·auto_submit 시 저장 클릭.
- factory 의 `roseweb` 분기에 `auto_submit` 전달, `adapters.py` 스텁 제거.
- config: `ROSEWEB_EXE_PATH`(기본 `C:\Roseweb\prog\roseweb.exe`) 등.
- 의존성: `uiautomation`(추가 완료). 이미지 폴백 불필요 → `pyautogui`/`opencv` 미추가.
