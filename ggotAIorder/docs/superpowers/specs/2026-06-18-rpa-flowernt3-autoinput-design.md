# RPA 자동입력 (FlowerNT3) + 멀티 프로그램 설계

- 날짜: 2026-06-18
- 브랜치(예정): `feature/rpa-autoinput`
- 상태: 설계 확정 대기

## 1. 배경 / 목표

ggotAI 파이프라인은 통화 → STT → Gemini 추출 → `order_details`(rpa_status='ready') → `rpa.enqueue`까지
동작하지만, **마지막 단계인 "꽃집 관리 프로그램 자동입력(RPA)"이 미구현**이다.
`rpa/automator.py`의 `WindowsProgramAutomator`가 스텁이라 (`is_program_running`은 항상 False,
`input_order`는 `NotImplementedError`) 모든 주문이 백업 경로('manual')로만 흐른다.

목표: 실제 관리 프로그램에 주문을 자동 입력하고 `rpa_status`를 `success`로 마킹한다.
대상 프로그램은 **웹 기반 FlowerNT3**(`https://www.flowernt.com`, Chrome)이며,
꽃집마다 쓰는 프로그램이 다르므로(FlowerNT / Roseweb / 기타) **프로그램별 어댑터 + 샵별 설정** 구조로 만든다.

### 비목표 (이번 범위 제외)
- Roseweb / 기타 어댑터의 **실제 입력 로직** — 스키마·팩토리·스텁만. 선택 시 안전하게 'manual' 백업.
- 지점 선택 / 2차 인증(OTP) 로그인 흐름 — 대상 프로그램에 불필요(사용자 확인).
- 수량(quantity) 입력 — FlowerNT3에 대응 칸 없음. 무시(사용자 확인).

## 2. 핵심 결정 (사용자 확인 완료)

| 항목 | 결정 |
|---|---|
| 자동화 기술 | Playwright (sync API), 웹 DOM 직접 입력 |
| 브라우저 제어 | 전용 프로필 Chrome + CDP(`connect_over_cdp`) 연결 |
| 저장 | **완전자동** — 폼 입력 후 `submit_reg()`(등록)까지 자동 실행 |
| 수량 | 무시 |
| 멀티 프로그램 | `setting_info`에 샵별 프로그램 설정 저장, 어댑터 팩토리로 분기 |
| 우선 구현 | FlowerNT3 어댑터 (Roseweb/기타는 스텁) |
| 자격증명 | `core.crypto`(AES-256-CBC) 암호화 저장, 프론트엔 마스킹(write-only) |
| 지점/OTP | 불필요 |

## 3. 아키텍처

기존 `ProgramAutomator`(Protocol) / `singleton_macro.enqueue` / 3-state(success/manual/fail) /
백업 경로는 **계약 유지**. 변경점은 (a) 어댑터 구현체 추가, (b) 팩토리로 자동 선택, (c) 샵 설정 로딩.

```
singleton_macro.enqueue(order_detail_id)
  └─ automator = build_automator(shop_settings)      # 신규 팩토리
       ├─ FlowerNt3Automator(url, login_id, login_pw)   # 이번 구현
       ├─ RoseWebAutomator(...)                          # 스텁 → 'manual'
       └─ None/etc → ManualOnlyAutomator                 # is_program_running=False
  └─ if automator.is_program_running(): automator.input_order(order)  # 기존 흐름
```

### 3.1 브라우저 세션 모델 (전용 프로필 + CDP)

- **상시 Chrome 1개**를 전용 프로필로 기동:
  `chrome.exe --user-data-dir=<rpa_profile_dir> --remote-debugging-port=<port> --no-first-run --no-default-browser-check`
  - `install_autostart.ps1`(또는 신규 헬퍼)에 이 Chrome 기동을 추가해 로그인 후 부팅 시 자동 기동.
  - 세션(쿠키)이 프로필에 영구 저장 → 자동 로그인 실패 시에도 수동 로그인 1회로 복구 가능.
- 자동화는 매 주문마다 `connect_over_cdp("http://localhost:<port>")`로 **붙었다 떼는** 방식.
  - 이유: sync Playwright 객체는 생성 스레드에 귀속되는데, `singleton_macro`가
    `asyncio.to_thread`로 자동화를 호출하므로(워커 스레드가 매번 다를 수 있음) 장기보관 객체 공유가 위험.
    각 `to_thread` 호출 안에서 연결→작업→해제를 완결하면 안전하다. 실제 Chrome/세션은 독립 유지.
  - 비용: 호출당 CDP 연결 오버헤드(~수백 ms). 주문량 대비 무시 가능.

### 3.2 어댑터 계약 (기존 Protocol 확장 없음)

