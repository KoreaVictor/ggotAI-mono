# Phase 4 통합·최종 검증 설계서

- **작성일:** 2026-06-05
- **대상:** `task.md` Phase 4 (통합 및 최종 검증) 3개 항목
- **접근법:** A — 계층형 자동화 + 라이브 게이팅 (오프라인 항상-on 안전망 + 라이브 자원 opt-in 심화)
- **선행 상태:** master `a6e0766`, Phase 1·2·3 완료, 전체 79 passed / 3 skipped

---

## 1. 배경 및 목표

`task.md` Phase 4는 세 가지 통합 검증을 요구한다.

1. **T1** 프론트엔드↔백엔드↔Supabase **DB 스키마 정합성 교차 테스트**
2. **T2** React UI [수집 중지] → Electron IPC → Windows 서비스 정지 + 트레이 아이콘 🔴 **OS 수준 수동 검증**
3. **T3** 모의 음성 Webhook → STT → Gemini → `order_details` → 싱글턴 RPA → 카카오 알림톡 **E2E 통합 검증**

세 항목은 성격이 달라 산출물을 분리한다.

| 항목 | 성격 | 산출물 |
|---|---|---|
| T1 | 정적 계약 + 라이브 드리프트 | pytest (오프라인 항상 + 라이브 opt-in) |
| T2 | OS/관리자권한/GUI 시각 | 수동 체크리스트 문서 + 비-GUI 명령 보조 |
| T3 | 모듈 조립 배선 | pytest (오프라인 fake 항상 + 풀 라이브 opt-in) |

### 가용 라이브 자원 (2026-06-05 확인)
- Supabase 실 DB 접근 ✓
- Gemini 실호출 ✓ (`GEMINI_API_KEY`)
- Windows 서비스 설치/구동 ✓ (관리자 권한)
- 카카오 알림톡 provider ✗ → notify는 **fake provider / spy로 배선만** 검증

### 범위 결정
- **STT 우회:** E2E는 `stt_text`를 직접 주입한다. 실 STT는 이미 자체 opt-in 라이브 테스트(`RUN_LIVE_STT`)가 존재하며, 이 머신은 ctranslate2 DLL 로드가 실패(MS VC++ Redistributable 미설치)하므로 E2E 경로에서 제외한다.
- **검출 결함 수정 포함:** 검증이 드러내는 실 결함(아래 §6의 NOT NULL 잠복 버그 등)은 본 작업 범위에서 수정한다.

---

## 2. 기준 계약: `docs/database_schema.sql`

검증의 단일 기준은 리포의 `docs/database_schema.sql`(4테이블)이다. 테이블·컬럼·제약은 다음과 같다(요지).

- `member_info` — `id`(PK), `username`, `password`, `shop_name`, `representative_name`, `landline_number?`, `mobile_number`, `email?`, `address?`, `address_detail?`, `is_approved`, `created_at`
- `server_call_history` — `id`(PK), `channel_order`, `channel_classification`(NN), `shop_key`(NN), `shop_name`(NN), `customer_phone_number`, `customer_name`, `call_date`(NN), `call_time`(NN), `duration_seconds`, `audio_file_name?`, `stt_text?`, `is_order`, `created_at`, FK→member_info
- `order_details` — `id`(PK), `call_history_id`(NN), `shop_key`(NN), `shop_name`(NN), `customer_name`, `customer_phone_number`(NN), `product_name`(NN), `quantity`, `price`, `delivery_at`(NN), `delivery_place`(NN), `receiver_name`(NN), `receiver_phone_number`(NN), `ribbon_sender?`, `ribbon_congratulations?`, `card_message?`, `rpa_status`, `created_at`, FK→server_call_history
- `setting_info` — `id`(PK), `shop_key`(NN,UQ), `use_notification`, `notification_phone_number?`, `rpa_success_message`, `rpa_fail_message`, `order_hp_1`(NN), `order_hp_2?`, `order_landline_1?`, `order_landline_2?`, `shopping_mall_*?`, `intranet_url?`, `intranet_id?`, `intranet_password?`, `shopping_mall_check_interval`, `intranet_check_interval`, `created_at`, FK→member_info

