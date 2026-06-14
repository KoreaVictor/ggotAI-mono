# ggotAIya C 대시보드 상황판 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 안티그래비티 dashboard.tsx의 가짜 상태·하드코딩·미작동 Realtime·shop_key=1 고정을, 샵 범위 `get_dashboard` RPC + 2.5초 안전 폴링 + 실데이터 6채널 그리드로 교체하고 `server_call_history`를 하드닝한다.

**Architecture:** 단일 `get_dashboard(shop_key, token)` SECURITY DEFINER RPC가 server_call_history+order_details+setting_info를 샵 범위로 서버측 집계. 토큰은 기존 remember_token 재사용(로그인 시 항상 발급→인메모리 readToken). 프론트는 데이터=RPC, 현재작업 문자열=순수함수. Supabase Realtime 제거.

**Tech Stack:** Postgres(pgcrypto) RPC, React+Vite+TypeScript, Vitest, Electron IPC(서비스 제어 기존 유지). 라이브 적용=Management API(curl UA, PAT).

**설계서:** `docs/superpowers/specs/2026-06-07-ggotaiya-c-dashboard-design.md`
**브랜치:** `feature/ggotaiya-c-dashboard` (master `923c8ea`에서 분기, 이미 생성됨)

## 파일 구조
- Create: `docs/migrations/2026-06-07-c-dashboard.sql` — get_dashboard + server_call_history 하드닝
- Create: `frontend/src/dashboard/client.ts` + `client.test.ts` — RPC 래퍼·타입
- Create: `frontend/src/dashboard/currentTask.ts` + `currentTask.test.ts` — 현재작업 파생·채널 정의(순수)
- Modify: `frontend/src/session/rememberToken.ts` + `rememberToken.test.ts` — restoreSession 반환 `{session,token}`
- Modify: `frontend/src/session/SessionContext.tsx` — readToken 항상 발급·노출
- Modify(재작성): `frontend/src/views/dashboard.tsx` — 폴링·6채널 그리드

---

## Task 1: DB 마이그레이션 (get_dashboard + server_call_history 하드닝) — 라이브, 컨트롤러 직접

> SQL을 파일로 기록하고 Management API로 적용 후 스모크/권한 검증. **라이브 DB 변경이라 컨트롤러가 직접(서브에이전트 위임 금지).** MCP Unauthorized 시 `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query` + `Authorization: Bearer <PAT>` + **User-Agent: curl**.

**Files:** Create: `docs/migrations/2026-06-07-c-dashboard.sql`

- [ ] **Step 1: 마이그레이션 SQL 파일 작성**

`docs/migrations/2026-06-07-c-dashboard.sql`:
```sql
-- ggotAIya C: 대시보드 상황판 — get_dashboard 샵범위 RPC + server_call_history 하드닝
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

create or replace function get_dashboard(p_shop_key int, p_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_set    setting_info%rowtype;
  v_today  timestamptz := ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'Asia/Seoul';
  v_stats json; v_channels json; v_config json; v_feed json;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  -- stats
  select json_build_object(
    'today_total', (select count(*) from server_call_history where shop_key = p_shop_key and created_at >= v_today),
    'rpa_success', (select count(*) from order_details where shop_key = p_shop_key and created_at >= v_today and rpa_status = 'success'),
    'rpa_fail',    (select count(*) from order_details where shop_key = p_shop_key and created_at >= v_today and rpa_status = 'fail'),
    'rpa_ready',   (select count(*) from order_details where shop_key = p_shop_key and created_at >= v_today and rpa_status = 'ready')
  ) into v_stats;

  -- channels (by channel_order)
  select coalesce(json_agg(json_build_object(
           'channel_order', t.channel_order, 'total', t.total, 'success', t.success)), '[]'::json)
    into v_channels
  from (
    select sch.channel_order,
           count(distinct sch.id) as total,
           count(*) filter (where od.rpa_status = 'success') as success
    from server_call_history sch
    left join order_details od on od.call_history_id = sch.id
    where sch.shop_key = p_shop_key and sch.created_at >= v_today
    group by sch.channel_order
  ) t;

  -- config
  select * into v_set from setting_info where shop_key = p_shop_key limit 1;
  v_config := json_build_object(
    'garjeon', coalesce(v_set.order_landline_1,'') <> '' or coalesce(v_set.order_landline_2,'') <> '',
    'hp1',     coalesce(v_set.order_hp_1,'') <> '',
    'hp2',     coalesce(v_set.order_hp_2,'') <> '',
    'voice',   true,
    'mall',    coalesce(v_set.shopping_mall_url,'') <> '' and coalesce(v_set.shopping_mall_id,'') <> '' and coalesce(v_set.shopping_mall_password,'') <> '',
    'intranet',coalesce(v_set.intranet_url,'') <> '' and coalesce(v_set.intranet_id,'') <> '' and coalesce(v_set.intranet_password,'') <> ''
  );

  -- feed (recent 8; rpa_status via 상관 서브쿼리로 1건만)
  select coalesce(json_agg(f order by f.created_at desc), '[]'::json) into v_feed
  from (
    select sch.id, sch.channel_order, sch.customer_name, sch.stt_text, sch.is_order,
           (select od.rpa_status from order_details od where od.call_history_id = sch.id order by od.id desc limit 1) as rpa_status,
           sch.created_at
    from server_call_history sch
    where sch.shop_key = p_shop_key
    order by sch.created_at desc
    limit 8
  ) f;

  return json_build_object('ok', true, 'stats', v_stats, 'channels', v_channels, 'config', v_config, 'feed', v_feed);
end;
$$;

grant execute on function get_dashboard(int, text) to anon;

-- 하드닝: server_call_history anon/authenticated 직접권한 회수(대시보드 전용 테이블; get_dashboard=owner 실행)
revoke all privileges on table server_call_history from anon, authenticated, public;
```

