# 스마트스토어 커머스API 연동 설계서

작성일: 2026-07-04
범위: 네이버 커머스API(공식)로 스마트스토어 신규주문을 수집해 `order_details`(rpa_status='ready')로 적재하고, FlowerNT RPA 입력 성공 후 자동 발주확인까지 수행. 기존 `scraper/`(인터라넷 크롤러)와 대칭인 새 `mall/` 모듈로 구현. 실제 커머스API 호출(OAuth2·주문조회·발주확인)은 client_id/secret 확보 전까지 스텁으로 두고 fake 클라이언트로 오프라인 검증.
기준 브랜치: master. 작업 브랜치 `feature/smartstore-commerce-api`.

---

## 1. 목표와 범위

PRD F3(쇼핑몰 주문 자동 연동, "공식 주문 수집 API")의 스마트스토어 구현. 인터라넷 크롤러와 동일한 오케스트레이션 골격을 쓰되, Playwright 스크래퍼 대신 커머스API 클라이언트를 끼운다.

- **포함(실로직, 오프라인 테스트)**: `mall_credentials` 자격 목록 로드, client_secret 복호화, (추상화된) 신규주문 수집, 중복 검증, 하이브리드 필드 매핑(API 정형값 + 메모 Gemini 병합), server_call_history + order_details 직접 INSERT, rpa.enqueue, RPA 성공분 자동 발주확인 스캐너, 연속 실패 비상 알림, shop별 격리.
- **연기(라이브/체크리스트)**: 실제 커머스API OAuth2 토큰 발급(bcrypt 서명)·주문조회·발주확인 HTTP 호출(client_id/secret 필요). 단, bcrypt 서명 생성은 결정적이라 단위테스트 대상.
- **비범위(후속)**: ggotAIya UI의 자격증명 입력 화면(초기엔 시드 스크립트로 주입), 쿠팡 클라이언트 구현(테이블만 대응), 전용 비상/성공 알림 문구.

## 2. 아키텍처

`mall.collector.poll_once`(APScheduler 주기 호출)는 오케스트레이션만 담당한다. 커머스API 상호작용은 `SmartStoreClient`(Protocol), DB는 `MallCredentialRepository`/`MallOrderRepository`(Protocol)로 추상화 → 오프라인 테스트는 fake 주입. 자동 발주확인은 RPA 내부에 결합하지 않고, 별도 `MallConfirmScanner`가 rpa_status='success' 행을 폴링해 처리한다(기존 `RpaRetryScanner`/`CatchupScanner` 패턴). 이로써 외부 쓰기(발주확인)는 **RPA 성공이 DB에 확정된 뒤에만** 일어난다.

## 3. 파일 구조

```
backend/src/ggotaiorder/mall/
├─ __init__.py
├─ models.py            # MallCredential, SmartStoreOrder, 상수(SMARTSTORE_CHANNEL, 마커, provider)
├─ credentials_repo.py  # MallCredentialRepository(Protocol) + SupabaseMallCredentialRepository
├─ order_repo.py        # MallOrderRepository(Protocol) + SupabaseMallOrderRepository
├─ smartstore_client.py # SmartStoreClient(Protocol) + HttpSmartStoreClient(실구현, 초기 스텁)
├─ collector.py         # poll_once 수집 오케스트레이션
└─ confirm_scanner.py   # MallConfirmScanner — RPA 성공분 자동 발주확인
backend/scripts/
└─ seed_mall_credential.py   # 초기 자격증명 시드(enable_rpa_shop.py 방식)
```

### 3.1 models.py

```python
SMARTSTORE_CHANNEL = "쇼핑몰"           # server_call_history.channel_order
SMARTSTORE_AUDIO_MARKER = "SMARTSTORE_API"  # audio_file_name — provider 식별 마커(INTRANET_CRAWLED 대칭)
PROVIDER_SMARTSTORE = "smartstore"

@dataclass
class MallCredential:
    shop_key: int
    shop_name: str
    provider: str            # 'smartstore'
    client_id: str
    enc_client_secret: str   # AES 암호문(복호화 전)
    extra: dict              # store_id 등 (jsonb)
    cursor: str | None       # last-changed 조회 커서(ISO8601), 없으면 None

@dataclass
class SmartStoreOrder:
    product_order_id: str    # 중복 식별키(channel_classification)
    raw_text: str            # 원문(배송메모+옵션 등, stt_text 로 저장)
    memo_text: str           # Gemini에 넣을 자유텍스트(메모+옵션+상품명)
    fields: OrderExtraction  # API 정형값으로 채운 11필드(권위 필드)
```

