# 핸드폰 채널 라이브 점등 + HTTP STT(Whisper) 전환 설계서

- **작성일:** 2026-06-13
- **대상:** 핸드폰(`channel_order='핸드폰'`) 통화의 전체 루틴 ①주문→②STT→③Gemini→④DB저장→⑤RPA 실가동
- **기준 브랜치:** master `926b4f2`

---

## 1. 배경 — 직접 점검 결과

라이브 DB/스토리지 직접 조회로 확인한 현재 상태:

- **①주문 인입: 정상.** ggotAIhp가 `server_call_history`에 `channel_order='핸드폰'` 행을 실시간 INSERT 중(id 103~132, shop_key=19, 최신 2026-06-13). 오디오는 **`audio-files`** 버킷의 **`{매장수신번호}/{YYYYMM}/{파일명}`** 경로에 적재됨. (실측: `01058921670/202606/01058921670_0555828585_20260612_190438.wav`)
- **②~⑤: 단 한 건도 처리 안 됨.** 모든 핸드폰 행 `stt_text=null`, `is_order='N'`. 이 통화들로 생성된 `order_details`=0건(현존 order_details는 6/10 시드 더미).

### 근본 원인
- **A. 버킷/경로 계약 불일치(코드 버그):** 백엔드 STT는 `call-audio`(존재하지 않는 버킷)에서, DB에 저장된 **flat 파일명** 그대로 다운로드 시도 → 100% 실패 → 파이프라인 중단.
- **B. STT 가동 불가/미점등:** faster-whisper의 ctranslate2 네이티브 의존이 머신마다 설치 부담(과거 MS VC++ 미설치로 로드 실패). 또한 백엔드가 상시 구동+Realtime 구독 상태로 운영된 적 없음.

## 2. 결정

- **STT를 로컬 faster-whisper → 외부 HTTP(Whisper) 호출로 전환.** 꽃집마다 whisper 설치 불가 → 중앙(또는 외부 API)에서 변환.
  - **지금(테스트): Groq** `whisper-large-v3` (OpenAI 호환 `/v1/audio/transcriptions`, 무료티어·빠름·한국어 우수).
  - **나중: 자체 whisper 서버** — 동일 OpenAI 호환 규격이면 `STT_API_BASE` 교체만으로 전환. 음성 외부유출 제거.
- **추상화:** STT를 provider로 분기. `STT_PROVIDER=http`(기본, OpenAI 호환) / `local`(기존 faster-whisper, 자체서버 GPU용 보존).
- **점등 검증:** 운영머신 미정 → **이 PC에서** 밀린 핸드폰 통화 1건을 직접 `process(id)`로 실행해 ②~⑤ 관통 확인.
- **⑤ RPA:** 실제 꽃집 주문 프로그램 미설치 → 설계대로 **백업 `.xlsx`/`.txt` 폴백**(automator 미구동 정상 경로). 전체 루틴 검증엔 충분.
- **트레이드오프 인지:** 외부 API 사용 시 통화 음성이 제3자(Groq)로 전송(PII)·과금. 자체서버 전환 시 해소.

## 3. 코드 변경 (TDD)

### 3.1 `api/storage.py`
- `AUDIO_BUCKET = "call-audio"` → **`"audio-files"`** (실제 버킷).

### 3.2 `pipeline/stt.py`
- **객체 키 해석 `_resolve_key(audio_file_name)`:**
  - `/` 포함 → 이미 풀 키(가게전화 api 업로드 `{shop_key}/{uuid}.ext`) → 그대로 사용.
  - `/` 없음(핸드폰=ggotAIhp flat 파일명) → `{매장번호}/{YYYYMM}/{파일명}` 복원. 규칙: `stem.split("_")` 에서 `parts[0]`=매장번호, `parts[-2]`=YYYYMMDD → `[:6]`=YYYYMM.
  - (방어) 복원 키로 다운로드 실패 시 로깅하고 예외 전파(상위 `process`가 해당 건 skip).
- **provider 분기:**
  - `transcribe(audio_file_name)`: `data = _download_audio(_resolve_key(name))` → `_provider().transcribe(data, name)`.
  - `STT_PROVIDER` env: `http`(기본) → `HttpWhisperProvider`; `local` → 기존 faster-whisper 경로.
  - `HttpWhisperProvider`: `POST {STT_API_BASE}/audio/transcriptions`, 헤더 `Authorization: Bearer {STT_API_KEY}`, 멀티파트 `file`(오디오 바이트+파일명)·`model={STT_MODEL}`·`language=ko`·`response_format=json`. 응답 `{"text": ...}` 파싱. 비-2xx → 예외. 키 없으면 호출 시점 예외(설정 lazy 검증).
  - 기본값: `STT_API_BASE=https://api.openai.com/v1`, `STT_MODEL=whisper-1` (Groq 사용 시 env로 base/model 교체).
- faster-whisper 지연 import 안전성·`_download_audio`/`_get_model` 목킹 가능성 유지(기존 테스트 호환).

### 3.3 `backend/.env` (라이브)
```
STT_PROVIDER=http
STT_API_BASE=https://api.groq.com/openai/v1
STT_API_KEY=<Groq 키>
STT_MODEL=whisper-large-v3
```
> `config.py` `_REQUIRED_KEYS`는 건드리지 않음 — STT 설정은 provider가 lazy 로딩(오프라인 테스트 불변).

## 4. 테스트

- **단위(오프라인 항상):**
  - `_resolve_key`: flat 핸드폰 파일명 → `{phone}/{yyyymm}/{name}`; `/` 포함 키 → 그대로; 비정형 파일명 방어.
  - `HttpWhisperProvider`: requests/httpx 목으로 멀티파트 구성·Bearer 헤더·`text` 파싱·비2xx 예외.
  - provider 선택: `STT_PROVIDER=http` → Http, `local` → 기존 경로.
  - 기존 `test_pipeline_stt.py`(local 경로) 회귀 유지(또는 provider 분리에 맞게 갱신).
- **라이브(opt-in `RUN_LIVE_STT_HTTP=1`):** 실제 Groq로 샘플 오디오 1건 변환 → 비공백 텍스트.
- 전체 `pytest -q` 그린 유지.

## 5. 점등 절차

1. 3장 코드 수정 + 단위테스트 그린.
2. `.env`에 Groq 키 주입.
3. 이 PC에서 밀린 핸드폰 통화 1건(실주문성 통화) 골라 `python -c "...process(id)..."` 직접 실행.
4. 관통 확인: 오디오 다운로드 → Groq STT → Gemini 추출 → `order_details` INSERT(또는 누락≥3이면 is_order='N') → RPA enqueue → 백업 `.xlsx` 생성.
5. DB 검증: `stt_text` 채워짐, `order_details` 행, `rpa_status`. 좋으면 밀린 건 일괄 backfill(선택).

## 6. 후속 (Out of Scope 지금)

- 운영머신 확정 후 **Realtime 활성화 + 백엔드 상시구동**(자동 트리거). 현재는 수동 `process(id)`로 점등.
- **자체 whisper 서버** 구축 후 `STT_API_BASE` 전환(음성 외부유출 제거).
- ⑤ 실제 꽃집 주문 프로그램 연동(매크로 좌표/필드 매핑).
- 가게전화(api 업로드) 채널·인트라넷 채널은 본 작업 범위 아님(핸드폰만).
```