- [ ] **Step 2: 적용 전 확인 (컨트롤러)**

Run: 다른 프론트 코드가 `server_call_history`를 직접 읽는지 재확인(대시보드만이어야 함).
```bash
git grep -n "server_call_history" frontend/src
```
Expected: `views/dashboard.tsx` 에서만 등장(곧 재작성됨). order_list/settings 등 다른 화면은 미등장.

- [ ] **Step 3: 마이그레이션 적용 (컨트롤러 직접)**

Run: 위 SQL 전체를 Management API `database/query` 로 실행.
Expected: `[]` (에러 없음).

- [ ] **Step 4: 라운드트립 스모크 (컨트롤러 직접)**

Run: 아래 DO 블록(시드→검증→정리). 성공 시 `[]`, 실패 시 예외.

> NOT NULL 제약: `server_call_history`는 channel_classification·shop_key·shop_name·call_date·call_time 필수. `order_details`는 call_history_id·shop_key·shop_name·customer_phone_number·product_name·delivery_at·delivery_place·receiver_name·receiver_phone_number 필수. 시드에 모두 채운다.
```sql
do $$
declare
  v_id bigint; v_ch2 bigint; v_ch3 bigint; r json;
  v_d date := (now() at time zone 'Asia/Seoul')::date;
  v_t time := (now() at time zone 'Asia/Seoul')::time;
begin
  insert into member_info(username,password,shop_name,representative_name,mobile_number,is_approved,
                          remember_token_hash,remember_token_expires_at)
  values('cdashsmoke', crypt('pw',gen_salt('bf')), 'C스모크','대표','01077770003','Y',
         crypt('CTOKEN',gen_salt('bf')), now()+interval '1 day') returning id into v_id;

  insert into setting_info(shop_key, order_hp_1, shopping_mall_url, shopping_mall_id, shopping_mall_password)
  values(v_id, '010-1111-2222', 'https://m', 'mid', 'mpw');

  -- ① STT중(stt null,is_order null)
  insert into server_call_history(channel_order,channel_classification,shop_key,shop_name,customer_name,call_date,call_time,stt_text,is_order)
  values('핸드폰','c1',v_id,'C스모크','홍A',v_d,v_t,null,null);
  -- ② 주문정보중(stt 있음,is_order null) → ready order_details 연결
  insert into server_call_history(channel_order,channel_classification,shop_key,shop_name,customer_name,call_date,call_time,stt_text,is_order)
  values('핸드폰','c2',v_id,'C스모크','홍B',v_d,v_t,'장미 주문',null) returning id into v_ch2;
  -- ③ 주문Y(쇼핑몰) → success order_details 연결
  insert into server_call_history(channel_order,channel_classification,shop_key,shop_name,customer_name,call_date,call_time,stt_text,is_order)
  values('쇼핑몰','c3',v_id,'C스모크','홍C',v_d,v_t,'국화','Y') returning id into v_ch3;

  insert into order_details(call_history_id,shop_key,shop_name,customer_name,customer_phone_number,product_name,
                            delivery_at,delivery_place,receiver_name,receiver_phone_number,rpa_status)
  values(v_ch3,v_id,'C스모크','홍C','01000000003','국화', now(),'서울','받는이','01000000009','success');
  insert into order_details(call_history_id,shop_key,shop_name,customer_name,customer_phone_number,product_name,
                            delivery_at,delivery_place,receiver_name,receiver_phone_number,rpa_status)
  values(v_ch2,v_id,'C스모크','홍B','01000000002','장미', now(),'부산','받는이2','01000000008','ready');

  r := get_dashboard(v_id::int, 'CTOKEN');
  if (r->>'ok')::boolean is not true then raise exception 'GD ok: %', r; end if;
  if (r#>>'{stats,today_total}')::int <> 3 then raise exception 'GD total: %', r; end if;
  if (r#>>'{stats,rpa_success}')::int <> 1 then raise exception 'GD success: %', r; end if;
  if (r#>>'{stats,rpa_ready}')::int <> 1 then raise exception 'GD ready: %', r; end if;
  if (r#>>'{config,hp1}')::boolean is not true then raise exception 'GD hp1: %', r; end if;
  if (r#>>'{config,mall}')::boolean is not true then raise exception 'GD mall: %', r; end if;
  if (r#>>'{config,intranet}')::boolean is not false then raise exception 'GD intranet: %', r; end if;
  if (r#>>'{config,voice}')::boolean is not true then raise exception 'GD voice: %', r; end if;
  if json_array_length(r->'feed') <> 3 then raise exception 'GD feed len: %', r; end if;

  -- 네거티브: 틀린 토큰
  r := get_dashboard(v_id::int, 'WRONG');
  if (r->>'reason') <> 'unauthorized' then raise exception 'GD wrongtoken: %', r; end if;

  -- 정리(필수)
  delete from order_details where shop_key=v_id;
  delete from server_call_history where shop_key=v_id;
  delete from setting_info where shop_key=v_id;
  delete from member_info where id=v_id;
  raise notice 'C SMOKE ALL PASSED';
end $$;
```
Expected: `[]`.

