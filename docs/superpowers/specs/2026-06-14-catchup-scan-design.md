# 부팅 시 catch-up 스캔 — 설계서 (2026-06-14)

## 1. 배경 / 문제

핸드폰(`channel_order='핸드폰'`)·가게음성 채널 주문은 Supabase **Realtime** `server_call_history`
INSERT 구독으로 실시간 처리된다(`realtime/listener.py`). 그러나 Realtime(postgres_changes)은
**구독 중 발생한 이벤트만** 전달하고 오프라인 동안의 INSERT는 재생하지 않는다.

따라서:
- **PC가 꺼져 있던 동안** ggotAIhp가 INSERT한 통화 행(오디오만, `stt_text=NULL`, `is_order='N'`)은
  부팅 후에도 자동 처리되지 않는다.
- 켜져 있어도 **절전/네트워크 끊김**(관측: 절전 진입 시 `WebSocket closed 1006`)으로 리스너가
  잠시 누락한 행도 같은 미처리 상태로 남는다.

현재 코드에는 미처리분을 따라잡는 backfill 로직이 전혀 없다(`orchestrator.start()`의 주기 작업은
인트라넷 크롤러 전용). 본 설계는 **부팅 시 1회 + 주기적 안전망** catch-up 스캔을 추가한다.

## 2. 목표 / 비목표

**목표**
- 미처리 핸드폰/가게음성 통화 행을 자동으로 찾아 기존 `pipeline.process()`로 처리.
- 부팅 직후 1회 + 이후 30분 주기 스캔으로 오프라인/절전 누락분 복구.
- Realtime 경로와의 **중복 처리(이중 주문 INSERT) 방지**.
- 영구 실패 행의 **무한 재시도 방지**.

**비목표**
- 멀티샵 shop_key 필터(별도 과제). 단일 PC = 단일 샵 전제.
- 인트라넷/쇼핑몰 채널(이미 크롤러/ api가 직접 처리).
- 중복 방지를 위한 분산 락(단일 asyncio 루프 내 in-process 가드로 충분).

## 3. 데이터 모델 (마이그레이션)

`server_call_history`에 컬럼 2개 추가:

| 컬럼 | 타입 | 기본값 | 의미 |
|------|------|--------|------|
| `processed_at` | `TIMESTAMPTZ` | `NULL` | 파이프라인이 **종결**(주문 'Y' / 비주문 'N')을 낸 시각. `NULL` = 미처리 |
| `process_attempts` | `INT` | `0 NOT NULL` | 처리 시도 횟수. 영구 실패 행을 스캔에서 제외하는 상한 적용용 |

- 둘 다 nullable / default 이므로 **ggotAIhp의 기존 INSERT 무손상**(컬럼 미지정 → NULL/0).
- 산출물:
  - `docs/database_schema.sql` 의 `server_call_history` 정의에 두 컬럼 반영.
  - `docs/migrations/2026-06-14-catchup-scan.sql` (기존 마이그레이션 파일 패턴).

## 4. 식별 쿼리 (백필 대상)

```sql
SELECT id FROM server_call_history
WHERE channel_order IN ('핸드폰','가게음성')   -- engine._REALTIME_CHANNELS 재사용(단일 출처)
  AND processed_at IS NULL
  AND process_attempts < 5                     -- MAX_ATTEMPTS
ORDER BY id;
```

- "꺼진 동안 들어온 주문"(오디오만 있는 행)뿐 아니라, STT/Gemini 일시 실패로 종결 못 낸 행까지 재시도.
- 5회 시도 후에도 종결 못 낸 행은 스캔에서 빠진다(무한 루프 방지). 사후 점검은
  `WHERE process_attempts >= 5 AND processed_at IS NULL` 쿼리로.

## 5. 파이프라인 변경 (`pipeline/engine.py`)

### 5.1 처리 종결 표시
- 기존 두 종결 분기(주문 아님 `set_is_order(id,'N')`, 주문 생성 후 `set_is_order(id,'Y')`)를
  **`mark_processed(id, value)`** 로 교체 → 한 번의 UPDATE로 `is_order` + `processed_at = now()` 기록.
- STT 없음/STT 실패/Gemini 실패/INSERT 실패의 **조기 리턴**에서는 `processed_at`를 찍지 않는다
  → 다음 스캔이 (상한까지) 재시도.

### 5.2 시도 횟수 증가
- `process()` 진입 직후(아래 in-flight 가드 통과 후, 첫 실제 작업 이전) `process_attempts += 1`.
  실패해도 카운트되어 상한이 적용된다.

### 5.3 중복 처리 방지 (in-flight 가드)
- 오케스트레이터는 단일 asyncio 이벤트 루프이므로, `engine` 모듈 레벨 `_in_flight: set[int]` 사용.
- `process(call_history_id)` 진입 즉시(첫 `await` 이전, 동기 구간):
  ```
  if call_history_id in _in_flight: return     # 이미 처리 중 → 스킵
  _in_flight.add(call_history_id)
  try:
      ... 기존 로직 ...
  finally:
      _in_flight.discard(call_history_id)
  ```