> 약식: `NN`=NOT NULL, `?`=NULL 허용(또는 DEFAULT NULL), 그 외는 DEFAULT 보유.

`order_details`의 **NN이면서 DEFAULT 없는** 컬럼: `call_history_id, shop_key, shop_name, customer_phone_number, product_name, delivery_at, delivery_place, receiver_name, receiver_phone_number`. (이 집합이 §6 결함 검출의 핵심)

---

## 3. T1 — 스키마 정합성 교차 테스트

### 3.1 계약 파서 — `tests/support/schema_contract.py`
- `parse_schema(path) -> dict[str, dict[str, ColumnSpec]]`
- `ColumnSpec`: `name`, `nullable: bool`(`NOT NULL` 부재 시 True), `has_default: bool`(`DEFAULT`/`SERIAL` 보유)
- `required_columns(table) -> set[str]`: `not nullable and not has_default`인 컬럼(INSERT 시 반드시 채워야 하는 집합).
- 단순 정규식/라인 파서로 충분(DDL이 안정적·소규모).

### 3.2 T1a 페이로드 적합성 (오프라인, 항상) — `tests/test_phase4_schema.py`
백엔드의 INSERT 페이로드 빌더를 샘플 입력으로 호출해 결과 dict를 계약과 대조한다.

대상 빌더와 테이블:
- `pipeline.engine._build_order_payload(row, extraction)` → `order_details`
- `scraper.crawler._call_record(shop, order)` → `server_call_history`
- `scraper.crawler._order_payload(shop, order, call_id)` → `order_details`
- `api.service`/`api.repository`가 만드는 `server_call_history` record (인입 record 구성 함수; 필요 시 소규모 헬퍼로 추출)

각 페이로드에 대해 단언:
1. **컬럼 존재:** 모든 키 ∈ 해당 테이블 컬럼.
2. **필수 충족:** `required_columns(table)` ⊆ 페이로드 키, 그리고 그 값이 `None`이 아님.
3. **(가능 시) 두 종류 입력:** "완전 추출"과 "최소/누락 직전 추출" 두 케이스로 호출해 누락 입력에서도 NN 컬럼이 None이 되지 않는지 확인.

> 이 단언이 §6의 NOT NULL 잠복 버그를 빨강으로 만든다 → 빌더 수정 후 초록.

### 3.3 T1b 컬럼 참조 스캔 (오프라인, 항상)
repository 계열 모듈(`*/repository.py`)에서 DB 컬럼 문자열을 추출해 계약 존재 여부를 단언한다.
- 추출 패턴(정규식): `.eq("<col>", …)`, `.select("<csv>")`, `.update({…})`의 키, `.is_("<col>", …)`, `.not_.is_("<col>", …)`.
- `.select("*")`·임베드(`member_info(...)`)·식별 불가 토큰은 스킵(화이트리스트로 제외).
- 테이블 귀속: 같은 호출 체인의 `.table("<name>")`로 결정. 결정 불가 시 "4개 테이블 컬럼 합집합"에 대한 존재만 검사(약식).

### 3.4 T1c 라이브 드리프트 (opt-in `RUN_LIVE_SCHEMA=1`)
실 Supabase의 실제 컬럼을 조회해 `schema.sql`과 비교.
- 조회: 각 테이블 `select("*").limit(0)` 또는 PostgREST/`information_schema`로 컬럼 키 수집.
- 단언: `set(실DB 컬럼) == set(schema.sql 컬럼)` (양방향). 불일치 시 누락/잉여를 메시지에 출력.
- 미설정 시 `pytest.skip`.

### 3.5 프론트 스캔 (오프라인, best-effort) — `tests/test_phase4_frontend_schema.py`
- 대상: `frontend/src/**/*.tsx`, `frontend/src/**/*.ts`.
- 추출: `.from('<table>')` 테이블명 + 인접 `.select('<csv>')`/`.eq('<col>',…)` 컬럼 리터럴.
- 단언: 추출 컬럼 ∈ 계약. 취약성 인지 — 추출 실패/모호 토큰은 스킵하고, 명백한 불일치만 실패시킨다.
- frontend 디렉터리/소스 부재 시 `pytest.skip`.