- [ ] **Step 5: 권한 검증 (컨트롤러 직접)**
```sql
select has_table_privilege('anon','server_call_history','select') as sel,   -- false
       has_table_privilege('anon','server_call_history','update') as upd,   -- false
       has_table_privilege('anon','server_call_history','delete') as del,   -- false
       (select count(*) from information_schema.column_privileges
          where table_name='server_call_history' and grantee in ('anon','authenticated')) as anon_cols,  -- 0
       has_function_privilege('anon','get_dashboard(integer,text)','execute') as gd;  -- true
```
Expected: `sel=false, upd=false, del=false, anon_cols=0, gd=true`.

- [ ] **Step 6: 커밋**
```bash
git add docs/migrations/2026-06-07-c-dashboard.sql
git commit -m "feat(db): C 대시보드 get_dashboard RPC + server_call_history 하드닝"
```

---

## Task 2: dashboard/client.ts + currentTask.ts (순수 래퍼·파생) — TDD, 서브에이전트

**Files:**
- Create: `frontend/src/dashboard/client.ts`, `frontend/src/dashboard/client.test.ts`
- Create: `frontend/src/dashboard/currentTask.ts`, `frontend/src/dashboard/currentTask.test.ts`

- [ ] **Step 1: client 실패 테스트 작성** — `frontend/src/dashboard/client.test.ts`
```ts
import { describe, it, expect } from 'vitest';
import { getDashboard, type DashRpc } from './client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const DATA = {
  ok: true,
  stats: { today_total: 3, rpa_success: 1, rpa_fail: 0, rpa_ready: 2 },
  channels: [{ channel_order: '핸드폰', total: 2, success: 0 }],
  config: { garjeon: false, hp1: true, hp2: false, voice: true, mall: true, intranet: false },
  feed: [{ id: 1, channel_order: '핸드폰', customer_name: '홍', stt_text: null, is_order: null, rpa_status: null, created_at: '2026-06-07T00:00:00Z' }],
};

describe('getDashboard', () => {
  it('성공이면 data 반환', async () => {
    const r = await getDashboard(fakeRpc(DATA), 7, 'tk');
    expect(r.ok).toBe(true);
    expect(r.data?.stats.today_total).toBe(3);
    expect(r.data?.channels[0].channel_order).toBe('핸드폰');
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getDashboard(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad');
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getDashboard(fakeRpc(null, { message: 'boom' }), 7, 'tk');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});
```