`fields`는 API 정형값(상품명·수량·가격·받는사람·전화·배송지·주문자)만 채우고, 배달일시·리본·카드·상품분류는 None으로 둔다(수집 단계에서 Gemini로 병합).

### 3.2 credentials_repo.py

```python
class MallCredentialRepository(Protocol):
    def list_credentials(self, provider: str) -> list[MallCredential]: ...
    def update_cursor(self, shop_key: int, provider: str, cursor: str) -> None: ...

class SupabaseMallCredentialRepository:
    # mall_credentials(is_active=true, provider=?) + member_info(shop_name) 조인 → MallCredential 목록
    # update_cursor: 마지막 조회 시점 저장(다음 폴링 lastChangedFrom 기준)
```

### 3.3 order_repo.py

```python
class MallOrderRepository(Protocol):
    def order_exists(self, shop_key: int, product_order_id: str) -> bool: ...
    def insert_call_history(self, record: dict) -> int: ...
    def insert_order_details(self, payload: dict) -> int: ...
    # 발주확인 스캐너용
    def list_confirmable(self, provider_marker: str) -> list[ConfirmTarget]: ...
    def mark_ack(self, order_id: int, status: str) -> None: ...
    def increment_ack_attempts(self, order_id: int) -> int: ...
```

- `order_exists`: server_call_history에서 shop_key=, channel_order='쇼핑몰', channel_classification=product_order_id 존재 여부(중복 방지).
- `list_confirmable`: order_details ⨝ server_call_history 조인으로 `rpa_status='success' AND mall_ack_status='pending' AND audio_file_name='SMARTSTORE_API'` 행 → ConfirmTarget(order_id, shop_key, product_order_id, ack_attempts) 목록.
- `mark_ack`: mall_ack_status를 'confirmed'|'skipped'로. `increment_ack_attempts`: 재시도 상한 관리.

### 3.4 smartstore_client.py

```python
class SmartStoreClient(Protocol):
    def fetch_new_orders(self, cred: MallCredential) -> tuple[list[SmartStoreOrder], str]:
        """결제완료(PAYED) 신규주문 목록과 다음 커서를 반환."""
    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        """발주확인(승인) — 외부 쓰기."""

class HttpSmartStoreClient:
    # TODO(라이브): OAuth2 토큰(client_secret bcrypt 서명, ~3h 캐시)
    #   → last-changed-statuses(lastChangedFrom=cursor, status=PAYED)
    #   → product-orders/query 상세 → SmartStoreOrder 매핑
    #   → confirm_order: /product-orders/{id}/confirm(발주확인)
    # 실제 HTTP는 client_id/secret 확보 후. fetch/confirm 스텁은 NotImplementedError.
    # 단, _make_signature(client_id, client_secret, ts)(bcrypt) 는 지금 구현 + 단위테스트.
```

토큰은 프로세스 메모리에 만료시각까지 캐시. `enc_client_secret`은 `core.crypto.decrypt` + `AES_ENCRYPTION_KEY` 재사용(기존 crypto 검증됨).

## 4. collector.py — poll_once 오케스트레이션

```
poll_once(*, cred_repo=None, order_repo=None, client=None, notify=None, extract=None):
  cred_repo   = cred_repo   or SupabaseMallCredentialRepository()
  order_repo  = order_repo  or SupabaseMallOrderRepository()
  client      = client      or HttpSmartStoreClient()
  extract     = extract     or pipeline.extractor.extract_order   # 메모 Gemini
  creds = await to_thread(cred_repo.list_credentials, PROVIDER_SMARTSTORE)
  for cred in creds:
    secret = decrypt(cred.enc_client_secret, config.aes_encryption_key)  # cred에 주입
    try:
      orders, next_cursor = await to_thread(client.fetch_new_orders, cred)
    except Exception:
      logger.exception(...); _record_failure(cred.shop_key, notify); continue
    _reset_failure(cred.shop_key)
    for order in orders:
      if await to_thread(order_repo.order_exists, cred.shop_key, order.product_order_id): continue
      merged = _merge_fields(order, extract)          # 하이브리드 병합
      call_id  = await to_thread(order_repo.insert_call_history, _call_record(cred, order))
      order_id = await to_thread(order_repo.insert_order_details, _order_payload(cred, merged, call_id))
      await enqueue(order_id)
    await to_thread(cred_repo.update_cursor, cred.shop_key, PROVIDER_SMARTSTORE, next_cursor)
```

