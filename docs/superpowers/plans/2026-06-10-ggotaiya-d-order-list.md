# ggotAIya D 주문조회 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 안티그래비티 order_list.tsx의 `shop_key=1` 하드코딩·`order_details` 직접 SELECT/UPDATE를, 샵 범위 `get_orders`/`requeue_order` SECURITY DEFINER RPC + 채널/기간/상태 서버필터 + 하단 요약바로 교체하고 `order_details`를 하드닝한다. 수동 편집 기능은 제외(읽기전용 상세).

**Architecture:** `get_orders(shop_key, token, channel, status, start, end)` RPC가 order_details를 server_call_history와 조인해 채널을 취득, 샵 범위로 서버측 조회(LIMIT 500). `requeue_order(shop_key, token, order_id)`가 rpa_status='ready' 재큐. 토큰은 기존 remember_token 재사용(C에서 배선된 인메모리 readToken). 프론트는 데이터=RPC 래퍼, 텍스트검색·요약바는 클라이언트 파생.

**Tech Stack:** Postgres(pgcrypto) RPC, React+Vite+TypeScript, Vitest, Electron(기존 유지). 라이브 적용=Management API(curl UA, PAT).

**설계서:** `docs/superpowers/specs/2026-06-10-ggotaiya-d-order-list-design.md`
**브랜치:** `feature/ggotaiya-d-order-list` (master `5abe64c`에서 분기 — 아래 "브랜치 준비"에서 생성)

## 파일 구조
- Create: `docs/migrations/2026-06-10-d-order-list.sql` — get_orders + requeue_order + order_details 하드닝
- Create: `frontend/src/orders/client.ts` + `client.test.ts` — RPC 래퍼·타입(`DashRpc`는 dashboard/client에서 재사용)
- Modify(재작성): `frontend/src/views/order_list.tsx` — 필터바·요약바·읽기전용 모달, RPC 사용

## 사전 사실 (확인됨)
- `readToken`/`session.shopKey`는 **이미 SessionContext에 배선됨**(C에서 완료, `useSession()`으로 사용). 세션 배선 Task 불필요.
- 프론트에서 `order_details` 직접 접근 화면은 `order_list.tsx` **단 하나**(grep 확인) → 하드닝 회귀 위험 없음.
- `server_call_history.channel_order` 실제 값: `가게전화`/`핸드폰`/`가게음성`/`인터라넷`/`쇼핑몰`(+`기타`). 핸드폰1·2는 `핸드폰` 공유.
- `order_details` NOT NULL: call_history_id·shop_key·shop_name·customer_phone_number·product_name·delivery_at·delivery_place·receiver_name·receiver_phone_number. customer_name·quantity·price·ribbon_*·card_message 등은 nullable 가능.

---

## 브랜치 준비 (컨트롤러, Task 1 이전 1회)

Run:
```bash
git checkout master && git pull --ff-only
git checkout -b feature/ggotaiya-d-order-list
```
Expected: `feature/ggotaiya-d-order-list` 브랜치로 전환(master `5abe64c` 이상).

---

## Task 1: DB 마이그레이션 (get_orders + requeue_order + order_details 하드닝) — 라이브, 컨트롤러 직접

> SQL을 파일로 기록하고 Management API로 적용 후 스모크/권한 검증. **라이브 DB 변경이라 컨트롤러가 직접(서브에이전트 위임 금지).** MCP Unauthorized 시 `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query` + `Authorization: Bearer <PAT>` + **User-Agent: curl**.

**Files:** Create: `docs/migrations/2026-06-10-d-order-list.sql`

- [ ] **Step 1: 마이그레이션 SQL 파일 작성**

