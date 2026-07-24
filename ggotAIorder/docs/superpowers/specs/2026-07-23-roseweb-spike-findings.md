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

## 7. Task 1 실측 갱신 (2026-07-23, 라이브)

- **신규주문 열기 = `F2`(주문관리 `TFmJumun`) → `Insert`(입력 `TFmju1inp`)**. 프로그래밍 재현 성공.
  → `layout.OPEN_NEW_ORDER` = 메인창 SetFocus 후 `{F2}` → 대기 → `{Insert}`.
- **식별자 불안정 확정**: 폼을 다시 열면 같은 칸 AutomationId 가 바뀜(788512→265002 …). **위치는 안정**
  → 좌표(폼 기준 상대) addressing 유지가 맞다.
- **⚠️ 상품명은 직접 타이핑 불가 — lookup 팝업**: 상품명 칸에 입력하면 `상품코드선택`(class `TFmCodesel`)
  팝업이 뜬다. RoseWeb 는 고정 상품마스터(동양란·근조3단화환·꽃다발·꽃바구니 … 코드 AA-01/BB-05)에서
  **검색→선택**. 따라서 `PRODUCT_DIRECT_TYPE = False`.
  - **결정(사장님): 상품명으로 팝업 검색 → 자동 선택, 매칭 안 되면 직접입력**(보류로 빠지지 않음).
    → Phase 2 Task 5 에 상품 서브루틴 추가: 상품명칸 포커스→팝업 대기(`TFmCodesel`)→검색어 입력→`검색`→
    첫/최유사 항목 `선택`; 결과 없으면 직접입력 경로(팝업에서 원문 입력 방식은 Task5 실측 확정).
- **⚠️ 안전 주의**: lookup/검증 칸에 블라인드 타이핑하면 팝업·`#32770 '고객Error'` 대화상자가 연쇄로 뜬다.
  필드 매핑은 한 칸씩(팝업 뜨면 즉시 닫고 기록), 또는 데이터 없는 깨끗한 캡처+좌표 대조로 한다.
  리셋은 `roseweb.exe` 강제종료+재실행(자동 로그인, 저장 안 한 것뿐이라 무손실).
- ~~**남은 Task 1**: 비-lookup 텍스트 필드의 폼기준 상대좌표 실측~~ → **8. 에서 완료(2026-07-24).**

## 8. Task 1 완료 (2026-07-24, 라이브) — `layout.py` 확정

타이핑을 한 번도 하지 않고(=팝업 위험 0) 끝냈다. 방법 = **컨트롤 사각형 덤프 + 폼 스크린샷 대조**.
`roseweb_inspect.py dump` 를 확장(상대좌표·부모 사각형·조상 클래스·offscreen/enabled → JSON).

- **⚠️ Delphi `TGraphicControl` 은 UIA 에 아예 안 보인다.** 라벨(`TLabel`) 0개, **하단 저장/취소
  버튼도 0개**. 창 핸들이 없어서다. 그래서
  - 라벨-칸 짝짓기로 필드를 식별하려던 방법은 불가 → **폼을 캡처해 눈으로 대조**했다.
  - **저장/취소는 컨트롤로 못 찾는다 → 좌표 클릭 필수**(`SAVE_BUTTON_POS`/`CANCEL_BUTTON_POS`,
    다른 상수와 달리 **중심** 좌표). 저장 x480~548 · 취소 x723~791, 둘 다 y809~831.
  - 반면 주문상태 라디오(정상/보류/취소)는 `TGroupButton` 이라 UIA 에 보인다.
- **⚠️ 그리드 유령 행**: 상품 그리드는 화면에 3줄만 보이는데 UIA 에는 화면 밖 행의 편집 컨트롤까지
  나온다(그리드 패널 자식 61개 중 **42개**). 이것들이 배달장소·경조사어 등 아래쪽 실제 칸과 위치가
  겹친다. `IsOffscreen` 은 **전부 False 라 쓸 수 없고**, 조상 클래스도 전부 `TPanel` 이라 무의미.
  **판별법 = 부모(그리드 패널, dy=232 1020x131) 세로 영역을 벗어난 컨트롤은 버린다.** 이 규칙으로
  113개 → 71개(진짜 칸)로 정확히 갈린다.
- **좌표 안정성 확인(계획서 Step 2)**: 폼을 Esc 로 닫고 F2→Insert 로 다시 열어 재덤프 →
  **71개 전부 동일**, 차이는 dy 1px 뿐(창 위치 반올림). 창 절대위치는 바뀐다(421,113 ↔ 446,109).