- `_merge_fields(order, extract)`: `soft = extract(order.memo_text)` 호출 후, `order.fields`(API 권위값)를 기준으로 **배달일시·delivery_at_text·리본(ribbon_congratulations)·카드(card_message)·상품분류(sang_divi)만 soft에서 취해** 합친 `OrderExtraction` 반환. API가 이미 채운 상품명·수량·가격·받는사람·전화·배송지·주문자는 절대 덮지 않음.
- `_call_record(cred, order)`: `{channel_order:'쇼핑몰', channel_classification: product_order_id, shop_key, shop_name, customer_*: API값, call_date/call_time: now, duration_seconds:0, audio_file_name: SMARTSTORE_AUDIO_MARKER, stt_text: order.raw_text, is_order:'Y'}`.
- `_order_payload(cred, merged, call_id)`: 기존 `pipeline.engine._build_order_payload`와 동일 규칙(NOT NULL 안전 기본값, delivery_at 정규화·센티넬 폴백)을 재사용/공유하되 `mall_ack_status='pending'`, `rpa_status='ready'` 추가.
- 연속 실패 카운터: 모듈 수준 `_failure_counts: dict[int,int]`. 임계치(3) 도달 시 `notify(shop_key)`(실패 템플릿) 후 리셋. 인터라넷과 동일 로직.
- 블로킹(repo·client·decrypt·extract)은 `asyncio.to_thread` 오프로드. cred별 try/except 격리. 커서 갱신은 해당 shop 처리 끝에서(부분 성공 시 다음 폴링이 재조회로 보완).

> 참고: `_build_order_payload`/`_normalize_delivery_at`는 현재 `pipeline.engine`에 있다. mall과 공유하기 위해 `pipeline/order_payload.py`(또는 pipeline 공용 헬퍼)로 추출해 engine·collector가 함께 임포트한다(중복 방지·단일 출처). engine 동작은 불변.

## 5. confirm_scanner.py — 자동 발주확인

```
class MallConfirmScanner:
  async def scan_once(*, order_repo=None, client=None, cred_repo=None):
    targets = await to_thread(order_repo.list_confirmable, SMARTSTORE_AUDIO_MARKER)
    creds_by_shop = { c.shop_key: c for c in cred_repo.list_credentials(PROVIDER_SMARTSTORE) }
    for t in targets:
      cred = creds_by_shop.get(t.shop_key)
      if cred is None: continue
      attempts = await to_thread(order_repo.increment_ack_attempts, t.order_id)
      try:
        await to_thread(client.confirm_order, cred, t.product_order_id)
        await to_thread(order_repo.mark_ack, t.order_id, "confirmed")
      except Exception:
        logger.exception("발주확인 실패 order_id=%s", t.order_id)
        if attempts >= _ACK_MAX_ATTEMPTS:
          await to_thread(order_repo.mark_ack, t.order_id, "skipped")   # 상한 초과 → 수동 확인 대상
```

- `_ACK_MAX_ATTEMPTS`(예: 5) 도달 시 'skipped'로 마킹해 무한 재시도 차단(pipeline.MAX_ATTEMPTS 관례와 동일). skip 시 경고 로그(후속: 사장님 알림 문구).
- 오케스트레이터에 스케줄 배선: `mall_confirm`(interval, 예: 5분, paused면 스킵) + 부팅 1회(`date`).

## 6. 스키마 변경 (Supabase 마이그레이션)

**신규 `mall_credentials`** (멀티프로바이더·쿠팡 대응):
```sql
CREATE TABLE mall_credentials (
    id SERIAL PRIMARY KEY,
    shop_key INT NOT NULL,
    provider VARCHAR(20) NOT NULL,             -- 'smartstore' | 'coupang'
    client_id VARCHAR(255) NOT NULL,
    enc_client_secret TEXT NOT NULL,           -- AES 암호문
    extra JSONB DEFAULT '{}'::jsonb,           -- store_id 등 provider별 부가정보
    cursor TIMESTAMPTZ DEFAULT NULL,           -- last-changed 조회 커서
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(shop_key, provider),
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);
```

**`order_details` 컬럼 2개 추가**:
```sql
ALTER TABLE order_details
  ADD COLUMN mall_ack_status VARCHAR(20) DEFAULT NULL,  -- NULL=비쇼핑몰, 'pending'|'confirmed'|'skipped'
  ADD COLUMN mall_ack_attempts INT DEFAULT 0;           -- 발주확인 재시도 카운트(상한용)
```
provider·product_order_id는 각각 server_call_history의 `audio_file_name` 마커·`channel_classification`으로 이미 식별되므로 별도 컬럼 불필요(조인으로 해결). `mall_ack_attempts`는 스캐너 `increment_ack_attempts`/`_ACK_MAX_ATTEMPTS` 상한 관리용.