- [ ] **Step 2: currentTask 실패 테스트 작성** — `frontend/src/dashboard/currentTask.test.ts`
```ts
import { describe, it, expect } from 'vitest';
import { deriveCurrentTask, latestForChannel, CHANNELS } from './currentTask';
import type { FeedRow } from './client';

function row(p: Partial<FeedRow>): FeedRow {
  return { id: 1, channel_order: '핸드폰', customer_name: null, stt_text: null, is_order: null, rpa_status: null, created_at: '2026-06-07T00:00:00Z', ...p };
}

describe('deriveCurrentTask', () => {
  it('행 없음 → 대기', () => expect(deriveCurrentTask(undefined)).toBe('대기'));
  it('is_order null + stt 없음 → STT 분석중', () => expect(deriveCurrentTask(row({ stt_text: null }))).toBe('STT 분석중'));
  it('is_order null + stt 있음 → 주문정보 분석중', () => expect(deriveCurrentTask(row({ stt_text: '장미' }))).toBe('주문정보 분석중'));
  it('N → 주문 아님', () => expect(deriveCurrentTask(row({ is_order: 'N' }))).toBe('주문 아님'));
  it('Y + ready → 입력 대기', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'ready' }))).toBe('입력 대기'));
  it('Y + success → 입력 완료', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'success' }))).toBe('입력 완료'));
  it('Y + fail → 입력 실패', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'fail' }))).toBe('입력 실패'));
  it('Y + rpa null → 대기', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: null }))).toBe('대기'));
});

describe('latestForChannel', () => {
  it('해당 채널 첫 매치 반환(피드는 desc 전제)', () => {
    const feed = [row({ id: 2, channel_order: '쇼핑몰' }), row({ id: 1, channel_order: '핸드폰' })];
    expect(latestForChannel(feed, '핸드폰')?.id).toBe(1);
    expect(latestForChannel(feed, '없음')).toBeUndefined();
  });
});

describe('CHANNELS', () => {
  it('6칸 정의', () => expect(CHANNELS.length).toBe(6));
  it('핸드폰1·2는 같은 channelOrder 공유', () => {
    const hp = CHANNELS.filter((c) => c.channelOrder === '핸드폰');
    expect(hp.map((c) => c.label)).toEqual(['핸드폰1', '핸드폰2']);
  });
});
```

- [ ] **Step 3: 실패 확인**

Run: `cd frontend && npm run test -- --run dashboard/`
Expected: FAIL (모듈 없음).

- [ ] **Step 4: client.ts 구현** — `frontend/src/dashboard/client.ts`
```ts
// supabase.rpc 와 호환되는 최소 계약(테스트 주입용)
export type DashRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;

export interface Stats { today_total: number; rpa_success: number; rpa_fail: number; rpa_ready: number; }
export interface ChannelAgg { channel_order: string; total: number; success: number; }
export interface Config { garjeon: boolean; hp1: boolean; hp2: boolean; voice: boolean; mall: boolean; intranet: boolean; }
export interface FeedRow {
  id: number; channel_order: string; customer_name: string | null;
  stt_text: string | null; is_order: string | null; rpa_status: string | null; created_at: string;
}
export interface DashboardData { stats: Stats; channels: ChannelAgg[]; config: Config; feed: FeedRow[]; }

export async function getDashboard(
  rpc: DashRpc, shopKey: number, token: string,
): Promise<{ ok: boolean; data?: DashboardData; reason?: string }> {
  const { data, error } = await rpc('get_dashboard', { p_shop_key: shopKey, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  const d = data as (DashboardData & { ok?: boolean; reason?: string }) | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, data: { stats: d.stats, channels: d.channels, config: d.config, feed: d.feed } };
}
```

- [ ] **Step 5: currentTask.ts 구현** — `frontend/src/dashboard/currentTask.ts`
```ts
import type { Config, FeedRow } from './client';

export function deriveCurrentTask(row?: FeedRow): string {
  if (!row) return '대기';
  if (row.is_order == null) {
    return row.stt_text && row.stt_text.trim() !== '' ? '주문정보 분석중' : 'STT 분석중';
  }
  if (row.is_order === 'N') return '주문 아님';
  switch (row.rpa_status) {
    case 'ready':   return '입력 대기';
    case 'success': return '입력 완료';
    case 'fail':    return '입력 실패';
    default:        return '대기';
  }
}

export interface ChannelDef { label: string; channelOrder: string; configKey: keyof Config; }
export const CHANNELS: ChannelDef[] = [
  { label: '가게전화', channelOrder: '가게전화', configKey: 'garjeon' },
  { label: '핸드폰1',  channelOrder: '핸드폰',   configKey: 'hp1' },
  { label: '핸드폰2',  channelOrder: '핸드폰',   configKey: 'hp2' },
  { label: '가게음성', channelOrder: '가게음성', configKey: 'voice' },
  { label: '쇼핑몰',   channelOrder: '쇼핑몰',   configKey: 'mall' },
  { label: '인터라넷', channelOrder: '인터라넷', configKey: 'intranet' },
];

export function latestForChannel(feed: FeedRow[], channelOrder: string): FeedRow | undefined {
  return feed.find((r) => r.channel_order === channelOrder);
}
```