`docs/migrations/2026-06-10-d-order-list.sql`:
```sql
-- ggotAIya D: 주문조회 — get_orders / requeue_order 샵범위 RPC + order_details 하드닝
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

-- 1) 주문 목록 조회 (채널/기간/상태 서버필터, server_call_history 조인으로 채널 취득)
create or replace function get_orders(
  p_shop_key int,
  p_token    text,
  p_channel  text default null,        -- null=전체, else server_call_history.channel_order 일치
  p_status   text default null,        -- null=전체, else order_details.rpa_status 일치
  p_start    timestamptz default null, -- 조회 시작(포함)
  p_end      timestamptz default null  -- 조회 종료(미포함)
) returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_rows json;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  select coalesce(json_agg(r order by r.created_at desc), '[]'::json) into v_rows
  from (
    select od.id, od.call_history_id, od.customer_name, od.customer_phone_number,
           od.product_name, od.quantity, od.price, od.delivery_at, od.delivery_place,
           od.receiver_name, od.receiver_phone_number, od.ribbon_sender,
           od.ribbon_congratulations, od.card_message, od.rpa_status, od.created_at,
           sch.channel_order
    from order_details od
    left join server_call_history sch on sch.id = od.call_history_id
    where od.shop_key = p_shop_key
      and (p_start   is null or od.created_at >= p_start)
      and (p_end     is null or od.created_at <  p_end)
      and (p_channel is null or sch.channel_order = p_channel)
      and (p_status  is null or od.rpa_status     = p_status)
    order by od.created_at desc
    limit 500
  ) r;

  return json_build_object('ok', true, 'rows', v_rows);
end;
$$;

-- 2) RPA 재큐 (샵스코핑으로 교차샵 차단)
create or replace function requeue_order(p_shop_key int, p_token text, p_order_id bigint)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_count int;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  update order_details set rpa_status = 'ready'
   where id = p_order_id and shop_key = p_shop_key;
  get diagnostics v_count = row_count;
  if v_count = 0 then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  return json_build_object('ok', true, 'rpa_status', 'ready');
end;
$$;

grant execute on function get_orders(int, text, text, text, timestamptz, timestamptz) to anon;
grant execute on function requeue_order(int, text, bigint) to anon;

-- 하드닝: order_details anon/authenticated 직접권한 회수(조회/재큐는 owner 실행 RPC로만)
revoke all privileges on table order_details from anon, authenticated, public;
```

- [ ] **Step 2: 적용 전 확인 (컨트롤러)**

Run: 다른 프론트 코드가 `order_details`를 직접 읽는지 재확인(order_list 만이어야 함).
```bash
git grep -n "order_details" frontend/src
```
Expected: `views/order_list.tsx` 에서만 등장(곧 재작성됨). dashboard/mypage/settings 등 다른 화면은 미등장.

- [ ] **Step 3: 마이그레이션 적용 (컨트롤러 직접)**

Run: 위 SQL 전체를 Management API `database/query` 로 실행.
Expected: `[]` (에러 없음).

- [ ] **Step 4: 라운드트립 스모크 (컨트롤러 직접)**

Run: 아래 DO 블록(시드→검증→정리). 성공 시 `[]`, 실패 시 예외.

> NOT NULL 제약: `server_call_history`는 channel_order·channel_classification·shop_key·shop_name·call_date·call_time 필수. `order_details`는 call_history_id·shop_key·shop_name·customer_phone_number·product_name·delivery_at·delivery_place·receiver_name·receiver_phone_number 필수. 시드에 모두 채운다.
```sql
do $$
declare
  v_id bigint; v_ch_hp bigint; v_ch_mall bigint;
  v_o_fail bigint; r json;
  v_d date := (now() at time zone 'Asia/Seoul')::date;
  v_t time := (now() at time zone 'Asia/Seoul')::time;
  v_start timestamptz := (v_d::timestamp at time zone 'Asia/Seoul');
  v_end   timestamptz := ((v_d + 1)::timestamp at time zone 'Asia/Seoul');
begin
  insert into member_info(username,password,shop_name,representative_name,mobile_number,is_approved,
                          remember_token_hash,remember_token_expires_at)
  values('dordsmoke', crypt('pw',gen_salt('bf')), 'D스모크','대표','01077770004','Y',
         crypt('DTOKEN',gen_salt('bf')), now()+interval '1 day') returning id into v_id;

  insert into server_call_history(channel_order,channel_classification,shop_key,shop_name,customer_name,call_date,call_time)
  values('핸드폰','d1',v_id,'D스모크','김A',v_d,v_t) returning id into v_ch_hp;
  insert into server_call_history(channel_order,channel_classification,shop_key,shop_name,customer_name,call_date,call_time)
  values('쇼핑몰','d2',v_id,'D스모크','김B',v_d,v_t) returning id into v_ch_mall;

  -- 핸드폰 / fail / 50000
  insert into order_details(call_history_id,shop_key,shop_name,customer_name,customer_phone_number,product_name,
                            quantity,price,delivery_at,delivery_place,receiver_name,receiver_phone_number,rpa_status)
  values(v_ch_hp,v_id,'D스모크','김A','01000000001','장미',1,50000, now(),'서울','받는이A','01000000011','fail')
  returning id into v_o_fail;
  -- 쇼핑몰 / success / 30000
  insert into order_details(call_history_id,shop_key,shop_name,customer_name,customer_phone_number,product_name,
                            quantity,price,delivery_at,delivery_place,receiver_name,receiver_phone_number,rpa_status)
  values(v_ch_mall,v_id,'D스모크','김B','01000000002','국화',2,30000, now(),'부산','받는이B','01000000012','success');

  -- ① 전체 조회(오늘) = 2건
  r := get_orders(v_id::int, 'DTOKEN', null, null, v_start, v_end);
  if (r->>'ok')::boolean is not true then raise exception 'GO ok: %', r; end if;
  if json_array_length(r->'rows') <> 2 then raise exception 'GO total: %', r; end if;

  -- ② 채널=핸드폰 = 1건, channel_order 노출
  r := get_orders(v_id::int, 'DTOKEN', '핸드폰', null, v_start, v_end);
  if json_array_length(r->'rows') <> 1 then raise exception 'GO hp len: %', r; end if;
  if (r#>>'{rows,0,channel_order}') <> '핸드폰' then raise exception 'GO hp ch: %', r; end if;
  if (r#>>'{rows,0,price}')::int <> 50000 then raise exception 'GO hp price: %', r; end if;

  -- ③ 상태=success = 1건
  r := get_orders(v_id::int, 'DTOKEN', null, 'success', v_start, v_end);
  if json_array_length(r->'rows') <> 1 then raise exception 'GO success len: %', r; end if;

  -- ④ 네거티브: 틀린 토큰
  r := get_orders(v_id::int, 'WRONG', null, null, v_start, v_end);
  if (r->>'reason') <> 'unauthorized' then raise exception 'GO wrongtoken: %', r; end if;

  -- ⑤ requeue: fail → ready
  r := requeue_order(v_id::int, 'DTOKEN', v_o_fail);
  if (r->>'ok')::boolean is not true or (r->>'rpa_status') <> 'ready' then raise exception 'RQ ok: %', r; end if;
  if (select rpa_status from order_details where id = v_o_fail) <> 'ready' then raise exception 'RQ apply'; end if;

  -- ⑥ requeue 네거티브: 없는 주문
  r := requeue_order(v_id::int, 'DTOKEN', 99999999);
  if (r->>'reason') <> 'not_found' then raise exception 'RQ notfound: %', r; end if;

  -- ⑦ requeue 네거티브: 틀린 토큰
  r := requeue_order(v_id::int, 'WRONG', v_o_fail);
  if (r->>'reason') <> 'unauthorized' then raise exception 'RQ wrongtoken: %', r; end if;

  -- 정리(필수)
  delete from order_details where shop_key=v_id;
  delete from server_call_history where shop_key=v_id;
  delete from member_info where id=v_id;
  raise notice 'D SMOKE ALL PASSED';
end $$;
```
Expected: `[]`.

