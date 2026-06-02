# ggotAIorder 백엔드 골격 설계서

작성일: 2026-06-02
범위: 백엔드(Windows Service) 전체 골격 + 모든 모듈 스텁 + 핵심 코어 실로직

---

## 1. 목표와 범위

PRD/구현계획서(Phase 3)에 정의된 백엔드 `ggotAIorder`의 **전체 골격**을 구성한다.
이번 작업의 산출물은 다음과 같다.

- **실제 동작(실로직)**: 환경설정 로딩, 로깅, AES-256-CBC 복호화(crypto-js 호환),
  Supabase 클라이언트 래퍼, asyncio 오케스트레이터, Windows Service 래퍼, 트레이 아이콘.
- **스텁(인터페이스 고정)**: 6개 도메인 모듈(api / realtime / pipeline / scraper / rpa / notifier).
  함수 시그니처·타입힌트·docstring으로 계약을 확정하고, 본문은 안전한 no-op + 로그 또는
  `NotImplementedError`로 둔다. 오케스트레이터가 이들을 호출하는 **배선은 실제로 연결**한다.

외부 리소스(실제 인트라넷 사이트, 꽃집 관리 프로그램 창, Gemini/카카오 API 키, VoIP 통신사
Webhook)가 있어야 동작하는 부분은 후속 세션에서 모듈별로 채운다.

전체 의존성(faster-whisper, playwright, pywin32 등 포함)을 venv에 설치한다.

---

## 2. 아키텍처: 단일 asyncio 이벤트 루프 오케스트레이터

여러 서브시스템(FastAPI 서버, Supabase Realtime 웹소켓, APScheduler 크롤러, 싱글턴 RPA)을
**단일 Windows Service 프로세스 안에서 하나의 asyncio 이벤트 루프** 위에 올린다.

- uvicorn(FastAPI), supabase realtime(async), `AsyncIOScheduler`, RPA(`asyncio.Lock`)가
  모두 같은 이벤트 루프를 공유한다.
- pywin32 Windows Service(`service.py`)가 **워커 스레드**에서 이 이벤트 루프를 start/stop 한다.
- 트레이(`tray.py`)는 별도 스레드/프로세스에서 동작하며 서비스 상태를 표시한다.

**채택 이유**: PRD가 요구하는 `asyncio.Lock()` 기반 싱글턴 순차 RPA 제어와 가장 자연스럽게
부합하고, 멀티스레드/멀티프로세스 대비 서브시스템 간 조율이 단순하다.

(대안 B: 멀티스레드+큐 — RPA 락 조율 복잡. 대안 C: 멀티프로세스 — Windows 서비스 관리 복잡.
둘 다 기각.)

---

## 3. 폴더 구조

```
backend/
├─ requirements.txt
├─ README.md                  # 서비스 등록/실행 가이드
├─ run_dev.py                 # 서비스 없이 로컬 디버그 실행 진입점
├─ src/ggotaiorder/
│  ├─ __init__.py
│  ├─ config.py               # [실로직] .env 로딩, 필수 키 검증
│  ├─ logging_setup.py        # [실로직] 파일+콘솔 로깅 구성
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ crypto.py            # [실로직] AES-256-CBC 복호화 (crypto-js 호환)
│  │  └─ supabase_client.py   # [실로직] supabase-py 클라이언트 래퍼(싱글턴)
│  ├─ orchestrator.py         # [실로직] asyncio 루프, 서브시스템 wiring, 수집 on/off 상태
│  ├─ service.py              # [실로직] pywin32 Windows Service 래퍼
│  ├─ tray.py                 # [실로직] pystray 트레이 아이콘/메뉴(🟢/🔴)
│  ├─ api/
│  │  ├─ __init__.py
│  │  └─ routes.py            # [스텁] FastAPI /api/v1/gate-phone/upload
│  ├─ realtime/
│  │  ├─ __init__.py
│  │  └─ listener.py          # [스텁] server_call_history INSERT 구독 콜백
│  ├─ pipeline/
│  │  ├─ __init__.py
│  │  └─ engine.py            # [스텁] STT(faster-whisper)+Gemini 11필드 추출/필터
│  ├─ scraper/
│  │  ├─ __init__.py
│  │  └─ crawler.py           # [스텁] Playwright 인트라넷 폴링 크롤러
│  ├─ rpa/
│  │  ├─ __init__.py
│  │  └─ singleton_macro.py   # [스텁] asyncio.Lock RPA + 엑셀/영수증 백업
│  └─ notifier/
│     ├─ __init__.py
│     └─ sms_sender.py        # [스텁] 알림톡/문자 + {channel}/{count} 템플릿 치환
└─ tests/
   └─ test_crypto.py          # [실로직] AES 복호화 검증
```

---

## 4. 핵심 코어 모듈 (실로직)

### 4.1 config.py
- `python-dotenv`로 `backend/.env` 로딩.
- 노출 값: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `AES_ENCRYPTION_KEY`.
- 필수 키 누락 시 명확한 예외로 조기 실패(fail-fast). 키 길이 검증(AES 키 32바이트).

### 4.2 logging_setup.py
- 콘솔 + 회전 파일 핸들러(`logs/ggotaiorder.log`). 포맷에 타임스탬프·레벨·모듈명 포함.