- [ ] **Step 6: 통과 확인**

Run: `cd frontend && npm run test -- --run dashboard/`
Expected: PASS (전부).

- [ ] **Step 7: 커밋**
```bash
git add frontend/src/dashboard/
git commit -m "feat(frontend): dashboard RPC 래퍼 + 현재작업 파생/채널 정의 (+test)"
```

---

## Task 3: 세션 readToken 배선 (rememberToken + SessionContext) — 서브에이전트

**Files:**
- Modify: `frontend/src/session/rememberToken.ts`, `frontend/src/session/rememberToken.test.ts`
- Modify: `frontend/src/session/SessionContext.tsx`

- [ ] **Step 1: rememberToken.test.ts 갱신(반환 형태 변경 반영)**

`frontend/src/session/rememberToken.test.ts` 의 "검증 성공" 케이스를 아래로 교체:
```ts
  it('검증 성공이면 세션+토큰 반환', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    const r = await restoreSession(fakeRpc({ id: 7, shop_name: '서울꽃집', username: 'seoul' }), store);
    expect(r).toEqual({ session: { shopKey: 7, shopName: '서울꽃집', username: 'seoul' }, token: 't' });
  });
```
(나머지 3개 케이스는 `toBeNull()` 그대로 유지 — 반환 형태가 `{session,token}|null` 이라도 null 케이스는 동일.)

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm run test -- --run rememberToken`
Expected: FAIL("검증 성공" 케이스 — 현재 구현은 Session 을 직접 반환).

- [ ] **Step 3: rememberToken.ts 구현 변경**

`frontend/src/session/rememberToken.ts` 의 `restoreSession` 시그니처/반환을 변경:
```ts
export async function restoreSession(
  rpc: RpcLike, store: TokenStore,
): Promise<{ session: Session; token: string } | null> {
  const saved = await store.load();
  if (!saved) return null;

  const { data, error } = await rpc.rpc('verify_remember_token', {
    p_user_id: saved.userId,
    p_token: saved.token,
  });

  if (error || !data) {
    await store.clear();
    return null;
  }
  const row = data as RememberRow;
  return {
    session: { shopKey: row.id, shopName: row.shop_name, username: row.username },
    token: saved.token,
  };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm run test -- --run rememberToken`
Expected: PASS.

- [ ] **Step 5: SessionContext.tsx — readToken 상태/발급/노출**

`frontend/src/session/SessionContext.tsx`:

(a) `SessionContextValue` 인터페이스에 추가:
```ts
interface SessionContextValue {
  session: Session | null;
  authReady: boolean;
  readToken: string | null;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<AuthResult>;
  logout: () => void;
}
```
(b) provider 상단 상태 추가(`const [authReady, setAuthReady] = useState(false);` 아래):
```ts
  const [readToken, setReadToken] = useState<string | null>(null);
```
(c) 자동로그인 복원 effect 를 아래로 교체(restoreSession 반환 형태 변경 반영):
```ts
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const restored = await restoreSession(rpcClient, electronStore);
        if (active && restored) { setSession(restored.session); setReadToken(restored.token); }
      } finally {
        if (active) setAuthReady(true);
      }
    })();
    return () => { active = false; };
  }, []);
```
(d) `login` 콜백을 아래로 교체(항상 토큰 발급 → readToken, rememberMe 면 safeStorage 도):
```ts
  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const result = await authenticate(rpcClient, username, password);
    if (result.ok && result.session) {
      setSession(result.session);
      const { data: token } = await rpcClient.rpc('issue_remember_token', { p_user_id: result.session.shopKey });
      if (typeof token === 'string') {
        setReadToken(token);
        if (rememberMe && window.electronAPI?.saveRememberToken) {
          await window.electronAPI.saveRememberToken(result.session.shopKey, token);
        }
      }
    }
    return result;
  }, []);
```
(e) `logout` 콜백에 `setReadToken(null)` 추가:
```ts
  const logout = useCallback(() => {
    if (session) void rpcClient.rpc('clear_remember_token', { p_user_id: session.shopKey });
    void window.electronAPI?.clearRememberToken?.();
    setSession(null);
    setReadToken(null);
  }, [session]);