- [ ] **Step 5: 권한 검증 (컨트롤러 직접)**
```sql
select has_table_privilege('anon','order_details','select') as sel,   -- false
       has_table_privilege('anon','order_details','update') as upd,   -- false
       has_table_privilege('anon','order_details','insert') as ins,   -- false
       (select count(*) from information_schema.column_privileges
          where table_name='order_details' and grantee in ('anon','authenticated')) as anon_cols,  -- 0
       has_function_privilege('anon','get_orders(integer,text,text,text,timestamp with time zone,timestamp with time zone)','execute') as go,  -- true
       has_function_privilege('anon','requeue_order(integer,text,bigint)','execute') as rq;  -- true
```
Expected: `sel=false, upd=false, ins=false, anon_cols=0, go=true, rq=true`.

- [ ] **Step 6: 커밋**
```bash
git add docs/migrations/2026-06-10-d-order-list.sql
git commit -m "feat(db): D 주문조회 get_orders/requeue_order RPC + order_details 하드닝"
```

---

## Task 2: orders/client.ts (RPC 래퍼·타입) — TDD, 서브에이전트

**Files:**
- Create: `frontend/src/orders/client.ts`, `frontend/src/orders/client.test.ts`

- [ ] **Step 1: 실패 테스트 작성** — `frontend/src/orders/client.test.ts`
```ts
import { describe, it, expect } from 'vitest';
import { getOrders, requeueOrder } from './client';
import type { DashRpc } from '../dashboard/client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const FILTERS = { channel: null, status: null, start: '2026-06-10T00:00:00+09:00', end: '2026-06-11T00:00:00+09:00' };
const ROW = {
  id: 1, call_history_id: 10, customer_name: '홍', customer_phone_number: '010', product_name: '장미',
  quantity: 1, price: 50000, delivery_at: '2026-06-10T10:00:00Z', delivery_place: '서울', receiver_name: '받는이',
  receiver_phone_number: '010', ribbon_sender: null, ribbon_congratulations: null, card_message: null,
  rpa_status: 'fail', created_at: '2026-06-10T00:00:00Z', channel_order: '핸드폰',
};

describe('getOrders', () => {
  it('성공이면 rows 반환', async () => {
    const r = await getOrders(fakeRpc({ ok: true, rows: [ROW] }), 7, 'tk', FILTERS);
    expect(r.ok).toBe(true);
    expect(r.rows?.[0].channel_order).toBe('핸드폰');
    expect(r.rows?.[0].price).toBe(50000);
  });
  it('rows 없으면 빈 배열', async () => {
    const r = await getOrders(fakeRpc({ ok: true }), 7, 'tk', FILTERS);
    expect(r).toEqual({ ok: true, rows: [] });
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getOrders(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad', FILTERS);
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getOrders(fakeRpc(null, { message: 'boom' }), 7, 'tk', FILTERS);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
  it('필터 인자를 RPC 인자로 매핑', async () => {
    let captured: Record<string, unknown> = {};
    const rpc: DashRpc = (async (_fn: string, args: Record<string, unknown>) => {
      captured = args; return { data: { ok: true, rows: [] }, error: null };
    }) as DashRpc;
    await getOrders(rpc, 7, 'tk', { channel: '핸드폰', status: 'fail', start: 's', end: 'e' });
    expect(captured).toEqual({ p_shop_key: 7, p_token: 'tk', p_channel: '핸드폰', p_status: 'fail', p_start: 's', p_end: 'e' });
  });
});

describe('requeueOrder', () => {
  it('성공이면 rpa_status 반환', async () => {
    const r = await requeueOrder(fakeRpc({ ok: true, rpa_status: 'ready' }), 7, 'tk', 1);
    expect(r).toEqual({ ok: true, rpa_status: 'ready' });
  });
  it('not_found 면 reason 전달', async () => {
    const r = await requeueOrder(fakeRpc({ ok: false, reason: 'not_found' }), 7, 'tk', 999);
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
  it('RPC 에러면 error', async () => {
    const r = await requeueOrder(fakeRpc(null, { message: 'boom' }), 7, 'tk', 1);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm run test -- --run orders/`
