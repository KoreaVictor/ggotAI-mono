# STT (faster-whisper) 실구현 설계서

작성일: 2026-06-03
범위: `pipeline.stt.transcribe` 스텁을 faster-whisper 실구현으로 — Storage 음성 다운로드 → 한국어 STT → 텍스트 반환. engine 통합 보정 포함.
기준 브랜치: master (PR #3 머지 완료), 작업 브랜치 `feature/stt-faster-whisper`.

---

## 1. 목표와 범위

PRD 6-4의 STT 단계(F5)를 실제 동작하도록 구현한다. `engine.process`는 이미 stt_text가 비고 실제 음성이 있을 때 `transcribe(audio_file_name)`을 호출한다(현재 스텁이 NotImplementedError). 이를 실 변환으로 대체한다.

- **포함(실로직)**: Supabase Storage(`call-audio`)에서 음성 다운로드, faster-whisper(한국어) 변환, 텍스트 반환. engine의 STT 호출을 비블로킹·예외안전하게 보정.
- **오프라인 테스트**: 다운로드·모델 seam을 monkeypatch한 결정적 단위테스트.
- **라이브(opt-in/체크리스트)**: 실제 모델 다운로드(small ~460MB)·한국어 샘플 음성으로 실변환 검증.
- **비범위**: 화자 분리·노이즈 제거, scraper/rpa/notifier, 실 모델/샘플 준비.

PRD 제약 8-3(매장 PC 자원 최소화): 경량 faster-whisper, 기본 `small`/`int8`/`cpu`.

## 2. 아키텍처 — 자기완결형 stt.py

STT를 한 모듈로 응집한다. `pipeline/stt.py`가 다운로드와 모델을 내부에 두고, 테스트는 두 seam(`_download_audio`, `_get_model`)을 monkeypatch한다. api 계층에 의존하지 않는다.

### 데이터 흐름
```
engine.process(call_history_id):
  stt_text 비어있고 audio가 실제 음성(≠INTRANET_CRAWLED)이면:
    stt_text = await asyncio.to_thread(transcribe, audio_file_name)
    repo.update_stt_text(id, stt_text)
  → 이후 기존 Gemini 추출/필터/INSERT 진행

transcribe(audio_file_name):
  data = _download_audio(audio_file_name)          # call-audio 버킷에서 bytes
  임시파일(원 확장자)로 기록
  model = _get_model()                              # lazy WhisperModel
  segments, _ = model.transcribe(temp_path, language="ko")
  text = " ".join(seg.text.strip() for seg in segments).strip()
  임시파일 삭제(finally)
  return text
```

## 3. pipeline/stt.py 구성

- `AUDIO_BUCKET` — `api.storage`에서 import(단일 출처; `api.storage`는 pipeline을 import하지 않으므로 순환 없음).
- 설정(env, 기본값 — 필수 Config 키 아님):
  - `STT_MODEL` 기본 `small`
  - `STT_COMPUTE_TYPE` 기본 `int8`
  - `STT_DEVICE` 기본 `cpu`
- `_get_model() -> WhisperModel`: lazy 싱글턴. `WhisperModel(STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE)`. 최초 호출 시 모델 다운로드(라이브).
- `_download_audio(object_name: str) -> bytes`: `get_client().storage.from_(AUDIO_BUCKET).download(object_name)`.
- `transcribe(audio_file_name: str) -> str`: 위 흐름. 임시파일은 `tempfile.NamedTemporaryFile(suffix=원확장자, delete=False)`로 만들고 `finally`에서 `os.unlink`. 확장자는 `PurePosixPath(audio_file_name).suffix or ".wav"`.

## 4. engine.process 변경 (통합 보정)

`backend/src/ggotaiorder/pipeline/engine.py`의 STT 블록:
- 호출을 비블로킹으로: `stt_text = await asyncio.to_thread(transcribe, row.audio_file_name)` (CPU 바운드 STT가 이벤트 루프 블로킹 방지). `import asyncio` 추가.
- 예외 처리: 기존 `except NotImplementedError` → `except Exception`(로깅 후 return). STT가 더는 NotImplementedError를 던지지 않으므로 다운로드/모델/디코딩 실패를 포괄.
- 나머지 흐름(추출·필터·INSERT·enqueue)은 불변.

## 5. 에러 처리

- 다운로드 실패·모델 로드 실패·오디오 디코딩 실패 → `transcribe`가 예외 전파 → engine이 `except Exception`으로 잡아 로깅 후 해당 건 skip(파이프라인 비중단).
- 빈 변환 결과(`""`)는 그대로 반환 → 이후 Gemini 추출에서 누락 다수 → is_order='N'으로 자연 처리.

## 6. 테스트

- `test_pipeline_stt.py` 재작성(오프라인 결정적):
  - `_download_audio`를 `lambda name: b"fake-bytes"`로, `_get_model`을 가짜 모델 반환으로 monkeypatch. 가짜 모델의 `transcribe(path, language=...)`는 `([Seg("안녕하세요"), Seg("꽃 주문이요")], None)` 반환.
  - `transcribe("2/x.wav")` == `"안녕하세요 꽃 주문이요"` 검증.
  - 임시파일이 정리되어 남지 않음을 검증(테스트 전후 temp 디렉토리 비교 또는 transcribe가 생성한 경로를 캡처해 미존재 확인).
- `test_pipeline_engine.py` 갱신:
  - 기존 `test_stt_needed_but_stub_skips` 대체 → `engine.transcribe` monkeypatch: (a) 정상 텍스트 반환 시 update_stt_text 호출 + 추출/INSERT 진행, (b) `transcribe`가 예외 → skip(insert 미호출) 검증. `engine.extract_order`/`enqueue`도 monkeypatch.
- `test_pipeline_stt_live.py`(opt-in): `pytest.mark.skipif(RUN_LIVE_STT != "1")`. `STT_SAMPLE_PATH` env의 로컬 한국어 음성으로 `_get_model().transcribe(path, language="ko")` 실행, 텍스트 비어있지 않음 확인. 기본 skip.
- 기존 50 passed 회귀 유지.

## 7. 의존성

`faster-whisper`·`ctranslate2`는 이미 설치됨. 추가 없음.

## 8. 라이브 구동 체크리스트 (인프라/샘플 준비 시)

1. 최초 실행 시 `small` 모델 자동 다운로드(~460MB) — 네트워크·디스크 필요.
2. `call-audio` 버킷에 실제 통화 음성이 적재돼 있어야 함(인입 경로 증분의 버킷 생성 선행).
3. 한국어 샘플 음성 + `RUN_LIVE_STT=1 STT_SAMPLE_PATH=...`로 opt-in 라이브 테스트 1회.
4. E2E: 업로드 → server_call_history → STT → Gemini → order_details 생성 확인.

## 9. 비범위(후속)

- scraper(Playwright)·rpa·notifier 실구현.
- STT 정확도 튜닝(beam_size, vad_filter 등), 모델 캐시 경로 관리.