## 7. 오케스트레이터 배선

`orchestrator.py`에 추가:
- `smartstore_poll`(interval, 기본 `setting_info.shopping_mall_check_interval` 또는 상수 10분; paused 스킵) → `mall.collector.poll_once`. `_scheduled_poll`과 동형의 `_scheduled_mall_poll` 추가.
- `mall_confirm`(interval 5분 + 부팅 1회 `date`; paused 스킵) → `MallConfirmScanner.scan_once`.

## 8. 에러 처리

- cred 단위 try/except: 한 shop 실패가 다른 shop·전체 폴링을 막지 않음(인터라넷과 동일).
- 수집 연속 실패 임계치(3) → `notifier.send(shop_key, channel='쇼핑몰', count=0, success=False)` 비상 알림.
- insert/enqueue 실패는 로깅 후 다음 주문으로(주문 단위 보호). 커서는 갱신 안 함 → 다음 폴링이 재시도.
- 발주확인 실패는 스캐너가 재시도, 상한 초과 시 'skipped'(수동 확인).
- Gemini(extract) 실패 시 해당 주문은 soft 필드 없이 정형값만으로 적재(배달일시 센티넬)하거나 스킵 후 다음 폴링 재시도 — **정형값이 이미 유효하므로 soft 실패는 치명적이지 않게**: soft 예외를 잡아 빈 병합으로 진행(주문 유실 방지).

## 9. 테스트 (오프라인 결정적, 기존 test_scraper.py 스타일)

`test_mall_collector.py` — fake cred_repo/order_repo/client + fake extract + spy enqueue/notify:
- 신규 주문 1건 → insert_call_history(channel_order='쇼핑몰', channel_classification=product_order_id, audio=SMARTSTORE_AUDIO_MARKER) + insert_order_details(rpa_status='ready', mall_ack_status='pending') + enqueue(order_id) + update_cursor(next_cursor) 호출.
- 하이브리드 병합: API 정형값이 Gemini soft값을 덮지 않음(product_name/price 등 유지), soft에서 delivery_at·ribbon·card·sang_divi만 반영.
- 중복(order_exists True) → insert/enqueue 미호출.
- client.fetch 예외 → 실패 카운터 증가; 3회째 notify(shop_key); 성공 폴링 끼면 리셋; 커서 미갱신.
- Gemini(extract) 예외 → 정형값만으로 적재 진행(주문 유실 없음).
- 다중 shop 격리.

`test_mall_confirm_scanner.py`:
- rpa_status='success'+pending 대상 → confirm_order 호출 후 mark_ack('confirmed').
- confirm 예외 → 재시도, 상한 초과 시 mark_ack('skipped').
- cred 없는 shop → 스킵.

`test_smartstore_signature.py`:
- `_make_signature`(bcrypt) 결정성/형식 단위테스트(고정 client_id·secret·ts → 검증 가능한 서명).

`SupabaseMall*Repository`·`HttpSmartStoreClient`의 HTTP 부분은 라이브 영역(import 확인만).
기존 테스트 전량 회귀. 비동기 테스트 `asyncio_mode="auto"`.

## 10. 라이브 구동 체크리스트

1. 커머스API센터에서 애플리케이션 등록 → client_id/client_secret 발급.
2. `HttpSmartStoreClient`의 OAuth2 토큰·주문조회·발주확인 HTTP 구현(bcrypt 서명은 이미 구현·테스트됨).
3. `seed_mall_credential.py`로 mall_credentials에 자격증명 주입(client_secret은 AES 암호화 저장).
4. `smartstore_poll` 1회 실행 → 결제완료 신규주문 수집·중복 skip·order_details 생성 확인.
5. RPA 성공 후 `mall_confirm` → 발주확인 반영 확인. 실패 3회 시 비상 알림 확인.

## 11. 비범위(후속)

- ggotAIya UI 자격증명 입력 화면(초기엔 시드 스크립트).
- 쿠팡 `CoupangClient` 구현(mall_credentials·order_details 스키마는 이미 대응).
- 전용 비상/발주확인 실패 알림 문구, 알림 이력 테이블.
- 자동 발주확인 on/off 설정 토글(현재는 항상 on; 필요 시 setting_info 플래그 추가).
