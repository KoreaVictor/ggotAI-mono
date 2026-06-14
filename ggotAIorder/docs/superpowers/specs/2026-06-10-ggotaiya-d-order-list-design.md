# ggotAIya 모듈 D(주문조회) 설계서

- 날짜: 2026-06-10
- 범위: 안티그래비티 `frontend/src/views/order_list.tsx`(주문조회 화면, PRD 화면8/F10) 정교화
- 패턴: 모듈 C(대시보드)에서 검증된 **샵범위 RPC + remember_token 인증 + anon 직접권한 하드닝** 재사용
- 선행 완료: A(기반·셸·암호화), B1(인증·자동로그인), B2a(폰 OTP), B2b(마이페이지), C(대시보드)

---

## 1. 목적과 범위

로그인한 꽃집이 자기 샵의 주문 내역을 **채널/기간/상태로 필터 조회**하고, RPA 입력에 실패한 주문을 **재전송(재큐)**할 수 있게 한다. 동시에 현재 `order_list.tsx`가 사용하는 `order_details` **anon 직접 SELECT/UPDATE 권한을 회수(하드닝)**하여 C/B2b와 동일한 보안 수준으로 끌어올린다.

### 범위에 포함
- 채널 세그먼트 필터(전체/핸드폰/가게전화/쇼핑몰/인터라넷/가게음성) + 기간 필터 + 상태 필터 → **서버 필터**(RPC 인자)
- 고객명/상품/배송지 등 텍스트 검색 → **클라이언트 필터**(불러온 페이지 내 narrowing)
- 메인 그리드(주문자/상품/가격/배달일시/배달장소/채널/입력상태 뱃지)
- 읽기전용 상세 모달(리본·카드메시지·수령자 등 전체 필드 표시)
- RPA 실패 주문 재전송(`requeue_order` RPC)
- 하단 요약바(총 건수 + 총 금액 합계)

### 범위에서 제외 (사용자 결정)
- **주문 상세 수동 편집·저장**(order_details 직접 수정) — 별도 모듈 이월. 따라서 상세 모달은 읽기전용으로 축소하고 order_details에 UPDATE 권한이 불필요해진다.
- 페이징(무한스크롤/페이지네이션) — 기본 기간 '오늘'은 충분히 작음. 안전 LIMIT 500으로 가드하고 후속 과제로 이월.

---

## 2. 아키텍처

백엔드(Python Windows 서비스, service_role) **무변경** — 수집/RPA 경로는 service_role 키로 동작하므로 anon 권한 회수에 영향받지 않는다. 신규는 DB RPC 2개 + 하드닝 1건, 프론트 1개 신규 모듈 + 1개 뷰 재작성.

| 구성 | 역할 |
|---|---|
| `get_orders(...)` RPC | SECURITY DEFINER. remember_token_hash 인증 → 채널/기간/상태 서버필터 + `server_call_history` 조인으로 `channel_order` 취득 → 풀 order_details 행 배열 반환 |
| `requeue_order(...)` RPC | SECURITY DEFINER. 인증 → 샵스코핑 `rpa_status='ready'` 재큐 |
| 하드닝 | `revoke all on order_details from anon, authenticated, public`. anon은 두 RPC만 EXECUTE |
| `orders/client.ts` (+test) | `getOrders`/`requeueOrder` 순수 래퍼(주입형 `DashRpc`) |
| `views/order_list.tsx` (재작성) | shop_key 하드코딩 제거 → `session.shopKey`+`readToken`. 필터바·요약바 추가, 모달 읽기전용화 |

---

## 3. 데이터 계약

### 3.1 채널 매핑 (코드 확인됨)

`server_call_history.channel_order`에 기록되는 실제 값:
- `가게전화` (api/service.py)
- `핸드폰` (realtime — 핸드폰1·2 **공유**, 라인 미구분: C와 동일 한계)
- `가게음성` (realtime)
- `인터라넷` (scraper/models.py `INTRANET_CHANNEL`)
- `쇼핑몰` (쇼핑몰 수집)
- (그 외 `기타` 폴백)