Expected: FAIL (모듈 없음).

- [ ] **Step 3: client.ts 구현** — `frontend/src/orders/client.ts`
```ts
import type { DashRpc } from '../dashboard/client';

export interface OrderRow {
  id: number;
  call_history_id: number;
  customer_name: string | null;
  customer_phone_number: string;
  product_name: string;
  quantity: number | null;
  price: number | null;
  delivery_at: string;
  delivery_place: string;
  receiver_name: string;
  receiver_phone_number: string;
  ribbon_sender: string | null;
  ribbon_congratulations: string | null;
  card_message: string | null;
  rpa_status: 'ready' | 'success' | 'fail';
  created_at: string;
  channel_order: string | null;
}

export interface OrderFilters {
  channel?: string | null;  // null=전체
  status?: string | null;   // null=전체
  start: string;            // ISO(오프셋 포함)
  end: string;              // ISO(오프셋 포함, 미포함 경계)
}

export async function getOrders(
  rpc: DashRpc, shopKey: number, token: string, f: OrderFilters,
): Promise<{ ok: boolean; rows?: OrderRow[]; reason?: string }> {
  const { data, error } = await rpc('get_orders', {
    p_shop_key: shopKey, p_token: token,
    p_channel: f.channel ?? null, p_status: f.status ?? null,
    p_start: f.start, p_end: f.end,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; rows?: OrderRow[]; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, rows: d.rows ?? [] };
}

export async function requeueOrder(
  rpc: DashRpc, shopKey: number, token: string, orderId: number,
): Promise<{ ok: boolean; rpa_status?: string; reason?: string }> {
  const { data, error } = await rpc('requeue_order', {
    p_shop_key: shopKey, p_token: token, p_order_id: orderId,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; rpa_status?: string; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, rpa_status: d.rpa_status };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm run test -- --run orders/`
Expected: PASS (전부).

- [ ] **Step 5: 커밋**
```bash
git add frontend/src/orders/
git commit -m "feat(frontend): orders RPC 래퍼(getOrders/requeueOrder) +test"
```

---

## Task 3: order_list.tsx 재작성 (필터바·요약바·읽기전용 모달, RPC 사용) — 서브에이전트

**Files:** Modify(전면 교체): `frontend/src/views/order_list.tsx`

- [ ] **Step 1: order_list.tsx 전면 교체**

