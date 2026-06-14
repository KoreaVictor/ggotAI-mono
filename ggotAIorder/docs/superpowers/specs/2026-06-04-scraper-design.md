# scraper (인트라넷 정기 크롤러) 실구현 설계서

작성일: 2026-06-04
범위: `scraper/crawler.py` 스텁을 오케스트레이션 실구현으로 — 설정 로드 → (추상화된) 스크래핑 → 중복검증 → server_call_history + order_details 직접 INSERT → rpa.enqueue → 연속 실패 비상 알림. 실제 Playwright 로그인·셀렉터는 연기.
기준 브랜치: master (PR #5 머지 완료), 작업 브랜치 `feature/scraper`.

---

## 1. 목표와 범위

PRD 6-3/F4(인터라넷 채널 자동 크롤링)의 **오케스트레이션**을 구현한다. 사이트별 Playwright 동작은 `IntranetScraper`(Protocol) 뒤로 추상화한다.

- **포함(실로직, 오프라인 테스트)**: 설정 로드(intranet_url 보유 shop 목록), 비밀번호 복호화, (추상화된) 주문 수집, 중복 검증, server_call_history + order_details 직접 INSERT(AI 패스), rpa.enqueue 호출, 연속 3회 실패 시 notifier 비상 알림, shop별 격리.
- **연기(라이브/체크리스트)**: 실제 Playwright 로그인·목록·상세 셀렉터(실 사이트 필요), Playwright 브라우저 바이너리 설치.
- **비범위**: 전용 비상 알림 문구, rpa 실구현, 알림 이력 테이블.

## 2. 아키텍처

`poll_once`(APScheduler가 주기 호출, 오케스트레이터에 이미 배선됨)는 오케스트레이션만 담당한다. 사이트 상호작용은 `IntranetScraper` Protocol로, DB는 `IntranetRepository` Protocol로 추상화 → 오프라인 테스트는 fake 주입.

## 3. 파일 구조

```
backend/src/ggotaiorder/scraper/
├─ crawler.py         # poll_once 오케스트레이션 + INTRANET_AUDIO_MARKER(유지)
├─ models.py          # IntranetShop, ScrapedOrder
├─ repository.py      # IntranetRepository(Protocol) + SupabaseIntranetRepository
└─ scraper_client.py  # IntranetScraper(Protocol) + PlaywrightIntranetScraper(골격)
```

### 3.1 models.py
```python
@dataclass
class IntranetShop:
    shop_key: int
    shop_name: str
    url: str
    username: str
    enc_password: str   # AES 암호문(복호화 전)

@dataclass
class ScrapedOrder:
    order_no: str               # 인트라넷 주문번호(중복키)
    raw_text: str               # 원문(stt_text 로 저장)
    fields: OrderExtraction     # pipeline.models.OrderExtraction (11필드) 재사용
```

### 3.2 repository.py
```python
class IntranetRepository(Protocol):
    def list_intranet_shops(self) -> list[IntranetShop]: ...
    def order_exists(self, shop_key: int, order_no: str) -> bool: ...
    def insert_call_history(self, record: dict) -> int: ...
    def insert_order_details(self, payload: dict) -> int: ...
```
`SupabaseIntranetRepository`:
- `list_intranet_shops`: setting_info에서 intranet_url IS NOT NULL인 행 + member_info(shop_name) 조인 → IntranetShop 목록(intranet_id=username, intranet_password=enc_password).
- `order_exists`: server_call_history에서 `shop_key`=, `channel_order`='인터라넷', `channel_classification`=order_no 존재 여부.
- `insert_call_history`/`insert_order_details`: 해당 테이블 insert, 새 id 반환.

### 3.3 scraper_client.py
```python
class IntranetScraper(Protocol):
    def fetch_orders(self, url: str, username: str, password: str) -> list[ScrapedOrder]: ...

class PlaywrightIntranetScraper:
    def fetch_orders(self, url, username, password) -> list[ScrapedOrder]:
        # TODO(라이브): playwright headless 로그인 → 목록 주문번호 추출 → 상세 11필드 스크래핑.
        # 실제 셀렉터는 대상 인트라넷 사이트 확보 후 작성.
        raise NotImplementedError("Playwright 인트라넷 스크래핑은 실 사이트 확보 후 구현")
```
실제 구현은 라이브 영역(단위테스트 안 함). 브라우저 설치(`playwright install chromium`)는 체크리스트.

## 4. crawler.py — poll_once 오케스트레이션

```
poll_once(*, repo=None, scraper=None, notify=None):
  repo = repo or SupabaseIntranetRepository()
  scraper = scraper or PlaywrightIntranetScraper()
  shops = await to_thread(repo.list_intranet_shops)
  for shop in shops:
    password = decrypt(shop.enc_password, config.aes_encryption_key)
    try:
      orders = await to_thread(scraper.fetch_orders, shop.url, shop.username, password)
    except Exception:
      logger.exception(...); _record_failure(shop.shop_key, notify) ; continue
    _reset_failure(shop.shop_key)
    for order in orders:
      if await to_thread(repo.order_exists, shop.shop_key, order.order_no): continue
      call_id = await to_thread(repo.insert_call_history, _call_record(shop, order))
      order_id = await to_thread(repo.insert_order_details, _order_payload(shop, order, call_id))
      await enqueue(order_id)
```

- `_call_record(shop, order)`: `{channel_order:'인터라넷', channel_classification: order.order_no, shop_key, shop_name, customer_phone_number:'', customer_name:'신규', call_date/call_time: now, duration_seconds:0, audio_file_name: INTRANET_AUDIO_MARKER, stt_text: order.raw_text, is_order:'Y'}`.
- `_order_payload(shop, order, call_id)`: order.fields(OrderExtraction) → 11필드 + call_history_id=call_id, shop_key, shop_name, customer_* 보강, quantity or 1, price or 0, rpa_status='ready'.
- 연속 실패 카운터: 모듈 수준 `_failure_counts: dict[int,int]`. `_record_failure`가 +1, **3 도달 시 notify(shop) 호출 후 0 리셋**. `_reset_failure`는 0으로.
- `notify` 기본값: `notifier.send` 래퍼 — `notifier.send(shop_key, channel='인터라넷', count=0, success=False)`. 주입 가능(테스트 spy).
- 비동기: 블로킹(repo·scraper·decrypt는 순수함수라 그대로)은 `asyncio.to_thread` 오프로드. shop별 try/except로 격리.

## 5. 에러 처리

- shop 단위 try/except: 한 shop의 스크래핑/디코딩 실패가 다른 shop·전체 폴링을 막지 않음.
- 스크래핑 실패 누적 3회 → 비상 알림(실패 템플릿). insert/enqueue 실패도 로깅 후 다음 주문으로(주문 단위 보호).

## 6. 테스트 (오프라인 결정적)

`test_scraper.py` — fake repo + fake scraper + spy enqueue/notify:
- 신규 주문 1건 → insert_call_history(channel_classification=order_no, audio=INTRANET_AUDIO_MARKER) + insert_order_details(rpa_status='ready', product_name 매핑) + enqueue(order_id) 호출.
- 중복(order_exists True) → insert/enqueue 미호출.
- scraper 예외 → 카운터 증가; 3회 연속째에 notify 호출(shop_key 전달); 성공 폴링이 끼면 리셋.
- 다중 shop → 각 shop 독립 처리(한 shop 실패가 다른 shop 처리 막지 않음).
- decrypt는 실제 core.crypto 사용(이미 검증됨) — fake shop의 enc_password는 테스트에서 encrypt로 생성하거나, scraper가 password를 받는지만 확인.
- 기존 63 회귀. 비동기 테스트는 `asyncio_mode="auto"`.

`SupabaseIntranetRepository`·`PlaywrightIntranetScraper`는 통합/라이브 영역(import 확인만, 단위테스트 안 함).

## 7. 라이브 구동 체크리스트

1. 대상 인트라넷 사이트 URL·계정·로그인/목록/상세 페이지 HTML 구조 확보.
2. `PlaywrightIntranetScraper.fetch_orders` 셀렉터 구현(로그인→목록 주문번호→상세 11필드).
3. `playwright install chromium`(브라우저 바이너리).
4. setting_info에 intranet_url/id/password(프론트가 AES 암호화 저장) 설정.
5. poll_once 실행 → 신규 주문 수집·중복 skip·order_details 생성 확인. 3회 실패 시 알림 확인.

## 8. 비범위(후속)

- 실 Playwright 셀렉터·세션 유지, 전용 비상 알림 문구, rpa 실구현, 알림 이력 테이블.