---

## 4. T3 — 음성→…→알림톡 E2E

### 4.1 진입점·체인
`FastAPI` `TestClient`로 `POST /api/v1/gate-phone/upload`부터 조립 체인을 관통한다(기존 `test_api_routes.py`의 DI override 패턴 재사용).

```
HTTP upload → api.ingest_gate_phone → server_call_history INSERT
           → pipeline.engine.process (stt_text 직접 주입, STT 우회)
           → extract_order → order_details INSERT (is_order='Y', rpa_status='ready')
           → rpa.singleton_macro.enqueue → get_order
           → automator.is_program_running == False → backup.write(.xlsx + .txt)
           → set_rpa_status('fail') → notify(spy)
```
> automator 미구동이 정상 경로(실제 꽃집 프로그램 없음) → 백업 분기. notify는 카카오 미보유로 spy/fake.

### 4.2 T3a 조립 E2E (오프라인, 항상) — `tests/test_phase4_e2e.py`
- 실 모듈 + fake 어댑터: fake `IngestRepository`/`AudioStorage`(api), fake `OrderRepository`(engine), fake `RpaRepository`/`ProgramAutomator`(미구동)/`BackupWriter`(tmp_path 실제 기록 또는 spy)/notify spy.
- `extract_order`는 monkeypatch로 결정적 추출 결과 주입(라이브 Gemini 불필요).
- 단언: 업로드 200 + `call_history_id` 반환 → `order_details` 페이로드 형태(NN 충족) → `enqueue` 호출 → 백업 파일 생성(또는 spy 호출) → `set_rpa_status` 마킹 → notify spy 호출(인자: shop_key/channel/count/success).
- `BackgroundTasks`는 `TestClient` 컨텍스트에서 응답 후 실행되므로, 필요 시 `process`를 동기 await로 직접 호출하는 보조 경로로 체인 끝까지 결정적으로 단언.

### 4.3 T3b 풀 라이브 E2E (opt-in `RUN_LIVE_E2E=1`)
- 실 Gemini 추출 + 실 Supabase INSERT/조회/상태마킹. automator 미구동→실제 백업 `.xlsx`. notify는 spy/fake.
- **전용 테스트 픽스처:** 사전에 존재해야 하는 테스트용 `member_info`(+`setting_info`) 행. 식별은 환경변수 `E2E_TEST_SHOP_KEY`(미설정 시 skip+안내).
- **정리:** 테스트가 생성한 `server_call_history`/`order_details` 행을 종료 시 삭제(FK CASCADE로 call_history 삭제 시 order_details 동반 삭제). 백업 파일은 tmp 디렉터리(`RPA_BACKUP_DIR`)로 격리 후 정리.
- 픽스처/환경 부재 시 `pytest.skip`. 시작 전 픽스처 존재 확인.

---

## 5. T2 — IPC→서비스정지→트레이🔴 (수동 폴백)

산출물: `docs/phase4_manual_verification.md` — 정밀 체크리스트.

- **사전 준비(비-GUI, 보조 가능):**
  - 프론트 빌드: `cd frontend && npm run build`(또는 dev 실행)
  - 서비스 설치(관리자): `python -m ggotaiorder.service install` → `sc query ggotAIorder`로 등록 확인
- **검증 절차(표: 단계 / 명령·동작 / 기대 관측 / 실패 진단):**
  1. 서비스 시작 → `sc query` `RUNNING` + 트레이 🟢
  2. Electron 앱 실행 → 대시보드 표시
  3. [수집 중지] 클릭 → Electron IPC → `net stop ggotAIorder` 실행
  4. `sc query ggotAIorder` → `STOPPED`
  5. 트레이 아이콘 🔴 (시각 확인 / 스크린샷)
  6. [시작] 클릭 → `net start` → `RUNNING` + 🟢 (역검증)