```
(f) Provider value 에 `readToken` 포함:
```ts
    <SessionContext.Provider value={{ session, authReady, readToken, login, logout }}>
```

- [ ] **Step 6: 전체 테스트(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 전부 PASS(기존 + 변경된 rememberToken).

- [ ] **Step 7: 빌드**

Run: `cd frontend && npm run build`
Expected: 성공.

- [ ] **Step 8: 커밋**
```bash
git add frontend/src/session/rememberToken.ts frontend/src/session/rememberToken.test.ts frontend/src/session/SessionContext.tsx
git commit -m "feat(frontend): 로그인 시 항상 readToken 발급·노출(대시보드 폴링 인증용)"
```

---

## Task 4: dashboard.tsx 재작성 (폴링·6채널 그리드, Realtime 제거) — 서브에이전트

**Files:** Modify(전면 교체): `frontend/src/views/dashboard.tsx`

- [ ] **Step 1: dashboard.tsx 전면 교체**

`frontend/src/views/dashboard.tsx` 전체를 아래로 교체:
```tsx
import { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getDashboard, type DashboardData, type DashRpc } from '../dashboard/client';
import { CHANNELS, deriveCurrentTask, latestForChannel } from '../dashboard/currentTask';
import {
  Play, Square, RefreshCw, Phone, Smartphone, Globe, Radio, MessageSquare, ShieldAlert, Clock,
} from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

type ServiceStatus = 'RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING';

function channelIcon(label: string) {
  if (label.startsWith('핸드폰')) return <Smartphone className="h-5 w-5 text-brand-primary" />;
  if (label === '가게전화') return <Phone className="h-5 w-5 text-brand-success" />;
  if (label === '쇼핑몰') return <Globe className="h-5 w-5 text-purple-400" />;
  if (label === '인터라넷') return <Radio className="h-5 w-5 text-pink-400" />;
  return <MessageSquare className="h-5 w-5 text-teal-400" />; // 가게음성
}