```python
class ProgramAutomator(Protocol):
    def is_program_running(self) -> bool: ...
    def input_order(self, order: RpaOrder) -> None: ...
```

`FlowerNt3Automator`는 생성자에서 `url, login_id, login_pw, debug_port, channel_map`을 받는다.
- `is_program_running()`:
  1. CDP 연결 가능?  아니면 False.
  2. FlowerNT 메인 도달 + 로그인 상태?  로그아웃이면 저장된 id/pw로 **자동 로그인** 시도.
  3. 로그인 성공 → True / 자격증명 없음·실패 → False(→ 백업 'manual').
- `input_order(order)`:
  1. `flowernt3Main` 프레임을 주문입력(`order/order3.asp`)으로 새로고침 → 빈 신규폼(`order_form2`).
  2. 필드 채움(§4 매핑).
  3. `submit_reg()`(등록) 실행. JS confirm/alert는 `page.on("dialog")`로 자동 수락.
  4. 검증경고 alert가 뜨면 입력 실패로 간주 → 예외 발생 → (singleton_macro가) 백업+'fail'.
     정상 등록 시 정상 반환 → 'success'.

### 3.3 팩토리 / 샵 설정 로딩

- 신규 `rpa/program_settings.py`(또는 `repository.py` 확장): `setting_info`에서 샵의 RPA 설정 조회.
  비밀번호는 `core.crypto.decrypt(rpa_login_password, aes_key)`로 평문 복원(백엔드 내부에서만).
- 신규 `rpa/factory.py`: `build_automator(settings) -> ProgramAutomator`.
  - `rpa_enabled='N'` 또는 type 미설정 → `ManualOnlyAutomator`(항상 백업).
  - `flowernt` → `FlowerNt3Automator`, `roseweb` → `RoseWebAutomator`(스텁: is_program_running=False).
- `singleton_macro.enqueue` 기본 automator를 팩토리 결과로 대체(테스트 위해 주입 인자는 유지).

## 4. FlowerNT3 필드 매핑 (실측 완료)

폼 위치: iframe `flowernt3Main` = `https://www.flowernt.com/order/order3.asp`, 폼 `order_form2`.
페이지 인코딩은 EUC-KR(터미널 표시만 깨짐, Playwright 입력은 정상). 모든 칸은 `name` 기준 안정.

| RpaOrder | FlowerNT3 (name) | 입력 방식 |
|---|---|---|
| channel | `order_divi` (radio) | 채널맵 → 라디오 선택(§4.1) |
| customer_name | `customer_name` | fill |
| customer_phone_number | `customer_hp` | fill |
| product_name | `sang_name` | fill |
| quantity | — | **무시** |
| price | `sang_money` | 숫자만 추출 후 fill |
| delivery_at / delivery_at_text | `hope_date` + `hope_time` | 날짜→`hope_date`(YYYY-MM-DD), 시각→`hope_time` |
| delivery_place | `receive_address1` | 자유텍스트 fill (우편번호 검색 생략) |
| receiver_name | `receive_name` | fill |
| receiver_phone_number | `receive_hp` | fill |
| ribbon_congratulations | `event_txt` (경조문구) | fill *(구현 시 라이브 확인)* |
| ribbon_sender | `event_txt` 합치기 또는 `people_txt` | *(구현 시 확인)* |
| card_message | `msg_text` (textarea) | fill |

저장 버튼: `submit_reg()`(등록=신규저장). (`submit_modify()`는 수정이므로 사용 안 함.)
`order_code`(주문코드)는 신규폼 진입 시 자동 발번된다.

### 4.1 채널 → order_divi 매핑 (기본값)

`order_divi` 라디오 6종(인터넷/전화/한솔/내방/프로그램/기타 — **정확 라벨·순서는 구현 시 라이브 폼에서 확정**).
사용자 지정 매핑:

| RpaOrder.channel | FlowerNT3 주문구분 |
|---|---|
| 전화 / 가게전화 / 핸드폰 | 전화 |
| 가게음성 | 매장판매 |
| 쇼핑몰 | 홈페이지 |
| 인터라넷 | 프로그램간 |
| (그 외/미상) | 기타 |

라디오는 깨진 value 대신 **라벨 텍스트 매칭 또는 인덱스**로 선택한다(인코딩 안전).

## 5. 데이터 / 설정 변경 (setting_info)

기존 `shopping_mall_password`/`intranet_password` 패턴을 그대로 따른다
(암호화 저장, RPC 별도 인자, 평문 미반환·`has_*` 불리언만 노출).

### 5.1 마이그레이션 `20260618000100_rpa_program_settings.sql`
`setting_info`에 컬럼 추가:

| 컬럼 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `rpa_program_type` | varchar(20) | `''` | `flowernt` / `roseweb` / `etc` |
| `rpa_program_url` | text | null | 접속 주소 |
| `rpa_login_id` | varchar(100) | null | 로그인 아이디 |
| `rpa_login_password` | text | null | **암호화** 저장(iv_hex:ct_b64) |
| `rpa_enabled` | varchar(1) | `'N'` | RPA on/off |
| `rpa_auto_submit` | varchar(1) | `'Y'` | 등록까지 자동 / 채우기만 |

`get_settings` RPC: 위 컬럼 반환하되 비밀번호는 `has_rpa_login_password` 불리언만.
`save_settings` RPC: `p_rpa_login_password text default null` 인자 추가(미전달 시 기존값 보존),
나머지 컬럼은 `p_settings` jsonb에서 읽어 update/insert.

### 5.2 config.py
- `rpa_profile_dir: Path` (기본 `C:\ggotAI\rpa_profile`, env `RPA_PROFILE_DIR`).
- `flowernt_debug_port: int` (기본 9222, env `RPA_DEBUG_PORT`).

## 6. 프론트엔드 (설정 UI)

설정 화면에 "관리 프로그램(RPA)" 섹션 추가:
- 프로그램 종류(드롭다운: FlowerNT / Roseweb / 기타), 웹주소, 아이디, 비밀번호(마스킹·write-only),
  RPA 사용(on/off), 자동등록(on/off).
- 비밀번호는 프론트에서 crypto-js로 암호화하여 `save_settings`의 비번 인자로 전달(기존 패턴 동일).
- 조회 시 `has_rpa_login_password`로 "설정됨" 표시, 평문은 받지 않음.
- 타입 동기화(types-in-sync 가드) 갱신.

## 7. 에러 / 복구 흐름

| 상황 | 결과 |
|---|---|
| Chrome 미기동 / CDP 연결 실패 | `is_program_running=False` → 백업 + **manual** |
| 로그아웃 + 자격증명 없음/로그인 실패 | False → 백업 + **manual** |
| 로그인 OK, 입력 중 예외/검증경고 | `input_order` 예외 → singleton_macro가 백업 + **fail** |
| 정상 등록 | **success** |
| `rpa_enabled='N'` | ManualOnlyAutomator → 항상 백업 + **manual** |

기존 `enqueue`의 전역 try/except·싱글턴 락·주문별 알림은 그대로 동작.

## 8. 테스트 전략 (TDD)

- **순수 함수 단위테스트(브라우저 불요):**
  - 필드 매핑: `RpaOrder` → `{name: value}` dict.
  - 채널맵: channel → order_divi 라벨.
  - 가격 정규화(숫자만), 날짜/시각 분리(delivery_at → hope_date/hope_time).
  - 팩토리: 설정별 올바른 어댑터 반환(enabled=N, type별).
  - crypto 라운드트립(비번 암복호) — 기존 crypto 테스트 패턴 재사용.
- **Playwright 통합테스트:** `order/order3.asp` 폼 HTML 스냅샷을 로컬 파일로 저장,
  헤드리스로 로드해 매핑이 올바른 칸을 채우는지 검증(라이브·실주문 생성 없음).
- **라이브 E2E:** 환경 플래그 뒤 수동 1건만(쓰레기 주문 방지). 등록 성공 → rpa_status='success' 확인.
- **smoke:** Playwright import/연결은 win32 + 포트 가용 시에만(헤드리스 CI 스킵), 기존 tray 패턴 따름.

## 9. 의존성 / 운영

- `playwright` 의존성 추가(`pyproject.toml`). 시스템 Chrome 사용(`channel="chrome"`) → 브라우저 다운로드 불필요.
  `greenlet`은 3.1.1로 고정(3.5.x가 이 환경에서 DLL 로드 실패).
- 전용 프로필 Chrome 자동기동 + 최초 1회 로그인 절차를 운영 문서/인스톨러에 반영.
- 멀티샵: 현재 백엔드는 단일샵(SHOP_KEY) 전용. 설정은 shop_key 단위로 저장되어 멀티샵 확장과 호환.

## 10. 구현 순서(요약)

1. 의존성(playwright, greenlet 고정) + config 항목.
2. DB 마이그레이션 + get/save_settings RPC + 프론트 설정 UI/타입.
3. 샵 설정 로딩(`program_settings`) + 팩토리(`factory`) + ManualOnly/스텁 어댑터.
4. 순수 매핑/채널맵 모듈 + 단위테스트.
5. `FlowerNt3Automator`(세션/로그인/입력/등록) + 통합테스트.
6. `singleton_macro` 배선(팩토리 사용).
7. 라이브 E2E 검증 → 라디오 라벨/리본 매핑 최종 확정.