PRD 채널 세그먼트와 1:1 대응. 핸드폰1/2 라인 구분은 `channel_order`가 표현하지 못하므로 세그먼트 '핸드폰'은 두 라인을 합산 표시한다(후속: 수신라인 필드 도입 시 분리).

### 3.2 `get_orders` RPC

```
get_orders(
  p_shop_key int,
  p_token    text,
  p_channel  text default null,   -- null=전체, else server_call_history.channel_order 일치
  p_status   text default null,   -- null=전체, else order_details.rpa_status 일치 ('ready'|'success'|'fail')
  p_start    timestamptz,         -- 조회 시작(포함)
  p_end      timestamptz          -- 조회 종료(미포함)
) returns json
```

- **인증**: get_dashboard와 동일 — member_info 조회 후 `remember_token_hash`/만료/`crypt(p_token, hash)` 검사. 실패 시 `{"ok": false, "reason": "unauthorized"}`.
- **쿼리**:
  ```
  order_details od
  join server_call_history sch on sch.id = od.call_history_id
  where od.shop_key = p_shop_key
    and od.created_at >= p_start and od.created_at < p_end
    and (p_channel is null or sch.channel_order = p_channel)
    and (p_status  is null or od.rpa_status     = p_status)
  order by od.created_at desc
  limit 500
  ```
- **반환**: `{"ok": true, "rows": [ {order_details 표시필드 + channel_order} ... ]}`
  - 행 필드: `id, call_history_id, customer_name, customer_phone_number, product_name, quantity, price, delivery_at, delivery_place, receiver_name, receiver_phone_number, ribbon_sender, ribbon_congratulations, card_message, rpa_status, created_at, channel_order`
- **기간 시맨틱**: 그리드의 '주문일자/주문시간'은 `order_details.created_at`(주문 수집 시각) 기준. 기본값은 **오늘(KST 경계)** — `((now() at time zone 'Asia/Seoul')::date)` 시작, 내일 0시 KST 미만. 프론트가 p_start/p_end를 계산해 전달(C의 v_today 경계 로직과 정합).

### 3.3 `requeue_order` RPC

```
requeue_order(p_shop_key int, p_token text, p_order_id bigint) returns json
```

- **인증**: 동일.
- **동작**: `update order_details set rpa_status = 'ready' where id = p_order_id and shop_key = p_shop_key`.
  - 영향 행 1 → `{"ok": true, "rpa_status": "ready"}`
  - 영향 행 0(미존재 또는 타 샵) → `{"ok": false, "reason": "not_found"}`
- 샵스코핑(`shop_key` 일치 조건)으로 교차샵 재큐 차단. UI는 기존대로 `rpa_status='fail'` 행에만 재전송 버튼을 노출(RPC 자체는 상태 무관 재큐 허용 — 단순성).

### 3.4 하드닝

```
revoke all privileges on table order_details from anon, authenticated, public;
grant execute on function get_orders(int, text, text, text, timestamptz, timestamptz) to anon;
grant execute on function requeue_order(int, text, bigint) to anon;
```

- 검증: `column_privileges`에서 anon/authenticated의 order_details count=0 (테이블 레벨 revoke가 컬럼 grant까지 정리됨 — B2b에서 실측 확인된 계약).
- 백엔드 service_role는 영향 없음. 프론트에서 order_details 직접 접근 화면은 `order_list.tsx` 단 하나(grep 확인)이므로 회귀 위험 없음.
- 신규 함수에 ALTER DEFAULT PRIVILEGES로 anon/authenticated EXECUTE가 자동 부여될 수 있으므로(B2a 전례), get_orders/requeue_order는 `revoke ... from public` 후 `grant ... to anon` 명시.

---

## 4. 프론트엔드 변경