export function DashboardView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('LOADING');
  const [statusError, setStatusError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const [data, setData] = useState<DashboardData | null>(null);
  const [dataError, setDataError] = useState('');
  const [loading, setLoading] = useState(true);

  const checkServiceStatus = async () => {
    if (!window.electronAPI) { setServiceStatus('STOPPED'); return; }
    try {
      const res = await window.electronAPI.getServiceStatus();
      if (res.error) setStatusError(res.error);
      setServiceStatus(res.status);
    } catch { setServiceStatus('STOPPED'); }
  };

  const fetchData = async () => {
    if (!shopKey || !readToken) { setDataError('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
    const r = await getDashboard(rpc, shopKey, readToken);
    if (!r.ok || !r.data) { setDataError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '상황판 데이터를 불러오지 못했습니다.'); setLoading(false); return; }
    setDataError(''); setData(r.data); setLoading(false);
  };

  useEffect(() => {
    checkServiceStatus();
    fetchData();
    const svc = setInterval(checkServiceStatus, 2500);
    const poll = setInterval(fetchData, 2500);
    return () => { clearInterval(svc); clearInterval(poll); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shopKey, readToken]);

  const handleStart = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true); setStatusError('');
    try {
      const res = await window.electronAPI.startService();
      if (!res.success) setStatusError(res.error || '서비스를 시작하지 못했습니다.');
      await checkServiceStatus();
    } catch (e) { setStatusError(e instanceof Error ? e.message : String(e)); }
    finally { setActionLoading(false); }
  };
  const handleStop = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true); setStatusError('');
    try {
      const res = await window.electronAPI.stopService();
      if (!res.success) setStatusError(res.error || '서비스를 중지하지 못했습니다.');
      await checkServiceStatus();
    } catch (e) { setStatusError(e instanceof Error ? e.message : String(e)); }
    finally { setActionLoading(false); }
  };

  const stats = data?.stats ?? { today_total: 0, rpa_success: 0, rpa_fail: 0, rpa_ready: 0 };
  const running = serviceStatus === 'RUNNING';

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      {/* 헤더 + 마스터 제어 */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8 bg-brand-card p-6 border border-brand-border rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">ggotAIya 실시간 상황판</h1>
            <div className="flex items-center gap-1.5 px-3 py-1 bg-brand-bg/60 rounded-full border border-brand-border text-xs font-semibold">
              <span>수집엔진:</span>
              {running ? <span className="text-brand-success flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-brand-success animate-ping" /> 가동중</span>
                : serviceStatus === 'NOT_INSTALLED' ? <span className="text-brand-text-muted">⚠️ 미설치</span>
                : serviceStatus === 'LOADING' ? <span className="text-brand-text-muted animate-pulse">조회중...</span>
                : <span className="text-brand-error flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-brand-error" /> 중지됨</span>}
            </div>
          </div>
          <p className="text-brand-text-secondary text-sm">6대 채널 비정형 주문을 실시간 감지하여 자동 전산 입력을 구동합니다.</p>
        </div>
        <div className="flex items-center gap-3 justify-end">
          {statusError && <div className="flex items-center gap-1 text-xs text-brand-error font-medium max-w-xs truncate" title={statusError}><ShieldAlert className="h-4 w-4 shrink-0" /><span>권한 부족/오류</span></div>}
          {running ? (
            <button onClick={handleStop} disabled={actionLoading} className="flex items-center gap-2 px-5 py-3 bg-brand-error hover:bg-brand-error/90 disabled:bg-brand-text-muted text-white text-sm font-bold rounded-xl shadow-lg transition">
              <Square className="h-4 w-4 fill-current" /><span>주문 자동 수집 중지</span>
            </button>
          ) : (
            <button onClick={handleStart} disabled={actionLoading || serviceStatus === 'NOT_INSTALLED'} className="flex items-center gap-2 px-5 py-3 bg-brand-success hover:bg-brand-success/90 disabled:bg-brand-text-muted text-brand-bg text-sm font-bold rounded-xl shadow-lg transition">
              <Play className="h-4 w-4 fill-current" /><span>주문 자동 수집 시작</span>
            </button>
          )}
        </div>
      </div>

      {dataError && <div className="mb-6 text-sm text-brand-error bg-brand-error/10 border border-brand-error/20 rounded-xl px-4 py-3">{dataError}</div>}

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">오늘 총 수집</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-text-primary">{stats.today_total} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            <div className="text-xs text-brand-primary font-medium flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> 2.5초 동기화</div>
          </div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 입력 성공</div>
          <div className="text-3xl font-display font-bold text-brand-success">{stats.rpa_success} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 입력 실패(수동확인)</div>
          <div className="text-3xl font-display font-bold text-brand-error">{stats.rpa_fail} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">RPA 순차 입력 대기</div>
          <div className="text-3xl font-display font-bold text-brand-warning">{stats.rpa_ready} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
      </div>

      {/* 6채널 그리드 + 피드 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <h3 className="text-base font-bold text-brand-text-primary">6대 채널 작동 상태</h3>
          <div className="grid grid-cols-2 gap-3">
            {CHANNELS.map((ch) => {
              const configured = data?.config[ch.configKey] ?? false;
              const active = configured && running;
              const agg = data?.channels.find((c) => c.channel_order === ch.channelOrder);
              const task = deriveCurrentTask(data ? latestForChannel(data.feed, ch.channelOrder) : undefined);
              return (
                <div key={ch.label} className="glass-panel p-4 rounded-xl border border-brand-border space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">{channelIcon(ch.label)}<span className="text-sm font-semibold text-brand-text-primary">{ch.label}</span></div>
                    <span className={`w-2.5 h-2.5 rounded-full ${active ? 'bg-brand-success animate-pulse' : 'bg-brand-error'}`} title={active ? '작동' : (configured ? '중지' : '미설정')} />
                  </div>
                  <div className="text-[11px] text-brand-text-secondary">현재작업: <span className="font-semibold text-brand-text-primary">{configured ? task : '미사용'}</span></div>
                  <div className="text-[11px] text-brand-text-muted">오늘작업: <span className="font-semibold text-brand-success">{agg?.success ?? 0}</span>건</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-brand-text-primary">실시간 주문 수집 피드</h3>
            <button onClick={fetchData} className="p-1 hover:bg-brand-card rounded text-brand-text-secondary hover:text-brand-text-primary transition" title="새로고침"><RefreshCw className="h-4 w-4" /></button>
          </div>
          <div className="glass-panel rounded-xl p-5 border border-brand-border space-y-3 max-h-[360px] overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-primary" /></div>
            ) : !data || data.feed.length === 0 ? (
              <div className="text-center py-20 text-brand-text-muted text-sm">수집된 실시간 주문 이력이 없습니다.</div>
            ) : (
              data.feed.map((item) => (
                <div key={item.id} className="flex gap-4 p-3 bg-brand-bg/40 border border-brand-border/40 rounded-lg">
                  <div className="shrink-0 w-8 h-8 rounded-full bg-brand-card border border-brand-border flex items-center justify-center">{channelIcon(item.channel_order.startsWith('핸드폰') ? '핸드폰1' : item.channel_order)}</div>
                  <div className="flex-1 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-brand-text-primary">{item.customer_name ?? '고객'} 님 ({item.channel_order})</span>
                      <span className="text-[10px] text-brand-text-muted">{new Date(item.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                    </div>
                    <p className="text-xs text-brand-text-secondary bg-brand-bg/50 p-2.5 rounded border border-brand-border/40 font-mono">{item.stt_text || '비정형 음성 원문 추출 대기중...'}</p>
                    <div className="flex justify-end"><span className="inline-flex items-center text-[9px] font-bold text-brand-text-primary bg-brand-card px-2 py-0.5 rounded border border-brand-border">{deriveCurrentTask(item)}</span></div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 + 타입체크**

Run: `cd frontend && npm run build`
Expected: 성공. (`window.electronAPI` 타입은 기존 `types/electron.ts` 에 `getServiceStatus/startService/stopService` 존재.)

- [ ] **Step 3: 전체 테스트(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 전부 PASS(신규 dashboard 테스트 포함).

- [ ] **Step 4: 커밋**
```bash
git add frontend/src/views/dashboard.tsx
git commit -m "feat(frontend): 대시보드 6채널 실데이터 그리드 + 2.5초 폴링(Realtime 제거)"
```

---

## Task 5: 전체 검증 + DB 스모크 재확인 + UI E2E + 브랜치 마무리 — 컨트롤러 직접

> 마이그레이션은 Task 1에서 라이브 적용됨. 이 Task는 프론트 빌드/테스트 최종 + 실제 UI E2E(컨트롤러) + finishing-a-development-branch.

- [ ] **Step 1: 프론트 테스트 + 빌드 최종**

Run: `cd frontend && npm run test -- --run` → 전부 PASS. `npm run build` → 성공.

- [ ] **Step 2: UI E2E (Playwright Node판, 컨트롤러 직접)**

> Python Playwright 불가(greenlet/MSVC). **Node판**(`npm i --no-save playwright` + `npx playwright install chromium`). B2a/B2b 전례. dev 서버는 `frontend/.env`(현재 레거시 anon 키) 사용.

흐름:
1. 시드(Management API): 승인 member(known password) + setting_info(핸드폰1·쇼핑몰 구성) + server_call_history 다상태 행 + order_details(success/ready). member 의 remember_token 은 **로그인이 issue 하므로 시드 불필요**(E2E 가 실제 로그인).
2. dev 서버 기동 → 로그인(아이디/비번) → 기본 라우트=대시보드.
3. 대시보드 폴링 결과 검증: 6채널 그리드 6칸 존재, 핸드폰1 칸 `현재작업`/`오늘작업` 표시, 통계 `오늘 총 수집` ≥ 시드 수, 피드에 시드 고객명 표출.
4. 정리(member + setting_info + server_call_history + order_details delete), leftover 0.

Expected: 각 단계 PASS, 정리 0. (스크립트는 일회성 — 검증 후 삭제.)

- [ ] **Step 3: 메모리 갱신**

`MEMORY.md` + `project-ggotaiorder.md` 의 '현재 재개 지점'을 C 완료로 갱신(머지 커밋·다음 후보 D/E·order_details/setting_info 하드닝 이월).

- [ ] **Step 4: finishing-a-development-branch**

REQUIRED: `superpowers:finishing-a-development-branch` — 테스트 검증 → 옵션 제시(머지/PR) → 사용자 선택 실행. PR 본문에 라이브 적용·스모크·권한검증·UI E2E 결과 + 이월(order_details/setting_info 하드닝) 기재.

---

## 완료 기준 (Definition of Done)
- DB: `get_dashboard` 라이브 적용·스모크·권한 검증 완료. `server_call_history` anon 직접권한 회수(column_privileges 0). 백엔드 service_role 수집 무관.
- 프론트: `dashboard/client`·`dashboard/currentTask`(+test), 세션 readToken 배선(자동로그인 회귀 OK), `dashboard.tsx` 재작성(폴링·6채널·Realtime 제거). 테스트 전부 PASS·빌드 성공.
- UI E2E: 로그인 → 대시보드 6채널/통계/피드 실데이터 렌더 + 폴링 확인.
- 브랜치 머지(또는 PR) 완료.
- **이월(알려진 잔여)**: `order_details`(D)·`setting_info`(E) anon 직접권한 하드닝은 각 모듈에서. 핸드폰1·2/일반전화1·2 라인 분리(백엔드 수신라인 필드)도 후속.
```