### 4.3 core/crypto.py — AES-256-CBC 복호화 (crypto-js 호환)
- DB 저장 포맷: `iv_hex(32 chars) + ":" + ciphertext_base64`.
- 알고리즘 `AES-256-CBC`, 패딩 `PKCS7(128)`, 키는 `AES_ENCRYPTION_KEY` UTF-8 32바이트.
- `decrypt(db_value: str) -> str` 제공. (대칭 검증용 `encrypt`도 테스트 목적상 함께 제공.)
- ipc_specification.md의 Python 복호화 예시 규격을 정확히 따른다.

### 4.4 core/supabase_client.py
- `supabase-py`로 클라이언트 생성(서비스 롤 키 사용). 프로세스 내 싱글턴으로 재사용.
- 얇은 래퍼: `get_client()` 및 자주 쓰는 테이블 접근 헬퍼는 후속 세션에서 확장.

---

## 5. 오케스트레이터 (실로직 배선)

`orchestrator.py`는 asyncio 루프를 소유하고 서브시스템을 기동/정지한다.

- `start()`: FastAPI(uvicorn) 서버, Realtime 리스너, APScheduler(크롤러 잡), RPA 워커를 기동.
- `stop()`: graceful shutdown.
- **수집 on/off 상태 플래그**: `paused` 상태를 보유. `net stop` 시 수집 루프를 일시정지(정지가
  아닌 일시정지), `net start` 시 재개. 트레이 색상은 이 상태를 반영.
- 6개 도메인 모듈의 진입 함수를 실제로 호출하도록 배선하되, 모듈 본문은 스텁.

---

## 6. 데이터 흐름 (스텁이 고정하는 계약)

```
[가게전화]  POST /api/v1/gate-phone/upload
              → 음성파일 Supabase Storage 임시적재
              → server_call_history INSERT (channel_order='가게전화')
              → pipeline.process(call_history_id)
[핸드폰/가게음성]  Realtime: server_call_history INSERT 감지
              → on_new_call_received(payload)
              → pipeline.process(call_history_id)

pipeline.process(call_history_id):
   STT(faster-whisper) → stt_text 업데이트
   → Gemini 11필드 JSON 추출
   → 공백 ≥3 이면 is_order='N' + 음성파일 강제삭제 후 종료
   → is_order='Y' 이면 order_details INSERT (rpa_status='ready')
   → rpa.enqueue(order_detail_id)

[인트라넷]  APScheduler 주기 폴링 → Playwright 로그인/스크래핑
              → 중복 검증 → server_call_history INSERT(stt_text=원문, audio_file_name='INTRANET_CRAWLED')
              → AI 패스, 바로 order_details INSERT (rpa_status='ready')
              → rpa.enqueue(order_detail_id)
              → 연속 3회 실패 시 notifier 비상 알림

rpa.enqueue(order_detail_id):   # asyncio.Lock 으로 싱글턴 순차
   관리프로그램 창 탐색
   → 있으면 클립보드/Tab 매크로 입력 → rpa_status='success'/'fail'
   → 없으면 엑셀(.xlsx)+텍스트 영수증 백업 생성
   → 완료 후 notifier.send(channel, count, success/fail)

notifier.send(...):
   setting_info.use_notification 'N' 이면 종료
   수신번호 = notification_phone_number ?? member_info.mobile_number
   템플릿({channel},{count} 치환) → 카카오 알림톡/문자 발송 + 이력 기록
```

각 스텁 함수는 위 시그니처/반환 계약을 타입힌트와 docstring으로 명시한다.

---

## 7. 수집 On/Off 및 서비스 수명주기 (UC2)

- `service.py`(pywin32): `SvcDoRun` → 워커 스레드에서 오케스트레이터 루프 시작.
  `SvcStop` → 오케스트레이터 graceful stop.
- 프론트엔드(Electron)는 `net start/stop ggotAIorder` / `sc query` 로 제어(ipc_specification.md).
- 트레이: 🟢 수집 중 / 🔴 수집 중지, 더블클릭 시 ggotAIya UI 호출(후속), 우클릭 메뉴.

---

## 8. 검증 계획

- **AES 복호화 단위테스트**(`tests/test_crypto.py`): crypto-js가 생성하는 포맷
  (`iv_hex:base64`)을 모사한 벡터로 `decrypt()`가 평문을 정확히 복원하는지 실제 실행 검증.
  encrypt→decrypt 라운드트립도 검증.
- **config 로딩 스모크**: `.env`에서 필수 키 로딩 및 누락 시 예외.
- **supabase_client 스모크**: 클라이언트 생성(네트워크 연결은 키가 유효할 때만).
- **import 스모크**: 6개 스텁 모듈이 정상 import 되는지 확인.

heavy 의존성(faster-whisper 모델 다운로드, playwright 브라우저 바이너리, pywin32
post-install)은 설치만 하고 실제 호출 검증은 후속 세션으로 미룬다.

---

## 9. 비범위 (Out of Scope, 후속 세션)

- 각 도메인 모듈의 실제 구현(STT 호출, Gemini 프롬프트, Playwright 셀렉터, RPA 매크로 좌표,
  카카오 API 연동).
- Windows 서비스 실제 등록/관리자 권한 통합 테스트.
- 프론트엔드-백엔드 E2E 통합.
