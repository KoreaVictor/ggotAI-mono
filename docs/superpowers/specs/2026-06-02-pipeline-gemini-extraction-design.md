# pipeline 모듈 실구현 (Gemini 추출 + 필터 + DB) 설계서

작성일: 2026-06-02
범위: `ggotaiorder.pipeline` 스텁을 실구현으로 — STT는 인터페이스만, Gemini 11필드 구조화 추출 + 누락 필터 + DB 기록 + RPA 큐 호출.
브랜치: `chore/gemini-sdk-swap` (SDK 교체에 이어 동일 브랜치)

---

## 1. 목표와 범위

PRD 6-4(AI 데이터 정형화 파이프라인) 중 **Gemini 추출 + 꽃주문 판별 필터 + order_details 기록 + rpa.enqueue** 경로를 실제 동작하도록 구현한다.

- **이번 증분에 포함(실로직)**: Gemini 11필드 구조화 추출, "누락 3개↑ → is_order='N'" 판별, server_call_history 상태 갱신, order_details INSERT(rpa_status='ready'), rpa.enqueue 호출, DB repository 추상화, config에 `GEMINI_API_KEY` 추가.
- **인터페이스만(스텁 유지)**: STT(`transcribe(audio_path) -> str`) — faster-whisper 실연동은 다음 증분(모델 다운로드·음성 샘플 필요).
- **검증**: repository fake 기반 단위테스트 + 실제 Gemini 스모크 1건(키 있을 때만).

비범위: faster-whisper 실STT, Supabase Storage 음성 다운로드/삭제의 실연동(인터페이스만 호출, 실제 삭제는 repository 메서드로 위임하되 이번엔 Storage 미연동 시 no-op 로깅 허용), 크롤러/실시간/알림 모듈.

## 2. Gemini 추출 접근법

`google-genai` SDK의 **구조화 출력**을 사용한다.
- `client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=OrderExtraction, temperature=0))`
- `OrderExtraction`은 Pydantic 모델(11필드, 모두 Optional). SDK가 스키마에 맞춰 파싱된 객체를 돌려준다.
- 파싱 실패/스키마 위반은 예외로 잡아 로깅 후 해당 건 skip(파이프라인 비중단).

## 3. 모듈 분해

```
backend/src/ggotaiorder/pipeline/
├─ engine.py       # process(call_history_id) 오케스트레이션 (얇게)
├─ extractor.py    # extract_order(stt_text) -> OrderExtraction (Gemini 구조화 호출)
├─ stt.py          # transcribe(audio_path: str) -> str  [인터페이스 스텁]
├─ models.py       # Pydantic OrderExtraction(11필드 Optional), CallHistory(repo 반환 DTO)
└─ repository.py   # OrderRepository(Protocol) + SupabaseOrderRepository
```
- 테스트용 `FakeOrderRepository`는 `backend/tests/`에 둔다.
- `engine.process`는 `OrderRepository`를 주입받는다(기본값으로 SupabaseOrderRepository 생성). 이를 통해 단위테스트는 fake를 주입한다.

### 11필드 (ORDER_FIELDS, 기존 스텁과 동일)
`customer_name, customer_phone_number, product_name, quantity, price, delivery_at, delivery_place, receiver_name, receiver_phone_number, ribbon_congratulations, card_message`

- `quantity`, `price` 는 정수(Optional[int]), `delivery_at` 는 문자열(ISO 또는 자연어, Optional[str]), 나머지 Optional[str].
- 기존 `engine.py`의 `ORDER_FIELDS` 상수는 유지하고 `models.py`/판별 로직이 이를 단일 출처로 참조한다.

## 4. 데이터 흐름 — `process(call_history_id: int)`