- 사용자가 GUI/시각 단계 수행·기록, 비-GUI 단계는 보조.

> 서비스명 정합: 프론트 `net start/stop ggotAIorder` ↔ `service.py`의 서비스명이 동일해야 함 — 체크리스트 0단계에서 확인.

---

## 6. 검출 예상 결함 및 수정 (범위 포함)

**잠복 버그 (T1a/T3b가 검출):** `order_details`의 NN·DEFAULT 없는 컬럼 `product_name, delivery_at, delivery_place, receiver_name, receiver_phone_number`에 대해 `engine._build_order_payload`가 `extraction.*`(None 가능)을 그대로 넣는다. 누락<3(주문 판별)이어도 이들 중 일부가 None이면 실 INSERT가 NOT NULL 위반으로 실패한다.

**수정 방침:** 빌더에서 NN 컬럼에 안전 기본값 부여(예: `product_name or "미정"`, `delivery_place or "미정"`, `receiver_name or customer_name`, `receiver_phone_number or customer_phone_number`, `delivery_at`는 미상 시 합의된 기본값/플레이스홀더). `scraper.crawler._order_payload`도 동일 점검·수정. 정확한 기본값은 구현 시 TDD로 확정하되, **NN 위반이 발생하지 않음**을 불변식으로 한다.

> `delivery_at`은 타임스탬프 NN이라 임의 문자열이 부적합할 수 있음 — 구현 단계에서 "미상 시 처리"(기본값 vs 별도 보류 상태)를 결정한다. 이는 plan 단계의 명시 과제로 넘긴다.

---

## 7. 산출물·게이팅 요약

| 파일 | 내용 | 실행 |
|---|---|---|
| `backend/tests/support/schema_contract.py` | schema.sql 파서 | (유틸) |
| `backend/tests/test_phase4_schema.py` | T1a 페이로드 적합성, T1b 참조 스캔, T1c 라이브 드리프트 | 오프라인 항상 + `RUN_LIVE_SCHEMA` |
| `backend/tests/test_phase4_frontend_schema.py` | 프론트 컬럼 best-effort 스캔 | 오프라인 항상(소스 없으면 skip) |
| `backend/tests/test_phase4_e2e.py` | T3a 조립 E2E, T3b 풀 라이브 E2E | 오프라인 항상 + `RUN_LIVE_E2E` |
| `docs/phase4_manual_verification.md` | T2 수동 체크리스트 | 수동 |
| `backend/src/.../engine.py` (수정) | NN 기본값 보강 | — |

**게이팅 컨벤션:** 라이브는 환경변수 opt-in(`RUN_LIVE_SCHEMA`, `RUN_LIVE_E2E`), 기존 `RUN_LIVE_GEMINI`/`RUN_LIVE_STT`와 동일 패턴. 오프라인 항상-on은 기본 `pytest -q`에 포함.

## 8. 완료 기준 (Definition of Done)
1. 오프라인 전체 `pytest -q` 그린(신규 T1a/T1b/T3a/프론트 포함).
2. §6 NOT NULL 결함 수정 + 회귀 테스트 통과.
3. (가능 시) `RUN_LIVE_SCHEMA=1`, `RUN_LIVE_E2E=1` 각 1회 통과 — 자원·픽스처 준비된 경우.
4. `docs/phase4_manual_verification.md` 작성, T2 수기 검증 결과 기록.
5. `task.md` Phase 4 항목 체크오프(검증 방식·라이브 후속 명시).

## 9. 비범위 (Out of Scope)
- 실 STT(faster-whisper) E2E 포함 — 별도 `RUN_LIVE_STT` 테스트로 존재.
- 실 카카오 알림톡 발송 — provider 미보유, fake/spy로 배선만.
- 실 인트라넷/꽃집 프로그램 라이브 골격 — 별도 Phase(라이브 골격 실구현).
- 잔여 라이브 후속(N+1 embed 조인 등)은 본 검증과 독립 — 필요 시 T1c가 드러내는 범위만 참조.