`frontend/src/views/order_list.tsx` 전체를 아래로 교체:
```tsx
import { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getOrders, requeueOrder, type OrderRow } from '../orders/client';
import type { DashRpc } from '../dashboard/client';
import {
  Search, Eye, Play, CheckCircle2, XCircle, AlertCircle,
  MapPin, Calendar, User, ShoppingBag, X, RefreshCw,
} from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

// 채널 세그먼트(전체 + 5채널). value=null 이면 전체. 핸드폰1·2는 '핸드폰' 공유.
const CHANNEL_SEGMENTS: { label: string; value: string | null }[] = [
  { label: '전체', value: null },
  { label: '핸드폰', value: '핸드폰' },
  { label: '가게전화', value: '가게전화' },
  { label: '쇼핑몰', value: '쇼핑몰' },
  { label: '인터라넷', value: '인터라넷' },
  { label: '가게음성', value: '가게음성' },
];

// 오늘(KST) 'YYYY-MM-DD'
function todayKst(): string {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}
// 'YYYY-MM-DD' → 해당일 00:00 KST(포함 경계)
function kstStartIso(dateStr: string): string {
  return `${dateStr}T00:00:00+09:00`;
}
// 'YYYY-MM-DD' → 다음날 00:00 KST(미포함 경계)
function kstEndIsoExclusive(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + 1));
  const ny = next.getUTCFullYear();
  const nm = String(next.getUTCMonth() + 1).padStart(2, '0');
  const nd = String(next.getUTCDate()).padStart(2, '0');
  return `${ny}-${nm}-${nd}T00:00:00+09:00`;
}

export function OrderListView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  // 필터(서버): 채널 / 상태 / 기간
  const [channel, setChannel] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [startDate, setStartDate] = useState<string>(todayKst());
  const [endDate, setEndDate] = useState<string>(todayKst());

  // 검색(클라이언트)
  const [searchQuery, setSearchQuery] = useState('');

  // 읽기전용 상세 모달
  const [selectedOrder, setSelectedOrder] = useState<OrderRow | null>(null);
  const [modalSuccess, setModalSuccess] = useState('');
  const [modalError, setModalError] = useState('');

  const loadOrders = async () => {
    if (!shopKey || !readToken) { setLoadError('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
    setLoading(true);
    const r = await getOrders(rpc, shopKey, readToken, {
      channel,
      status: statusFilter === 'all' ? null : statusFilter,
      start: kstStartIso(startDate),
      end: kstEndIsoExclusive(endDate),
    });
    if (!r.ok || !r.rows) {
      setLoadError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '주문 내역을 불러오지 못했습니다.');
      setLoading(false);
      return;
    }
    setLoadError('');
    setOrders(r.rows);
    setLoading(false);
  };

  // 진입 시 + 채널/상태 변경 시 자동 조회(기간은 [조회] 버튼으로 명시 조회)
  useEffect(() => {
    loadOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shopKey, readToken, channel, statusFilter]);

  // 텍스트 검색(불러온 행 narrowing)
  const filteredOrders = orders.filter((order) => {
    const q = searchQuery.toLowerCase();
    if (!q) return true;
    return (
      (order.customer_name ?? '').toLowerCase().includes(q) ||
      order.product_name.toLowerCase().includes(q) ||
      order.delivery_place.toLowerCase().includes(q) ||
      order.customer_phone_number.includes(q) ||
      order.receiver_name.toLowerCase().includes(q)
    );
  });

  // 요약바: 화면 표시중(검색 적용 후) 행 기준 클라이언트 파생
  const totalCount = filteredOrders.length;
  const totalAmount = filteredOrders.reduce((sum, o) => sum + (o.price ?? 0), 0);

  const handleViewDetail = (order: OrderRow) => {
    setSelectedOrder(order);
    setModalSuccess('');
    setModalError('');
  };

  const handleRequeue = async (orderId: number) => {
    setModalSuccess('');
    setModalError('');
    const r = await requeueOrder(rpc, shopKey, readToken ?? '', orderId);
    if (!r.ok) {
      setModalError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.'
        : r.reason === 'not_found' ? '해당 주문을 찾을 수 없습니다.' : 'RPA 재전송 중 오류가 발생했습니다.');
      return;
    }
    setModalSuccess('RPA 대기열에 주문을 전송했습니다. 백엔드가 곧 입력을 시작합니다.');
    setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, rpa_status: 'ready' } : o)));
    if (selectedOrder && selectedOrder.id === orderId) {
      setSelectedOrder((prev) => (prev ? { ...prev, rpa_status: 'ready' } : prev));
    }
  };

  const renderStatusBadge = (status: 'ready' | 'success' | 'fail') => {
    switch (status) {
      case 'success':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-success/15 text-brand-success border border-brand-success/30">
            <CheckCircle2 className="h-3 w-3" />성공
          </span>
        );
      case 'fail':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-error/15 text-brand-error border border-brand-error/30">
            <XCircle className="h-3 w-3" />실패
          </span>
        );
      case 'ready':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-warning/15 text-brand-warning border border-brand-warning/30 animate-pulse">
            <Play className="h-3 w-3" />대기중
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 animate-fade-in-up">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">주문 내역 조회</h1>
          <p className="text-brand-text-secondary text-sm mt-1">채널·기간·상태로 조회하고, 입력 실패 주문을 RPA로 재전송할 수 있습니다.</p>
        </div>
      </div>

      {/* 필터바: 채널 세그먼트 + 기간 + 조회 + 검색 */}
      <div className="glass-panel rounded-xl border border-brand-border p-4 mb-6 space-y-4">
        {/* 채널 세그먼트 */}
        <div className="flex flex-wrap gap-1.5">
          {CHANNEL_SEGMENTS.map((seg) => (
            <button
              key={seg.label}
              onClick={() => setChannel(seg.value)}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-md transition ${channel === seg.value ? 'bg-brand-primary text-white shadow' : 'bg-brand-card text-brand-text-secondary hover:text-brand-text-primary border border-brand-border'}`}
            >
              {seg.label}
            </button>
          ))}
        </div>

        {/* 기간 + 조회 + 상태 + 검색 */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-brand-text-muted" />
            <input type="date" value={startDate} max={endDate} onChange={(e) => setStartDate(e.target.value)}
              className="bg-brand-card border border-brand-border rounded-lg px-3 py-2 text-sm text-brand-text-primary outline-none focus:border-brand-primary" />
            <span className="text-brand-text-muted text-sm">~</span>
            <input type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)}
              className="bg-brand-card border border-brand-border rounded-lg px-3 py-2 text-sm text-brand-text-primary outline-none focus:border-brand-primary" />
            <button onClick={loadOrders}
              className="flex items-center gap-1.5 px-4 py-2 bg-brand-primary hover:bg-brand-primary-hover text-white text-xs font-semibold rounded-lg transition">
              <Search className="h-3.5 w-3.5" />조회
            </button>
          </div>

          {/* 상태 탭 */}
          <div className="flex bg-brand-card p-1 border border-brand-border rounded-lg lg:ml-2">
            {([['all', '전체'], ['ready', '대기'], ['success', '성공'], ['fail', '실패']] as const).map(([val, label]) => (
              <button key={val} onClick={() => setStatusFilter(val)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === val ? 'bg-brand-primary text-white shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}>
                {label}
              </button>
            ))}
          </div>

          {/* 검색(클라이언트) */}
          <div className="relative w-full lg:w-64 lg:ml-auto">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-brand-text-muted" />
            <input type="text" placeholder="고객명·상품·배송지 검색..." value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-brand-card border border-brand-border focus:border-brand-primary rounded-lg pl-10 pr-4 py-2 text-sm text-brand-text-primary outline-none transition" />
          </div>
        </div>
      </div>

      {loadError && <div className="mb-6 text-sm text-brand-error bg-brand-error/10 border border-brand-error/20 rounded-xl px-4 py-3">{loadError}</div>}

      {/* 주문 그리드 */}
      <div className="glass-panel rounded-xl shadow-xl overflow-hidden">
        {loading ? (
          <div className="flex justify-center items-center py-24">
            <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-brand-primary"></div>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="text-center py-24 text-brand-text-muted space-y-2">
            <AlertCircle className="h-10 w-10 mx-auto text-brand-text-muted" />
            <p className="text-sm">조건에 부합하는 주문 내역이 없습니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-brand-border/80 bg-brand-card/50 text-[11px] font-semibold text-brand-text-secondary uppercase tracking-wider">
                  <th className="px-5 py-4">주문일시</th>
                  <th className="px-5 py-4">주문자</th>
                  <th className="px-5 py-4">상품 / 수량</th>
                  <th className="px-5 py-4 text-right">가격</th>
                  <th className="px-5 py-4">배달 장소</th>
                  <th className="px-5 py-4 text-center">채널</th>
                  <th className="px-5 py-4 text-center">입력상태</th>
                  <th className="px-5 py-4 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40 text-sm text-brand-text-primary">
                {filteredOrders.map((order) => (
                  <tr key={order.id} className="hover:bg-brand-card-hover/40 transition group cursor-pointer" onClick={() => handleViewDetail(order)}>
                    <td className="px-5 py-4 text-xs">
                      {new Date(order.created_at).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-semibold text-brand-text-primary">{order.customer_name ?? '고객'}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.customer_phone_number}</div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-medium">{order.product_name}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.quantity ?? 0}개</div>
                    </td>
                    <td className="px-5 py-4 text-right font-semibold text-brand-success">{(order.price ?? 0).toLocaleString()}원</td>
                    <td className="px-5 py-4 max-w-[180px] truncate"><span className="text-xs text-brand-text-secondary">{order.delivery_place}</span></td>
                    <td className="px-5 py-4 text-center"><span className="text-xs text-brand-text-secondary">{order.channel_order ?? '-'}</span></td>
                    <td className="px-5 py-4 text-center">{renderStatusBadge(order.rpa_status)}</td>
                    <td className="px-5 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-2">
                        <button onClick={() => handleViewDetail(order)} className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-secondary hover:text-brand-primary transition" title="상세 보기">
                          <Eye className="h-4 w-4" />
                        </button>
                        {order.rpa_status === 'fail' && (
                          <button onClick={() => handleRequeue(order.id)} className="p-1.5 hover:bg-brand-warning/15 rounded-lg text-brand-warning transition" title="RPA 재전송">
                            <RefreshCw className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 하단 요약바 */}
        {!loading && filteredOrders.length > 0 && (
          <div className="flex items-center justify-end gap-6 px-6 py-4 border-t border-brand-border/80 bg-brand-card/40 text-sm">
            <span className="text-brand-text-secondary">총 건수 <span className="font-bold text-brand-text-primary">{totalCount.toLocaleString()}</span>건</span>
            <span className="text-brand-text-secondary">총 금액 <span className="font-bold text-brand-success">{totalAmount.toLocaleString()}</span>원</span>
          </div>
        )}
      </div>

      {/* 읽기전용 상세 모달 */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in-up">
          <div className="glass-panel w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden border border-brand-border flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 border-b border-brand-border/80 flex justify-between items-center bg-brand-card">
              <div className="flex items-center gap-2">
                <ShoppingBag className="h-5 w-5 text-brand-primary" />
                <h3 className="font-semibold text-brand-text-primary text-base">주문 상세 명세서</h3>
                {renderStatusBadge(selectedOrder.rpa_status)}
                <span className="text-xs text-brand-text-muted">({selectedOrder.channel_order ?? '-'})</span>
              </div>
              <button onClick={() => setSelectedOrder(null)} className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-muted hover:text-brand-text-primary transition">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {modalSuccess && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-success/15 border border-brand-success/30 rounded-lg text-brand-success text-xs">
                  <CheckCircle2 className="h-4.5 w-4.5" /><span>{modalSuccess}</span>
                </div>
              )}
              {modalError && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-error/15 border border-brand-error/30 rounded-lg text-brand-error text-xs">
                  <AlertCircle className="h-4.5 w-4.5" /><span>{modalError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <User className="h-4 w-4" /> 인적 사항 (주문 & 배달 대상)
                  </h4>
                  <div className="space-y-3.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">보내는 분:</span>
                      <span className="font-semibold">{selectedOrder.customer_name ?? '고객'} ({selectedOrder.customer_phone_number})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">받으시는 분:</span>
                      <span className="font-semibold">{selectedOrder.receiver_name} ({selectedOrder.receiver_phone_number})</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <Calendar className="h-4 w-4" /> 상품 및 배송 내역
                  </h4>
                  <div className="space-y-3.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">상품 / 수량:</span>
                      <span className="font-semibold">{selectedOrder.product_name} ({selectedOrder.quantity ?? 0}개)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">결제 가격:</span>
                      <span className="font-semibold text-brand-success">{(selectedOrder.price ?? 0).toLocaleString()} 원</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">배달 약속 일시:</span>
                      <span className="font-semibold">{new Date(selectedOrder.delivery_at).toLocaleString('ko-KR')}</span>
                    </div>
                  </div>
                </div>

                <div className="md:col-span-2 space-y-3 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <MapPin className="h-4 w-4" /> 배달 목적지 주소
                  </h4>
                  <div className="text-sm font-semibold">{selectedOrder.delivery_place}</div>
                </div>

                <div className="md:col-span-2 space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2">
                    🎗️ 리본 문구 및 메시지 카드 내역
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div className="bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">리본 경조 문구 (오른쪽 리본)</span>
                      <div className="font-semibold text-brand-text-primary">{selectedOrder.ribbon_congratulations || '(없음)'}</div>
                    </div>
                    <div className="bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">리본 보내는이 문구 (왼쪽 리본)</span>
                      <div className="font-semibold text-brand-text-primary">{selectedOrder.ribbon_sender || '(없음)'}</div>
                    </div>
                    <div className="md:col-span-2 bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">전달할 카드 메시지</span>
                      <div className="font-semibold text-brand-text-primary whitespace-pre-line">{selectedOrder.card_message || '(없음)'}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 모달 푸터: fail 시 재전송만 */}
            <div className="px-6 py-4 border-t border-brand-border/80 flex justify-between items-center bg-brand-card">
              <div>
                {selectedOrder.rpa_status === 'fail' && (
                  <button onClick={() => handleRequeue(selectedOrder.id)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-brand-warning text-brand-bg hover:bg-brand-warning/90 text-xs font-semibold rounded-lg transition">
                    <RefreshCw className="h-3.5 w-3.5" /><span>전산에 RPA로 재입력 시키기</span>
                  </button>
                )}
              </div>
              <button onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 border border-brand-border hover:bg-brand-card text-brand-text-secondary hover:text-brand-text-primary text-xs font-semibold rounded-lg transition">
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 빌드 + 타입체크**

Run: `cd frontend && npm run build`
Expected: 성공. (미사용 import 없음 — Edit2/Save/Phone/ShoppingBag 중 ShoppingBag만 사용, 나머지 제거됨.)

- [ ] **Step 3: 전체 테스트(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 전부 PASS(신규 orders 테스트 포함, 기존 회귀 없음).

- [ ] **Step 4: 커밋**
```bash
git add frontend/src/views/order_list.tsx
git commit -m "feat(frontend): 주문조회 채널/기간/상태 서버필터 + 요약바 + 읽기전용 상세(RPC)"
```

---

## Task 4: 전체 검증 + UI E2E + 브랜치 마무리 — 컨트롤러 직접

> 마이그레이션은 Task 1에서 라이브 적용됨. 이 Task는 프론트 빌드/테스트 최종 + 실제 UI E2E(컨트롤러) + finishing-a-development-branch.

- [ ] **Step 1: 프론트 테스트 + 빌드 최종**

Run: `cd frontend && npm run test -- --run` → 전부 PASS. `npm run build` → 성공.

- [ ] **Step 2: UI E2E (Playwright Node판, 컨트롤러 직접)**

> Python Playwright 불가(greenlet/MSVC). **Node판**(`npm i --no-save playwright` + `npx playwright install chromium`). B2a/B2b/C 전례. dev 서버는 `frontend/.env`(현재 레거시 anon 키) 사용. remember_token은 **로그인이 issue 하므로 시드 불필요**.

흐름:
1. 시드(Management API): 승인 member(known password) + server_call_history(핸드폰·쇼핑몰 등 다채널, **오늘 KST**) + order_details(fail/success/ready, 가격 포함, 오늘 KST).
2. dev 서버 기동 → 로그인 → 주문조회 메뉴 진입(기본 기간=오늘 자동조회).
3. 검증: 그리드에 시드 주문 표출, 채널 세그먼트 '핸드폰' 클릭 시 핸드폰 주문만, 상태 '실패' 탭 시 fail만, **요약바 총 건수·총 금액**이 표시중 행과 일치, 텍스트검색 narrowing 동작.
4. 재전송: fail 주문 행/모달의 재전송 클릭 → 상태 '대기중'(ready) 반영 + DB `rpa_status='ready'` 확인.
5. 정리(member + server_call_history + order_details delete), leftover 0.

Expected: 각 단계 PASS, 정리 0. (스크립트는 일회성 — 검증 후 삭제.)

- [ ] **Step 3: 메모리 갱신**

`MEMORY.md` + `project-ggotaiorder.md` 의 '현재 재개 지점'을 D 완료로 갱신(머지 커밋·다음 후보 E·setting_info 하드닝 이월).

- [ ] **Step 4: finishing-a-development-branch**

REQUIRED: `superpowers:finishing-a-development-branch` — 테스트 검증 → 옵션 제시(머지/PR) → 사용자 선택 실행. PR 본문에 라이브 적용·스모크·권한검증·UI E2E 결과 + 이월(setting_info(E) 하드닝, 핸드폰1·2 라인 분리) 기재.

---

## 완료 기준 (Definition of Done)
- DB: `get_orders`·`requeue_order` 라이브 적용·스모크(채널/상태 필터·재큐·네거티브)·권한 검증 완료. `order_details` anon 직접권한 회수(column_privileges 0). 백엔드 service_role 무관.
- 프론트: `orders/client`(+test), `order_list.tsx` 재작성(채널/기간/상태 서버필터 + 검색 클라이언트 + 요약바 + 읽기전용 모달 + RPC 재전송). 테스트 전부 PASS·빌드 성공.
- UI E2E: 로그인 → 주문조회 진입(오늘 자동조회) → 채널/기간/상태 필터 → 요약바 합계 → 재전송(fail→ready) 확인.
- 브랜치 머지(또는 PR) 완료.
- **이월(알려진 잔여)**: `setting_info`(E) anon 직접권한 하드닝은 모듈 E에서. 핸드폰1·2/일반전화1·2 라인 분리(백엔드 수신라인 필드)도 후속. 수동 편집(update_order)도 별도 모듈. 페이징(LIMIT 500 초과)도 후속.
```