- Realtime 콜백과 스캐너가 같은 id를 동시에 스케줄해도 한 번만 처리된다(단일 루프에서 add가 첫
  await 이전에 일어나므로 원자적). → `order_details` 중복 INSERT 차단.

## 6. 스캐너 (`pipeline/catchup.py`)

```
class CatchupScanner:
    def __init__(self, repo: OrderRepository | None = None): ...
    async def scan_once(self) -> int:
        """미처리 핸드폰/가게음성 행을 조회해 순차적으로 process(id)를 호출. 처리 건수 반환."""
        ids = await asyncio.to_thread(self._repo.list_pending_call_ids,
                                      _REALTIME_CHANNELS, MAX_ATTEMPTS)
        for cid in ids:
            await process(cid, repo=self._repo)   # in-flight 가드가 Realtime과 dedup
        return len(ids)
```

- **순차 await**: 야간 백로그를 직렬 처리해 Gemini/STT 레이트리밋 버스트를 피한다(백로그는 통상 소량).
- 스캔 도중 도착하는 신규 INSERT는 Realtime이 받고, in-flight 가드가 중복을 막는다.

## 7. 오케스트레이터 배선 (`orchestrator.py`)

`start()` 순서:
1. `await self._listener.start()` — Realtime 구독.
2. **부팅 1회** `await self._scanner.scan_once()` — 구독 이후 실행(스캔 중 도착분은 Realtime이 처리).
3. APScheduler 인터벌 잡 `catchup_scan` 추가: **30분 주기**, `max_instances=1`(겹침 방지),
   `_paused`면 스킵(기존 `_scheduled_poll`과 동일 정책).
4. 기존 인트라넷 폴링 잡 + uvicorn 유지.

상수: `_CATCHUP_INTERVAL_MIN = 30`, `MAX_ATTEMPTS = 5` (engine 또는 catchup 모듈).

## 8. 리포지토리 계약 (`pipeline/repository.py`)

`OrderRepository` Protocol + `SupabaseOrderRepository` + 테스트 `FakeOrderRepository`에 추가:
- `list_pending_call_ids(channels: set[str], max_attempts: int) -> list[int]`
- `increment_attempts(call_history_id: int) -> None`
- `mark_processed(call_history_id: int, is_order: str) -> None`  (기존 `set_is_order` 대체:
  `is_order` + `processed_at=now()` 동시 기록)

> `set_is_order` 호출부는 전부 `mark_processed` 로 교체. `processed_at`는 **클라이언트가
> `datetime.now(timezone.utc).isoformat()` 으로 채워 PostgREST UPDATE**로 기록한다(단일 PC =
> 단일 시각원, 보안 민감도 없음 → DB now() RPC 불필요). 값 자체는 "미처리 판별용 NULL 여부"가
> 핵심이라 초 단위 정밀도면 충분.

## 9. 동시성 / 엣지 케이스

| 상황 | 처리 |
|------|------|
| Realtime + 스캔이 같은 id 동시 | in-flight 가드로 1회만 |
| 스캔 인터벌 겹침 | APScheduler `max_instances=1` |
| 영구 실패 행 | attempts 5 도달 시 스캔 제외 |
| 절전 후 WS 끊김 누락 | 30분 스캔이 복구 |
| STT 성공 후 Gemini 실패 | processed_at 미기록 → 재시도(상한까지) |
| 대량 백로그 | 순차 처리(직렬)로 레이트리밋 보호 |

## 10. 테스트 (TDD)

- **repository/Fake**: `list_pending_call_ids` 필터(채널·processed_at·attempts), `increment_attempts`,
  `mark_processed`(is_order+processed_at) 계약.
- **engine**: in-flight 가드가 동일 id 이중 호출을 1회로 / 종결 시 processed_at·is_order 기록 /
  attempts 증가 / 실패 조기리턴 시 processed_at 미기록.
- **catchup**: pending id만 스캔, 비대상 채널·attempts 상한 제외, Realtime과 idempotent.
- **orchestrator**: 부팅 1회 `scan_once` 호출 + 인터벌 잡 등록 + paused 시 스킵.
- 기존 스위트 회귀 0.

## 11. 배포 (구현 후)

- 라이브 Supabase에 §3 마이그레이션 적용 필요. **Supabase MCP는 Unauthorized**이므로:
  - (A) Management API(PAT) 직접 호출, 또는 (B) 사장님이 Supabase SQL 편집기에서 SQL 실행.
- 적용 후, 실행 중인 `ggotAIorder`(pythonw) 인스턴스를 새 코드로 재기동.
- 스모크: 합성 미처리 행(processed_at NULL) 삽입 후 `scan_once` 가 처리하는지 라이브 확인 → 정리.
