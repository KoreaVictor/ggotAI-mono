# ggotAIorder 백엔드

다중 채널 주문 수집·AI 정형화·자동입력(RPA) Windows 백그라운드 서비스.

## 개발 환경 설정

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
backend\.venv\Scripts\python.exe -m pip install -e backend
```

### 관리 프로그램별 자동입력(RPA) 의존성

꽃집이 쓰는 주문관리 프로그램에 맞는 extra만 설치한다. 안 쓰는 쪽은 설치하지 않는다
(설치돼 있지 않아도 수집엔진은 정상 기동하며, 해당 주문은 백업(manual) 경로로 흐른다).

```powershell
# FlowerNT(웹) 쓰는 가게
backend\.venv\Scripts\python.exe -m pip install -e "backend[flowernt]"
backend\.venv\Scripts\python.exe -m playwright install chromium

# RoseWeb(데스크톱 앱) 쓰는 가게
backend\.venv\Scripts\python.exe -m pip install -e "backend[roseweb]"
```

후속 세션에서 필요 시:
```powershell
backend\.venv\Scripts\python.exe backend\.venv\Scripts\pywin32_postinstall.py -install
```

## 로컬 디버그 실행 (서비스 미등록)

```powershell
backend\.venv\Scripts\python.exe backend\run_dev.py
```
FastAPI: http://127.0.0.1:8765/health

## Windows 서비스 등록 (관리자 권한)

```powershell
backend\.venv\Scripts\python.exe -m ggotaiorder.service install
net start ggotAIorder
net stop ggotAIorder
```

## 테스트

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### Gemini 라이브 테스트 (선택)

실제 Gemini API를 호출하는 추출 테스트는 기본적으로 skip됩니다. 실제 호출로 검증하려면:
```powershell
$env:RUN_LIVE_GEMINI="1"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_extractor_live.py -v
```
`GEMINI_API_KEY`가 `backend/.env`에 있어야 합니다.

## 인입 경로 라이브 구동 체크리스트

api Webhook·Realtime은 코드로 구현·오프라인 테스트되었으나, 실제 동작에는 다음 인프라가 필요합니다(인프라 준비 시 수행):

1. Supabase Storage에 비공개 버킷 `call-audio` 생성.
2. `server_call_history` 테이블 Realtime(Replication) 활성화.
3. `run_dev.py` 기동 후 멀티파트 업로드 → server_call_history 행 + order_details 생성 확인.
4. '핸드폰' 채널 행 INSERT(모바일 앱/수동) → Realtime이 process 트리거하는지 확인.

## STT(faster-whisper) 라이브 구동 체크리스트

STT는 코드로 구현·오프라인 테스트되었으나, 실제 음성 변환에는 다음이 필요합니다:

1. **MS Visual C++ Redistributable** 설치 — ctranslate2 네이티브 DLL 의존(미설치 시 `faster_whisper` import가 DLL 로드 실패).
2. 최초 실행 시 STT 모델 자동 다운로드(기본 `small` ~460MB). 환경변수로 조정: `STT_MODEL`/`STT_COMPUTE_TYPE`/`STT_DEVICE`(기본 small/int8/cpu).
3. `call-audio` 버킷에 통화 음성이 적재되어 있어야 함(인입 경로 증분의 버킷 생성 선행).
4. 한국어 샘플 음성으로 opt-in 검증: `$env:RUN_LIVE_STT="1"; $env:STT_SAMPLE_PATH="<sample.wav>"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt_live.py -v`

## notifier(알림 발송) 라이브 구동 체크리스트

알림 발송 로직은 구현·오프라인 테스트되었으나, 실제 발송에는 다음이 필요합니다:

1. 메시징 제공사 계정/API 키 발급(SMS) + 알림톡 사용 시 발신프로필·승인 템플릿 등록.
2. `.env`에 제공사 선택·자격증명 설정. `NOTIFY_PROVIDER`로 제공사 선택:
   - 미설정(기본): `HttpNotificationProvider`(범용 SMS 골격). `NOTIFY_API_URL`/`NOTIFY_API_KEY` 설정 + 페이로드 규격 완성.
   - `iwinv`: 카카오 알림톡(iwinv). `IWINV_API_KEY` + 템플릿코드(아래 5번).
   - `bizm`: 카카오 알림톡(비즈엠/스윗트래커). `BIZM_USER_ID`(계정명)·`BIZM_PROFILE_KEY`(발신프로필키 40자) + 템플릿코드.
3. `setting_info.use_notification='Y'` + 수신번호(`notification_phone_number` 또는 `member_info.mobile_number`) 설정 후 테스트 발송.
4. (후속) rpa 처리 완료 시 `notifier.send(shop_key, channel, count, success)` 호출 배선.
5. 알림톡(iwinv/bizm) 템플릿코드는 outcome별로 `NOTIFY_TEMPLATE_CODE_SUCCESS|MANUAL|FAIL`(provider 중립)에 설정. 구 `IWINV_TEMPLATE_CODE_*`도 폴백 인식.
   - ⚠️ 비즈엠은 서버가 템플릿을 렌더링하지 않고 완성 문구(`msg`)를 그대로 보내므로, `setting_info.rpa_*_message`(치환 후 텍스트)가 **승인된 템플릿 고정문구와 일치**해야 발송된다.

## scraper(인트라넷 크롤러) 라이브 구동 체크리스트

크롤러 오케스트레이션은 구현·오프라인 테스트되었으나, 실제 수집에는 다음이 필요합니다:

1. 대상 인트라넷 사이트 URL·계정·로그인/목록/상세 페이지 HTML 구조 확보.
2. `PlaywrightIntranetScraper.fetch_orders` 셀렉터 구현(로그인 → 신규 주문번호 → 상세 11필드).
3. `backend\.venv\Scripts\python.exe -m playwright install chromium` (브라우저 바이너리).
4. `setting_info`에 `intranet_url`/`intranet_id`/`intranet_password`(프론트가 AES 암호화 저장) 설정.
5. 폴링 실행 → 신규 주문 수집·중복 skip·order_details 생성 확인. 연속 3회 실패 시 비상 알림 확인.

## RPA(싱글턴 입력 엔진) 라이브 구동 체크리스트

enqueue 오케스트레이션·백업은 구현·오프라인 테스트되었으나, 실제 자동 입력에는 다음이 필요합니다:

1. 대상 꽃집 관리 프로그램 창 제목·입력 폼 필드 Tab 이동 순서 확보.
2. `WindowsProgramAutomator.is_program_running` 창 탐색(pygetwindow) 구현.
3. `WindowsProgramAutomator.input_order` 클립보드(pyperclip)+키 시퀀스 입력 구현.
4. (선택) `.env`에 `RPA_BACKUP_DIR` 설정 — 기본값은 `backend/backups`.
5. enqueue 실행 → 구동 시 자동 입력·`rpa_status='success'`·성공 알림 / 미구동·입력실패 시 백업(.xlsx+.txt)·`'fail'`·경고 알림 확인.

### RoseWeb(화원박사) 가게 온보딩 체크리스트

RoseWeb 자동입력은 그 PC 의 실측값(폼 좌표·상품 마스터)에 묶여 있다. 새 가게를 붙이거나
프로그램이 업데이트되면 아래를 반드시 다시 맞춘다. 실측 방법은
`docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md` 참조.

1. **상품 마스터 재확인 — 가장 중요.** `rpa/roseweb/product.py` 의 `MASTER_TERMS`·키워드 규칙은
   **가게마다 다르고**, 현재 값은 shop 19(테스트꽃집) 실측이다. ⚠️ 마스터에 **없는** 이름으로
   검색한 뒤 '선택'을 누르면 RoseWeb 이 크래시한다(Access violation, 재시작 필요). 코드로는
   이걸 막을 수 없다 — 크래시가 클릭 순간 나기 때문이다. 그래서 `product.py` 가 내놓는 검색어가
   전부 그 가게 **실제** 마스터에 있는지 사람이 대조해야 한다(자동 테스트는 규칙 출력이
   `MASTER_TERMS` 안에 있는지만 보장하지, `MASTER_TERMS` 가 라이브와 맞는지는 모른다).
2. **폼 좌표 재측정.** `rpa/roseweb/layout.py` 는 폼 크기 1076x854 기준 실측이다. 창 크기/버전이
   다르면 `roseweb_inspect.py dump` 로 다시 뜬다(automator 가 폼 크기가 다르면 채우기를 거부한다).
3. **채우기(auto_submit=N)부터.** `setting_info` 에 `rpa_program_type='roseweb'`·`rpa_enabled='Y'`·
   `rpa_auto_submit='N'`. 실주문 몇 건이 정확히 채워지는지 사장님이 눈으로 확인.
4. **auto_submit=Y 전환**은 채우기 검증이 쌓인 뒤 사장님 결정(FlowerNT 관례). 전환 전
   `_save_confirm_timeout`(기본 30초)이 그 PC 에 충분한지 확인 — 저장 후 폼이 닫히는 데 그보다
   오래 걸리면 실제 등록된 주문을 fail 로 오판해 중복이 생긴다.

## 구조

- `config` / `logging_setup` / `core/crypto` / `core/supabase_client` — 핵심 코어(실로직)
- `orchestrator` — 단일 asyncio 루프, 서브시스템 배선, 수집 on/off
- `service` / `tray` — Windows 서비스·트레이
- `api` / `realtime` / `pipeline` / `scraper` / `rpa` / `notifier` — 도메인 모듈(스텁, 후속 구현)
