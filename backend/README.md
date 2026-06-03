# ggotAIorder 백엔드

다중 채널 주문 수집·AI 정형화·자동입력(RPA) Windows 백그라운드 서비스.

## 개발 환경 설정

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
backend\.venv\Scripts\python.exe -m pip install -e backend
```

후속 세션에서 필요 시:
```powershell
backend\.venv\Scripts\python.exe -m playwright install chromium
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

## 구조

- `config` / `logging_setup` / `core/crypto` / `core/supabase_client` — 핵심 코어(실로직)
- `orchestrator` — 단일 asyncio 루프, 서브시스템 배선, 수집 on/off
- `service` / `tray` — Windows 서비스·트레이
- `api` / `realtime` / `pipeline` / `scraper` / `rpa` / `notifier` — 도메인 모듈(스텁, 후속 구현)