- **오인식 여유**: 13개 목표 필드 전부 실측 좌표와 **거리 0** 으로 매칭되고, 두 번째로 가까운
  컨트롤까지는 **최소 26px**. → `FIELD_MATCH_RADIUS = 12`. (계획서 locator 기본값 60은 너무 넓다 —
  칸이 사라졌을 때 조용히 옆 칸을 집는다. Task 3 에서 12로 쓸 것.)
- 산출물: `backend/src/ggotaiorder/rpa/roseweb/layout.py` + 형태 검증 테스트
  `backend/tests/test_rpa_roseweb_layout.py`(플레이스홀더 잔존·키 불일치 방지).

## 9. Task 5 실측 (2026-07-24) — 입력 방식 확정

**§7 의 "상품명은 직접 못 친다(PRODUCT_DIRECT_TYPE=False)"는 오판이었다.** 상품명 칸은 자유
입력이고 `{Tab}` 확정 후에도 값이 남으며, 다른 칸으로 옮겨도 유지된다. 팝업도 안 뜬다.
정확한 마스터 상품명('동양란')을 넣어도 **상품코드는 비어 있다** — 코드를 채우려면 돋보기
lookup 이 필요하지만 채우기에는 지장 없다. → `PRODUCT_DIRECT_TYPE = True`.

- **⚠️ 입력은 SendKeys 가 아니라 클립보드 붙여넣기로 한다.** 키를 하나씩 보내면 한글이 깨진다
  (실측: '김발주'→'주癰償', '축 개업'→'내?개업'). DB 연동 칸의 자동완성과 IME 조합이 엉키는
  것으로 보이며, `TdxDBPickEdit`(경조사어·보내는이)에서 특히 심했다. 날짜 칸도 타이핑하면
  마스크가 어긋나고('2026-07-25'→'2026-  -07') 붙여넣기는 정확하다.
  - 확정 절차 = `SetFocus` → `{Ctrl}a` → `SetClipboardText` → `{Ctrl}v` → `{Tab}`.
  - **`{Ctrl}a` 뒤에 `{Delete}` 를 넣지 말 것** — 조합 잔여물이 남아 '?김발주' 가 됐다.
    선택 상태에서 그대로 덮어쓰면 깨끗하다.
  - 붙여넣기라 SendKeys 의 `{}` 이스케이프는 **하면 안 된다**(문자 그대로 들어간다).
  - 클립보드는 사장님 것을 빌려 쓰는 것이라 끝나면 되돌린다.
- **⚠️ RoseWeb 의 확인·경고창은 Delphi `TMessageForm` 이다(`#32770` 아님).** 이게 뜨면 주문폼이
  통째로 **비활성(`IsEnabled=False`)** 이 되어 이후 입력이 전부 허공으로 간다. `#32770` 만
  보면 "대화상자 없음"으로 오판한다(조사 중 실제로 그랬다). 본문 텍스트는 Delphi 라벨이라
  **UIA 에 안 보이고** 제목·버튼 이름만 읽을 수 있다.
- **⚠️ 폼이 열려 있는데 `Insert` 를 또 누르면 같은 좌표에 폼이 겹쳐 뜬다.** 어느 쪽에 값이
  들어갔는지 알 수 없다. → 폼이 이미 열려 있으면 자동입력을 하지 않는다(사장님이 작업 중일
  수도 있으므로 `is_program_running()` 이 False 를 돌려 백업·재시도 경로로 보낸다).
- 참고: 창을 `SetTopmost(True)` 로 올려두면 **모달 대화상자보다 위에 뜬다**. 조사용 스크립트가
  이걸 되돌리지 않아 "클릭이 안 먹는" 현상으로 한참 헤맸다.
- **라이브 결과(auto_submit=N)**: 13개 필드 전부 정확히 채워짐(발주자·휴대폰·상품명·단가·수량·
  배달일자·배달시간·배달장소·받는분·핸드폰·경조사어·보내는이·카드 2줄). 소요 ~19초.
  클립보드 원상복구 확인.

### 저장(auto_submit=Y) 전에 풀어야 할 것

- **'배달일자를 확인하세요' 대화상자**가 폼을 닫을 때 떴다. 배달일자를 2026-07-25(익일)로
  넣었는데도 나온다 — 검증 규칙을 모른다. 저장 시에도 막을 가능성이 높다.
- **금액·총합계금액이 0** 이다(단가 55,000 × 수량 2 인데). 저장 시 계산되는지 확인 필요.
- **상품코드가 빈 값**이라 저장이 거부될 수 있다. 거부되면 돋보기 lookup(`TFmCodesel`)
  서브루틴이 필요해진다.
- 저장 버튼은 UIA 에 없어 좌표 클릭이다. 취소 버튼 좌표 클릭은 라이브에서 동작 확인함.
