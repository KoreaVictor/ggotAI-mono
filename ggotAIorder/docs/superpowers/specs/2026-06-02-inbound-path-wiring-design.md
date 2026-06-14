# 인입 경로 배선 (api Webhook + Realtime → pipeline.process) 설계서

작성일: 2026-06-02
범위: 가게전화 Webhook과 Supabase Realtime 구독을 `pipeline.process`에 실제로 연결. 채널별 분리 트리거로 이중 처리 방지.
기준 브랜치: master (PR #2 머지 완료)

---

## 1. 목표와 범위

PRD 6-1(가게전화 Webhook)·6-2(Realtime 감시)를 실제 동작하도록 구현하여, 수집된 건이 `pipeline.process`로 흘러들어가는 **인입 경로**를 완성한다.

- **포함(실로직, 오프라인 테스트)**: api 업로드 엔드포인트(샵 판별·Storage 적재·server_call_history INSERT·process 백그라운드 예약), Realtime 리스너(구독 + 채널 필터 콜백), 샵 판별 repository, 오디오 Storage 추상화.
- **라이브 구동(체크리스트로 분리)**: Storage 버킷 생성, Realtime 활성화(Replication), 실제 구독 연결, 실제 멀티파트 업로드 — MCP/인프라 준비 시 수행.
- **비범위**: 실 STT(faster-whisper), Storage 음성 삭제 실연동, pipeline의 async sleep/부분쓰기 하드닝(별도 후속), 쇼핑몰 연동(F3).

> 인프라 메모: 현재 Supabase MCP 토큰이 미인증이라 이번 세션에서 버킷 생성/Realtime 활성화/라이브 조회 불가. 코드는 빌드+오프라인 검증하고 라이브는 체크리스트로 남긴다.

## 2. 아키텍처 — 채널별 분리 트리거

`server_call_history` INSERT를 트리거로 `pipeline.process`가 도는데, 채널마다 트리거 주체를 분리해 이중 처리를 막는다.

- **api (가게전화)**: 업로드 수신 → 샵 판별 → 음성 Storage 적재 → `server_call_history` INSERT(`channel_order='가게전화'`) → `process(id)`를 백그라운드 태스크로 예약 → 즉시 `accepted` 응답.
- **Realtime (핸드폰/가게음성)**: `server_call_history` INSERT 구독. payload의 `channel_order`가 `'핸드폰'` 또는 `'가게음성'`일 때만 `process(id)` 예약. `'가게전화'`(api가 처리)·`'인터라넷'`(크롤러가 처리)은 skip.
- **crawler (인트라넷)**: 기존대로 server_call_history + order_details 직접 INSERT (이 증분에서 변경 없음).

이로써 같은 행이 api와 Realtime 양쪽에서 중복 처리되지 않는다.

## 3. 파일 구조

```
backend/src/ggotaiorder/
├─ api/
│  ├─ routes.py        # create_app + POST /api/v1/gate-phone/upload (얇게: 의존성 주입 → service 호출 → BackgroundTasks)
│  ├─ service.py       # ingest_gate_phone(...) 오케스트레이션 → call_history_id | None
│  ├─ repository.py    # Shop, IngestRepository(Protocol) + SupabaseIngestRepository
│  └─ storage.py       # AudioStorage(Protocol) + SupabaseAudioStorage
└─ realtime/
   └─ listener.py      # 실제 구독(start/stop) + _handle_payload(payload) 채널 필터 → process 예약
```

각 단위는 단일 책임이며, Protocol로 추상화해 테스트에서 fake를 주입한다.

## 4. 컴포넌트 계약

### 4.1 api/repository.py
```python
@dataclass
class Shop:
    shop_key: int
    shop_name: str

class IngestRepository(Protocol):
    def find_shop_by_phone(self, phone: str) -> Shop | None: ...
    def insert_call_history(self, record: dict) -> int: ...
```
`SupabaseIngestRepository`:
- `find_shop_by_phone`: `setting_info`의 `order_landline_1/2`·`order_hp_1/2`에서 phone 일치하는 `shop_key`를 찾고, 없으면 `member_info`의 `landline_number/mobile_number`로 폴백. 찾은 shop_key로 `member_info`에서 `shop_name` 조회해 `Shop` 반환. 없으면 None.
- `insert_call_history(record)`: `server_call_history`에 insert, 새 `id` 반환.

### 4.2 api/storage.py
```python
class AudioStorage(Protocol):
    def upload_audio(self, data: bytes, dest: str) -> str: ...  # 저장된 object 이름 반환
```
`SupabaseAudioStorage`: 버킷 `call-audio`에 업로드. 객체 경로 `{shop_key}/{uuid}.{ext}`.

### 4.3 api/service.py
```python
async def ingest_gate_phone(
    *, file_bytes: bytes, filename: str, caller_number: str,
    call_duration: int, user_phone_number: str,
    repo: IngestRepository, storage: AudioStorage,
) -> int | None:
    """샵 판별 → 업로드 → INSERT. 반환: 새 call_history_id, 샵 미판별 시 None."""
```
흐름: `shop = repo.find_shop_by_phone(user_phone_number)`; None이면 None 반환(라우트가 400). 아니면 `object_name = storage.upload_audio(file_bytes, dest)`; `record` 구성 후 `repo.insert_call_history(record)` → id 반환.

`record` 필드: `channel_order='가게전화'`, `channel_classification=user_phone_number`, `customer_phone_number=caller_number`, `shop_key/shop_name`, `call_date`=오늘(YYYY-MM-DD), `call_time`=현재(HH:MM:SS), `duration_seconds=call_duration`, `audio_file_name=object_name`, `is_order='N'`.

### 4.4 api/routes.py
- `POST /api/v1/gate-phone/upload`: 멀티파트(`file`, `caller_number`, `call_duration`, `user_phone_number`) 수신 → `file.read()` → `ingest_gate_phone(...)` 호출.
  - None 반환 → `HTTP 400`(`{"detail": "shop not found"}`) + 경고 로그.
  - id 반환 → `BackgroundTasks`로 `pipeline.process(id)` 예약 → `{"status": "accepted", "call_history_id": id}`.
- repo/storage 의존성은 FastAPI `Depends`(또는 app.state)로 제공해 테스트에서 override.

### 4.5 realtime/listener.py
실시간 payload 스키마(supabase-py 버전별 키 차이)에 테스트가 결합되지 않도록, **얇은 콜백 추출**과 **테스트 가능한 처리 로직**을 분리한다.
- `start()`: supabase-py 비동기 realtime로 `server_call_history` INSERT 구독. 구독 콜백은 raw 메시지에서 record dict를 방어적으로 추출(`payload.get("data",{}).get("record") or payload.get("record") or payload.get("new")`)해 `_process_record(record)`에 넘긴다. (라이브 검증은 체크리스트)
- `_process_record(record: dict)`: `channel_order = record.get("channel_order")`. `{"핸드폰","가게음성"}`에 속하면 `asyncio.create_task(process(record["id"]))`. 아니면 skip. 예외는 잡아 로깅(리스너 유지). — **이 함수가 단위 테스트 대상**.
- `stop()`: 구독 해제.

## 5. 에러 처리

- 샵 미판별 → 400 + 경고(행 미생성).
- Storage/INSERT 실패 → 500 + 로깅(통신사 재시도 유도). process는 백그라운드라 응답 지연 없음.
- Realtime 콜백 예외 → 잡아 로깅(리스너 유지). payload 스키마 불일치도 방어적으로 로깅.

## 6. 테스트 (오프라인 결정적)

- `test_api_service.py`: `ingest_gate_phone` — fake repo+storage. 샵 있음(upload 호출·insert record 필드 검증·id 반환), 샵 없음(None·insert 미호출).
- `test_api_routes.py`: TestClient + 의존성 override(fake repo/storage, process spy). 정상 멀티파트 → 200 + `process` 백그라운드 호출(id 전달) 검증; 샵 없음 → 400.
- `test_realtime_listener.py`: `_process_record` — '핸드폰'/'가게음성' → process 호출(id), '가게전화'/'인터라넷' → 미호출, id 없는 record → 예외 없이 skip; process는 monkeypatch한 async spy.
- 라이브(버킷 생성·Realtime 활성화·실 구독·실 업로드)는 **체크리스트**로 분리, 인프라 준비 시 수행.
- 기존 39 테스트 회귀 유지.
- 비동기 테스트는 기존 `asyncio_mode="auto"` 사용.

## 7. 라이브 구동 체크리스트 (인프라 준비 시)

1. Supabase Storage에 `call-audio` 버킷 생성(비공개).
2. `server_call_history` 테이블 Realtime(Replication) 활성화 — PRD 8-2.
3. `run_dev.py`로 기동 후 멀티파트 업로드 → server_call_history 행 + order_details 생성 확인.
4. 모바일 앱(또는 수동 INSERT)으로 '핸드폰' 행 추가 → Realtime이 process 트리거하는지 확인.

## 8. 비범위(후속)

- pipeline async sleep 비블로킹화, is_order='Y' 부분쓰기 하드닝, order_details NOT NULL 기본값.
- 실 STT(faster-whisper) + Storage 음성 다운로드/삭제.
- 쇼핑몰 이메일/API 연동(F3), 알림(notifier)·RPA 실구현.