1. `row = repo.get_call_history(call_history_id)` → `CallHistory`(id, shop_key, shop_name, customer_name, customer_phone_number, stt_text, audio_file_name, channel_order).
2. **STT 필요 판단**: `row.stt_text`가 비어있고 `row.audio_file_name`이 실제 음성(값이 있고 `INTRANET_CRAWLED`가 아님)이면 → `text = stt.transcribe(row.audio_file_name)` 후 `repo.update_stt_text(id, text)`. STT는 이번 증분 스텁이라 `NotImplementedError`를 던지며, engine은 이를 잡아 경고 로깅 후 해당 건 skip(주문 판별로 진행하지 않음). 즉 **이번 증분에서 실제로 끝까지 도는 경로는 stt_text가 이미 채워진 건**(인트라넷·테스트 데이터).
3. `extraction = extractor.extract_order(stt_text)` → `OrderExtraction`(누락은 None).
4. `missing = count_missing(extraction)` (None 또는 공백 문자열 개수).
   - `missing >= 3` → `repo.set_is_order(id, 'N')`; `repo.delete_audio(row.audio_file_name)`(있을 때); 종료.
5. else → `repo.set_is_order(id, 'Y')`; `order_id = repo.insert_order_details(payload)` (payload = 11필드 + shop_key/shop_name/call_history_id, customer_* 보강, rpa_status='ready'); `await rpa.enqueue(order_id)`.

`customer_name`/`customer_phone_number`가 추출에서 비었으면 `row`의 값으로 보강한다(전화 채널은 발신번호가 이미 있음).

## 5. config 변경

- `Config`에 `gemini_api_key: str` 추가. `_REQUIRED_KEYS`에 `GEMINI_API_KEY` 포함, 비어있으면 `ConfigError`.
- `test_config.py`의 `VALID`에 `GEMINI_API_KEY` 추가, 누락 테스트 케이스 보강.
- 모델명 상수 `GEMINI_MODEL = "gemini-2.5-flash"` (extractor.py).
- extractor는 `genai.Client(api_key=load_config().gemini_api_key)`를 지연 생성(모듈 import 시 네트워크/키 요구 없음 → 테스트가 키 없이도 import 가능).

## 6. 에러 처리

- Gemini 호출/파싱 실패: 예외 로깅 후 해당 call 건 skip(예외 전파 안 함) — 파이프라인 워커가 죽지 않도록.
- repository 예외: 로깅 후 전파(상위 호출자가 인지). 단 `delete_audio`/Storage 미연동은 경고 no-op 허용.
- STT 미구현: `NotImplementedError`를 engine이 잡아 경고 로깅.

## 7. 테스트

- `test_pipeline_filter.py`: `count_missing`/판별 순수 로직 — 0·2·3·전체누락 경계, 공백 문자열 처리, 숫자 None 처리.
- `test_pipeline_engine.py` (FakeOrderRepository + spy enqueue, `monkeypatch`로 extractor.extract_order 대체):
  - Y경로: 누락<3 → `set_is_order('Y')`, `insert_order_details` 호출(payload 검증), `rpa.enqueue(order_id)` 호출.
  - N경로: 누락≥3 → `set_is_order('N')`, insert 미호출, `delete_audio` 호출.
  - 인트라넷 경로: stt_text 존재 + audio=`INTRANET_CRAWLED` → STT 건너뛰고 추출 진행.
  - STT 필요 경로: stt_text 비고 audio 음성 → transcribe 스텁의 NotImplementedError를 잡아 skip(insert/enqueue 미호출) 검증.
- `test_pipeline_extractor_live.py`: `GEMINI_API_KEY` 있을 때만 실행(`pytest.mark.skipif`/환경 확인). 한국어 주문 예문("내일 오후 3시 강남 배달, 김철수 생일 축하 꽃다발 5만원, 받는분 이영희 010-...")에서 product_name/receiver_name 등 핵심 필드가 비지 않음을 확인.
- 비동기 테스트를 위해 `pytest-asyncio`를 requirements에 추가하고 `pyproject.toml`에 `asyncio_mode = "auto"` 설정.
- 기존 27 테스트 회귀 유지.

## 8. 의존성/패키지 변경

- `requirements.txt`: `pydantic`(google-genai 의존이라 이미 설치돼 있으나 직접 의존으로 명시), `pytest-asyncio` 추가.
- `pyproject.toml`: `[tool.pytest.ini_options]`에 `asyncio_mode = "auto"`.

## 9. 비범위(다음 증분)

- faster-whisper 실 STT + Supabase Storage 음성 다운로드/삭제 실연동.
- realtime/api가 `process`를 실제 트리거하도록 배선(현재 오케스트레이터는 스텁 호출만).
- Gemini 프롬프트 정밀 튜닝/few-shot, 비용·레이트리밋 대응.