### 4.1 `orders/client.ts` (+ `orders/client.test.ts`)
C의 `dashboard/client.ts` 형태. 주입형 `DashRpc` 타입 재사용(또는 공유 타입 import). `OrderRow` 인터페이스(3.2 반환 행) 정의.
- `getOrders(rpc, shopKey, token, {channel, status, start, end}) -> {ok, rows?, reason?}`
- `requeueOrder(rpc, shopKey, token, orderId) -> {ok, rpa_status?, reason?}`
- 테스트: ok 경로, unauthorized 경로, error 경로, 인자 전달 매핑.

### 4.2 `views/order_list.tsx` 재작성
- `import { supabase }` 직접 쿼리 → `getOrders`/`requeueOrder` 래퍼 + `useSession()`의 `shopKey`/`readToken` 사용. `defaultShopKey = 1` 제거.
- **필터바**: 채널 세그먼트(전체+5채널) + 기간(기본 오늘 KST, 시작/종료 입력) + [조회] 버튼. 채널/기간/상태 변경 후 [조회] 시 `getOrders` 재호출. (상태탭 유지)
- **텍스트 검색**: 기존 클라이언트 `filteredOrders` 로직 유지(불러온 rows에 대해).
- **모달 읽기전용화**: `isEditing`/`editedOrder`/`handleSaveChanges`/`handleModalInputChange` 및 편집 폼 전부 제거. 상세 뷰어 + (fail 시) 재전송 버튼만 유지.
- **재전송**: `handleTriggerRPA` → `requeueOrder` 래퍼 호출, 성공 시 로컬 행 상태 `ready` 반영 + 재조회.
- **하단 요약바**: `filteredOrders`(검색 적용 후 표시중 행) 기준 **클라이언트 파생** — 총 건수 = length, 총 금액 = price 합계. 화면 그리드와 항상 일치(LIMIT 500 내).
- 미사용 import(`Phone` 등) 정리.

---

## 5. 검증 계획

1. **마이그레이션 SQL** `docs/migrations/2026-06-10-d-order-list.sql` 작성 → Management API(curl UA, PAT) 적용.
2. **라운드트립 스모크**: 토큰행 시드 → `get_orders`(채널/기간/상태 조합) 결과 검증 → `requeue_order` 후 rpa_status='ready' 확인 → 권한 검증(`column_privileges` count=0) → 스모크 데이터 정리.
3. **프론트**: vitest(orders/client) + `npm run build`.
4. **UI E2E(Playwright Node판)**: 로그인 → 주문조회 진입(오늘 자동조회) → 채널/기간 필터 [조회] → 재전송(fail→ready) → 요약바 합계 확인.

---

## 6. 알려진 한계 / 이월

- **핸드폰1·2 합산**: `channel_order`가 라인 미구분 → 세그먼트 '핸드폰'은 두 라인 합산(C와 동일, 백엔드 수신라인 필드 후속).
- **수동 편집 제외**: 상세 수정 기능은 본 모듈에서 제외 — 필요 시 별도 모듈(update_order RPC + 검증).
- **페이징 없음**: LIMIT 500 가드. 넓은 기간 조회 시 잘릴 수 있음 — 페이지네이션 후속.
- **요약바는 표시중 행 기준**: LIMIT 500 초과 데이터는 요약에 미반영(화면-요약 일치 우선).
- **setting_info(E) anon 하드닝**: 모듈 E로 이월.

---

## 7. 재사용 자산

- `session.shopKey`/`readToken`(C에서 배선, in-memory)
- get_dashboard 인증 블록(remember_token_hash + crypt) → get_orders/requeue_order에 복제
- `dashboard/client.ts`의 `DashRpc` 주입 패턴
- Management API + curl UA 적용 패턴(PAT 채팅 제공), `column_privileges` count=0 권한검증
- Playwright **Node판**(Python판 불가 — greenlet/MSVC DLL)
