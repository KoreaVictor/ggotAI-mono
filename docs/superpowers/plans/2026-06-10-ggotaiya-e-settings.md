# ggotAIya E 환경설정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 안티그래비티 settings.tsx의 `shop_key=1` 하드코딩·`setting_info` 직접 SELECT/UPSERT를, 샵 범위 `get_settings`/`save_settings` SECURITY DEFINER RPC + 비번 "설정됨/미설정" 뱃지로 교체하고 `setting_info`를 하드닝한다.

**Architecture:** `get_settings(shop_key, token)` RPC가 setting_info 행을 비번 ciphertext 제외 + `has_*` boolean으로 반환. `save_settings(shop_key, token, settings jsonb, sm_pw, it_pw)` RPC가 UPDATE→없으면 INSERT upsert(비번 null=기존 보존). 토큰은 기존 remember_token(C/D에서 배선된 인메모리 readToken). 암호화는 클라이언트 유지(`encryptPassword`).

**Tech Stack:** Postgres(pgcrypto) RPC, React+Vite+TypeScript, Vitest, crypto-js AES. 라이브 적용=Management API(curl UA, PAT).

**설계서:** `docs/superpowers/specs/2026-06-10-ggotaiya-e-settings-design.md`
**브랜치:** `feature/ggotaiya-e-settings` (master `44b07a9`에서 분기, 설계서 커밋 `2020d05` 포함 — 이미 생성됨)

## 파일 구조
- Create: `docs/migrations/2026-06-10-e-settings.sql` — get_settings + save_settings + setting_info 하드닝
- Create: `frontend/src/settings/client.ts` + `client.test.ts` — RPC 래퍼·타입(`DashRpc`는 dashboard/client에서 재사용)
- Modify(재작성): `frontend/src/views/settings.tsx` — RPC 경유, 비번 뱃지, 세션 shopKey

## 사전 사실 (확인됨)
- `readToken`/`session.shopKey`는 **이미 SessionContext에 배선됨**(C에서 완료, `useSession()`). 세션 배선 Task 불필요.
- 프론트에서 `setting_info` 직접 접근 화면은 `settings.tsx` **단 하나**(grep: crypto.ts·crypto.test.ts·settings.tsx만 매치, 그중 setting_info 직접 쿼리는 settings.tsx뿐).
- `setting_info` 19컬럼. `order_hp_1` **NOT NULL**, `shop_key` NOT NULL. 비밀 컬럼=`shopping_mall_password`/`intranet_password`(nullable).
- `utils/crypto.ts`의 `encryptPassword(plain) -> "iv_hex:ciphertext_b64"`(AES-256-CBC, 기존). `decryptPassword`도 있으나 프론트 미사용(유지).

---

## Task 1: DB 마이그레이션 (get_settings + save_settings + setting_info 하드닝) — 라이브, 컨트롤러 직접

> SQL을 파일로 기록하고 Management API로 적용 후 스모크/권한 검증. **라이브 DB 변경이라 컨트롤러가 직접(서브에이전트 위임 금지).** MCP Unauthorized 시 `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query` + `Authorization: Bearer <PAT>` + **User-Agent: curl**.

**Files:** Create: `docs/migrations/2026-06-10-e-settings.sql`

- [ ] **Step 1: 마이그레이션 SQL 파일 작성**

`docs/migrations/2026-06-10-e-settings.sql`:
```sql
-- ggotAIya E: 환경설정 — get_settings / save_settings 샵범위 RPC + setting_info 하드닝
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

-- 1) 설정 조회 (비번 ciphertext 제외, has_* boolean 추가)
create or replace function get_settings(p_shop_key int, p_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_set    setting_info%rowtype;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  select * into v_set from setting_info where shop_key = p_shop_key limit 1;
  if not found then
    return json_build_object('ok', true, 'settings', null);
  end if;

  return json_build_object('ok', true, 'settings', json_build_object(
    'use_notification', v_set.use_notification,
    'notification_phone_number', v_set.notification_phone_number,
    'rpa_success_message', v_set.rpa_success_message,
    'rpa_fail_message', v_set.rpa_fail_message,
    'order_hp_1', v_set.order_hp_1,
    'order_hp_2', v_set.order_hp_2,
    'order_landline_1', v_set.order_landline_1,
    'order_landline_2', v_set.order_landline_2,
    'shopping_mall_url', v_set.shopping_mall_url,
    'shopping_mall_id', v_set.shopping_mall_id,
    'intranet_url', v_set.intranet_url,
    'intranet_id', v_set.intranet_id,
    'shopping_mall_check_interval', v_set.shopping_mall_check_interval,
    'intranet_check_interval', v_set.intranet_check_interval,
    'has_shopping_mall_password', coalesce(v_set.shopping_mall_password,'') <> '',
    'has_intranet_password', coalesce(v_set.intranet_password,'') <> ''
  ));
end;
$$;

-- 2) 설정 저장 (UPDATE→없으면 INSERT, 비번 null=기존 보존)
create or replace function save_settings(
  p_shop_key int,
  p_token    text,
  p_settings jsonb,
  p_shopping_mall_password text default null,
  p_intranet_password      text default null
) returns json
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

  if coalesce(nullif(p_settings->>'order_hp_1',''), '') = '' then
    return json_build_object('ok', false, 'reason', 'order_hp_1_required');
  end if;

  update setting_info set
    use_notification = coalesce(p_settings->>'use_notification','Y'),
    notification_phone_number = nullif(p_settings->>'notification_phone_number',''),
    rpa_success_message = p_settings->>'rpa_success_message',
    rpa_fail_message = p_settings->>'rpa_fail_message',
    order_hp_1 = p_settings->>'order_hp_1',
    order_hp_2 = nullif(p_settings->>'order_hp_2',''),
    order_landline_1 = nullif(p_settings->>'order_landline_1',''),
    order_landline_2 = nullif(p_settings->>'order_landline_2',''),
    shopping_mall_url = nullif(p_settings->>'shopping_mall_url',''),
    shopping_mall_id  = nullif(p_settings->>'shopping_mall_id',''),
    intranet_url = nullif(p_settings->>'intranet_url',''),
    intranet_id  = nullif(p_settings->>'intranet_id',''),
    shopping_mall_check_interval = coalesce((p_settings->>'shopping_mall_check_interval')::int, 10),
    intranet_check_interval      = coalesce((p_settings->>'intranet_check_interval')::int, 30),
    shopping_mall_password = coalesce(p_shopping_mall_password, shopping_mall_password),
    intranet_password      = coalesce(p_intranet_password, intranet_password)
  where shop_key = p_shop_key;
  get diagnostics v_count = row_count;

  if v_count = 0 then
    insert into setting_info(
      shop_key, use_notification, notification_phone_number, rpa_success_message, rpa_fail_message,
      order_hp_1, order_hp_2, order_landline_1, order_landline_2,
      shopping_mall_url, shopping_mall_id, shopping_mall_password,
      intranet_url, intranet_id, intranet_password,
      shopping_mall_check_interval, intranet_check_interval)
    values(
      p_shop_key,
      coalesce(p_settings->>'use_notification','Y'),
      nullif(p_settings->>'notification_phone_number',''),
      p_settings->>'rpa_success_message',
      p_settings->>'rpa_fail_message',
      p_settings->>'order_hp_1',
      nullif(p_settings->>'order_hp_2',''),
      nullif(p_settings->>'order_landline_1',''),
      nullif(p_settings->>'order_landline_2',''),
      nullif(p_settings->>'shopping_mall_url',''),
      nullif(p_settings->>'shopping_mall_id',''),
      p_shopping_mall_password,
      nullif(p_settings->>'intranet_url',''),
      nullif(p_settings->>'intranet_id',''),
      p_intranet_password,
      coalesce((p_settings->>'shopping_mall_check_interval')::int, 10),
      coalesce((p_settings->>'intranet_check_interval')::int, 30));
  end if;

  return json_build_object('ok', true);
end;
$$;

grant execute on function get_settings(int, text) to anon;
grant execute on function save_settings(int, text, jsonb, text, text) to anon;

-- 하드닝: setting_info anon/authenticated/public 직접권한 회수(조회/저장은 owner 실행 RPC로만)
revoke all privileges on table setting_info from anon, authenticated, public;
```

- [ ] **Step 2: 적용 전 확인 (컨트롤러)**

Run: 다른 프론트 코드가 `setting_info`를 직접 읽는지 재확인(settings.tsx 만이어야 함).
```bash
git grep -n "from('setting_info')\|setting_info" frontend/src
```
Expected: `views/settings.tsx` 에서만 `setting_info` 직접 쿼리(곧 재작성됨). dashboard/order_list 등은 미등장(get_dashboard는 RPC 내부에서 setting_info 읽음 — owner 실행이라 무관).

- [ ] **Step 3: 마이그레이션 적용 (컨트롤러 직접)**

Run: 위 SQL 전체를 Management API `database/query` 로 실행.
Expected: `[]` (에러 없음).

- [ ] **Step 4: 라운드트립 스모크 (컨트롤러 직접)**

Run: 아래 DO 블록(시드→검증→정리). 성공 시 `[]`, 실패 시 예외.
```sql
do $$
declare
  v_id bigint; r json; v_pw text;
begin
  insert into member_info(username,password,shop_name,representative_name,mobile_number,is_approved,
                          remember_token_hash,remember_token_expires_at)
  values('esetsmoke', crypt('pw',gen_salt('bf')), 'E스모크','대표','01077770005','Y',
         crypt('ETOKEN',gen_salt('bf')), now()+interval '1 day') returning id into v_id;

  -- ① 행 없음 → settings null (json null 은 ->> 로 SQL NULL)
  r := get_settings(v_id::int, 'ETOKEN');
  if (r->>'ok')::boolean is not true or (r->>'settings') is not null then
    raise exception 'GS empty: %', r; end if;

  -- ② save(INSERT) + 비번 2개
  r := save_settings(v_id::int, 'ETOKEN',
        jsonb_build_object('use_notification','Y','order_hp_1','010-1','shopping_mall_url','https://m',
                           'shopping_mall_id','mid','intranet_url','https://i','intranet_id','iid',
                           'shopping_mall_check_interval','15','intranet_check_interval','40',
                           'rpa_success_message','s','rpa_fail_message','f'),
        'sm_cipher_v1', 'it_cipher_v1');
  if (r->>'ok')::boolean is not true then raise exception 'SAVE insert: %', r; end if;

  -- ③ get → 라운드트립 + has_* true + 비번 미반환
  r := get_settings(v_id::int, 'ETOKEN');
  if (r#>>'{settings,order_hp_1}') <> '010-1' then raise exception 'GS hp1: %', r; end if;
  if (r#>>'{settings,shopping_mall_check_interval}')::int <> 15 then raise exception 'GS smint: %', r; end if;
  if (r#>>'{settings,has_shopping_mall_password}')::boolean is not true then raise exception 'GS has_sm: %', r; end if;
  if (r#>>'{settings,has_intranet_password}')::boolean is not true then raise exception 'GS has_it: %', r; end if;
  if (r#>>'{settings,shopping_mall_password}') is not null then raise exception 'GS leak sm pw: %', r; end if;
  if (r#>>'{settings,intranet_password}') is not null then raise exception 'GS leak it pw: %', r; end if;

  -- ④ save(UPDATE) 비번 null=보존, 다른 필드만 변경
  r := save_settings(v_id::int, 'ETOKEN',
        jsonb_build_object('use_notification','N','order_hp_1','010-2','rpa_success_message','s2','rpa_fail_message','f2'),
        null, null);
  if (r->>'ok')::boolean is not true then raise exception 'SAVE update: %', r; end if;
  select shopping_mall_password into v_pw from setting_info where shop_key=v_id;
  if v_pw <> 'sm_cipher_v1' then raise exception 'PW not preserved: %', v_pw; end if;
  r := get_settings(v_id::int, 'ETOKEN');
  if (r#>>'{settings,order_hp_1}') <> '010-2' then raise exception 'GS hp1 upd: %', r; end if;
  if (r#>>'{settings,use_notification}') <> 'N' then raise exception 'GS noti upd: %', r; end if;

  -- ⑤ order_hp_1 공란 거부
  r := save_settings(v_id::int, 'ETOKEN', jsonb_build_object('order_hp_1',''), null, null);
  if (r->>'reason') <> 'order_hp_1_required' then raise exception 'SAVE hp1 req: %', r; end if;

  -- ⑥ 네거티브: 틀린 토큰
  r := get_settings(v_id::int, 'WRONG');
  if (r->>'reason') <> 'unauthorized' then raise exception 'GS wrongtoken: %', r; end if;
  r := save_settings(v_id::int, 'WRONG', jsonb_build_object('order_hp_1','x'), null, null);
  if (r->>'reason') <> 'unauthorized' then raise exception 'SAVE wrongtoken: %', r; end if;

  -- 정리(필수)
  delete from setting_info where shop_key=v_id;
  delete from member_info where id=v_id;
  raise notice 'E SMOKE ALL PASSED';
end $$;
```
Expected: `[]`.

- [ ] **Step 5: 권한 검증 (컨트롤러 직접)**
```sql
select has_table_privilege('anon','setting_info','select') as sel,   -- false
       has_table_privilege('anon','setting_info','update') as upd,   -- false
       has_table_privilege('anon','setting_info','insert') as ins,   -- false
       (select count(*) from information_schema.column_privileges
          where table_name='setting_info' and grantee in ('anon','authenticated')) as anon_cols,  -- 0
       has_function_privilege('anon','get_settings(integer,text)','execute') as gs,  -- true
       has_function_privilege('anon','save_settings(integer,text,jsonb,text,text)','execute') as ss;  -- true
```
Expected: `sel=false, upd=false, ins=false, anon_cols=0, gs=true, ss=true`.

- [ ] **Step 6: 커밋**
```bash
git add docs/migrations/2026-06-10-e-settings.sql
git commit -m "feat(db): E 환경설정 get_settings/save_settings RPC + setting_info 하드닝"
```

---

## Task 2: settings/client.ts (RPC 래퍼·타입) — TDD, 서브에이전트

**Files:**
- Create: `frontend/src/settings/client.ts`, `frontend/src/settings/client.test.ts`

- [ ] **Step 1: 실패 테스트 작성** — `frontend/src/settings/client.test.ts`
```ts
import { describe, it, expect } from 'vitest';
import { getSettings, saveSettings, type SettingsData } from './client';
import type { DashRpc } from '../dashboard/client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const SET: SettingsData = {
  use_notification: 'Y', notification_phone_number: null,
  rpa_success_message: 's', rpa_fail_message: 'f',
  order_hp_1: '010-1', order_hp_2: null, order_landline_1: null, order_landline_2: null,
  shopping_mall_url: 'https://m', shopping_mall_id: 'mid', intranet_url: null, intranet_id: null,
  shopping_mall_check_interval: 15, intranet_check_interval: 40,
  has_shopping_mall_password: true, has_intranet_password: false,
};

describe('getSettings', () => {
  it('성공이면 settings 반환', async () => {
    const r = await getSettings(fakeRpc({ ok: true, settings: SET }), 7, 'tk');
    expect(r.ok).toBe(true);
    expect(r.settings?.order_hp_1).toBe('010-1');
    expect(r.settings?.has_shopping_mall_password).toBe(true);
  });
  it('행 없으면 settings null', async () => {
    const r = await getSettings(fakeRpc({ ok: true, settings: null }), 7, 'tk');
    expect(r).toEqual({ ok: true, settings: null });
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getSettings(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad');
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getSettings(fakeRpc(null, { message: 'boom' }), 7, 'tk');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('saveSettings', () => {
  it('성공이면 ok', async () => {
    const r = await saveSettings(fakeRpc({ ok: true }), 7, 'tk', SET, 'cipher', null);
    expect(r).toEqual({ ok: true });
  });
  it('order_hp_1_required 면 reason 전달', async () => {
    const r = await saveSettings(fakeRpc({ ok: false, reason: 'order_hp_1_required' }), 7, 'tk', SET, null, null);
    expect(r).toEqual({ ok: false, reason: 'order_hp_1_required' });
  });
  it('RPC 에러면 error', async () => {
    const r = await saveSettings(fakeRpc(null, { message: 'boom' }), 7, 'tk', SET, null, null);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
  it('인자를 RPC 인자로 매핑(비번 null 포함)', async () => {
    let captured: Record<string, unknown> = {};
    const rpc: DashRpc = (async (_fn: string, args: Record<string, unknown>) => {
      captured = args; return { data: { ok: true }, error: null };
    }) as DashRpc;
    await saveSettings(rpc, 7, 'tk', SET, 'smc', null);
    expect(captured.p_shop_key).toBe(7);
    expect(captured.p_token).toBe('tk');
    expect(captured.p_shopping_mall_password).toBe('smc');
    expect(captured.p_intranet_password).toBe(null);
    expect((captured.p_settings as SettingsData).order_hp_1).toBe('010-1');
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm run test -- --run settings/`
Expected: FAIL (모듈 없음).

- [ ] **Step 3: client.ts 구현** — `frontend/src/settings/client.ts`
```ts
import type { DashRpc } from '../dashboard/client';

export interface SettingsData {
  use_notification: string;
  notification_phone_number: string | null;
  rpa_success_message: string;
  rpa_fail_message: string;
  order_hp_1: string;
  order_hp_2: string | null;
  order_landline_1: string | null;
  order_landline_2: string | null;
  shopping_mall_url: string | null;
  shopping_mall_id: string | null;
  intranet_url: string | null;
  intranet_id: string | null;
  shopping_mall_check_interval: number;
  intranet_check_interval: number;
  has_shopping_mall_password: boolean;
  has_intranet_password: boolean;
}

export async function getSettings(
  rpc: DashRpc, shopKey: number, token: string,
): Promise<{ ok: boolean; settings?: SettingsData | null; reason?: string }> {
  const { data, error } = await rpc('get_settings', { p_shop_key: shopKey, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; settings?: SettingsData | null; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, settings: d.settings ?? null };
}

export async function saveSettings(
  rpc: DashRpc, shopKey: number, token: string,
  settings: SettingsData,
  shoppingMallPassword: string | null,
  intranetPassword: string | null,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await rpc('save_settings', {
    p_shop_key: shopKey, p_token: token, p_settings: settings,
    p_shopping_mall_password: shoppingMallPassword,
    p_intranet_password: intranetPassword,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true };
}
```

> 주의: `save_settings`에 넘기는 `settings`는 폼 상태 객체다. `has_shopping_mall_password`/`has_intranet_password` 키도 포함되지만 RPC의 `p_settings->>'...'` 추출은 해당 키만 읽으므로 잉여 키는 무시된다(무해). 별도 정제 불필요.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm run test -- --run settings/`
Expected: PASS (전부).

- [ ] **Step 5: 커밋**
```bash
git add frontend/src/settings/
git commit -m "feat(frontend): settings RPC 래퍼(getSettings/saveSettings) +test"
```

---

## Task 3: settings.tsx 재작성 (RPC 경유, 비번 설정됨 뱃지, 세션 shopKey) — 서브에이전트

**Files:** Modify(전면 교체): `frontend/src/views/settings.tsx`

- [ ] **Step 1: settings.tsx 전면 교체**

`frontend/src/views/settings.tsx` 전체를 아래로 교체:
```tsx
import React, { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getSettings, saveSettings, type SettingsData } from '../settings/client';
import type { DashRpc } from '../dashboard/client';
import { encryptPassword } from '../utils/crypto';
import { Save, Shield, Bell, Globe, Key, AlertTriangle, CheckCircle2, Lock } from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

const DEFAULTS: SettingsData = {
  use_notification: 'Y',
  notification_phone_number: '',
  rpa_success_message: '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.',
  rpa_fail_message: '[ggotAI 경고] {channel} 주문 자동 입력 실패! 수동 확인 바랍니다.',
  order_hp_1: '',
  order_hp_2: '',
  order_landline_1: '',
  order_landline_2: '',
  shopping_mall_url: '',
  shopping_mall_id: '',
  intranet_url: '',
  intranet_id: '',
  shopping_mall_check_interval: 10,
  intranet_check_interval: 30,
  has_shopping_mall_password: false,
  has_intranet_password: false,
};

function PwBadge({ set }: { set: boolean }) {
  return set ? (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-brand-success">
      <Lock className="h-3 w-3" /> 설정됨
    </span>
  ) : (
    <span className="text-[10px] font-bold text-brand-text-muted">미설정</span>
  );
}

export function SettingsView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const [settings, setSettings] = useState<SettingsData>(DEFAULTS);
  const [shoppingMallPassword, setShoppingMallPassword] = useState('');
  const [intranetPassword, setIntranetPassword] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      if (!shopKey || !readToken) { setErrorMsg('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
      setLoading(true);
      const r = await getSettings(rpc, shopKey, readToken);
      if (!active) return;
      if (!r.ok) {
        setErrorMsg(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '설정을 불러오지 못했습니다.');
        setLoading(false);
        return;
      }
      if (r.settings) {
        setSettings({
          ...DEFAULTS,
          ...r.settings,
          notification_phone_number: r.settings.notification_phone_number ?? '',
          order_hp_2: r.settings.order_hp_2 ?? '',
          order_landline_1: r.settings.order_landline_1 ?? '',
          order_landline_2: r.settings.order_landline_2 ?? '',
          shopping_mall_url: r.settings.shopping_mall_url ?? '',
          shopping_mall_id: r.settings.shopping_mall_id ?? '',
          intranet_url: r.settings.intranet_url ?? '',
          intranet_id: r.settings.intranet_id ?? '',
        });
      }
      setLoading(false);
    })();
    return () => { active = false; };
  }, [shopKey, readToken]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setSettings((prev) => ({ ...prev, [name]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    setErrorMsg('');

    const smPw = shoppingMallPassword.trim() ? encryptPassword(shoppingMallPassword.trim()) : null;
    const itPw = intranetPassword.trim() ? encryptPassword(intranetPassword.trim()) : null;

    const r = await saveSettings(rpc, shopKey, readToken ?? '', {
      ...settings,
      shopping_mall_check_interval: Number(settings.shopping_mall_check_interval),
      intranet_check_interval: Number(settings.intranet_check_interval),
    }, smPw, itPw);

    setSaving(false);
    if (!r.ok) {
      setErrorMsg(
        r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.'
        : r.reason === 'order_hp_1_required' ? '주문 수신 핸드폰 번호 1은 필수입니다.'
        : '설정 저장 중 오류가 발생했습니다.');
      return;
    }
    setSuccessMsg('주문 수집 환경설정이 안전하게 저장되었습니다!');
    setSettings((prev) => ({
      ...prev,
      has_shopping_mall_password: prev.has_shopping_mall_password || smPw !== null,
      has_intranet_password: prev.has_intranet_password || itPw !== null,
    }));
    setShoppingMallPassword('');
    setIntranetPassword('');
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[500px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-brand-primary"></div>
        <p className="mt-4 text-brand-text-secondary text-sm">설정 정보를 로딩하고 있습니다...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 animate-fade-in-up">
      <div className="mb-8">
        <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">수집 환경설정</h1>
        <p className="text-brand-text-secondary text-sm mt-1">다중 채널 수집 간격, 기기 정보, 연동 계정을 개인화하여 관리합니다.</p>
      </div>

      {successMsg && (
        <div className="mb-6 flex items-center gap-3 p-4 bg-brand-success/15 border border-brand-success/30 rounded-lg text-brand-success text-sm">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}
      {errorMsg && (
        <div className="mb-6 flex items-center gap-3 p-4 bg-brand-error/15 border border-brand-error/30 rounded-lg text-brand-error text-sm">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-8 max-w-5xl">

        {/* 섹션 1: 수신 기기 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Shield className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">수신 기기 식별 설정</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 1 (필수)</label>
              <input type="text" name="order_hp_1" required placeholder="예: 010-1234-5678"
                value={settings.order_hp_1} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 2</label>
              <input type="text" name="order_hp_2" placeholder="예: 010-9876-5432"
                value={settings.order_hp_2 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 1</label>
              <input type="text" name="order_landline_1" placeholder="예: 02-123-4567"
                value={settings.order_landline_1 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 2</label>
              <input type="text" name="order_landline_2" placeholder="예: 02-987-6543"
                value={settings.order_landline_2 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
          </div>
        </div>

        {/* 섹션 2: 외부 채널 연동 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Globe className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">온라인 채널 연동 설정</h2>
          </div>
          <div className="space-y-6">
            {/* 쇼핑몰 */}
            <div className="border-b border-brand-border/40 pb-6 space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>꽃가게 공식 쇼핑몰
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">쇼핑몰 관리자 로그인 주소 (URL)</label>
                  <input type="url" name="shopping_mall_url" placeholder="https://admin.myshop.com"
                    value={settings.shopping_mall_url ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input type="text" name="shopping_mall_id" placeholder="쇼핑몰 아이디"
                    value={settings.shopping_mall_id ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />새 비밀번호
                    <PwBadge set={settings.has_shopping_mall_password} />
                  </label>
                  <input type="password" placeholder="수정할 때만 입력"
                    value={shoppingMallPassword} onChange={(e) => setShoppingMallPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input type="number" name="shopping_mall_check_interval" min="1" max="120"
                    value={settings.shopping_mall_check_interval} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
              </div>
            </div>
            {/* 인트라넷 */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>화원 연합 인트라넷
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">인트라넷 로그인 주소 (URL)</label>
                  <input type="url" name="intranet_url" placeholder="https://intranet.flower-association.com"
                    value={settings.intranet_url ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input type="text" name="intranet_id" placeholder="인트라넷 아이디"
                    value={settings.intranet_id ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />새 비밀번호
                    <PwBadge set={settings.has_intranet_password} />
                  </label>
                  <input type="password" placeholder="수정할 때만 입력"
                    value={intranetPassword} onChange={(e) => setIntranetPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input type="number" name="intranet_check_interval" min="1" max="120"
                    value={settings.intranet_check_interval} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 섹션 3: 알림 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Bell className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">개인화 알림 보고 및 피드백 설정</h2>
          </div>
          <div className="space-y-6">
            <div className="flex items-center gap-4 bg-brand-bg/30 p-4 border border-brand-border/60 rounded-lg">
              <label className="text-sm font-semibold text-brand-text-primary">실시간 수집/RPA 처리 알림 수신 여부</label>
              <select name="use_notification" value={settings.use_notification} onChange={handleInputChange}
                className="bg-brand-card border border-brand-border text-brand-text-primary text-sm rounded-lg px-3 py-1.5 transition outline-none">
                <option value="Y">🟢 사용함 (권장)</option>
                <option value="N">🔴 사용 안 함</option>
              </select>
            </div>
            {settings.use_notification === 'Y' && (
              <div className="grid grid-cols-1 gap-6">
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">알림 보고 수신 사장님 핸드폰 번호</label>
                  <input type="text" name="notification_phone_number" placeholder="비워둘 시 꽃가게 대표 번호로 발송"
                    value={settings.notification_phone_number ?? ''} onChange={handleInputChange}
                    className="w-full md:w-1/2 bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 전산 입력 성공 보고 문자 템플릿</label>
                    <textarea name="rpa_success_message" rows={3} value={settings.rpa_success_message} onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y" />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">※ 변수 사용: `{'{channel}'}` (수집 채널명 치환), `{'{count}'}` (주문 개수 치환)</span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 전산 입력 실패 경고 문자 템플릿</label>
                    <textarea name="rpa_fail_message" rows={3} value={settings.rpa_fail_message} onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y" />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">※ 변수 사용: `{'{channel}'}` (수집 채널명 치환)</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-4">
          <button type="submit" disabled={saving}
            className="flex items-center gap-2 px-6 py-3 bg-brand-primary hover:bg-brand-primary-hover disabled:bg-brand-text-muted text-white text-sm font-semibold rounded-lg shadow-lg hover:shadow-brand-primary/20 transition cursor-pointer">
            {saving ? <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div> : <Save className="h-4 w-4" />}
            <span>설정 정보 저장하기</span>
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 + 타입체크**

Run: `cd frontend && npm run build`
Expected: 성공. (신규 import `Lock` 사용; `encryptPassword` 사용. 미사용 import 없음.)

- [ ] **Step 3: 전체 테스트(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 전부 PASS(신규 settings 테스트 포함, 회귀 없음).

- [ ] **Step 4: 커밋**
```bash
git add frontend/src/views/settings.tsx
git commit -m "feat(frontend): 환경설정 RPC 경유 + 비번 설정됨 뱃지 + 세션 shopKey(직접권한 제거)"
```

---

## Task 4: 전체 검증 + UI E2E + 브랜치 마무리 — 컨트롤러 직접

> 마이그레이션은 Task 1에서 라이브 적용됨. 이 Task는 프론트 빌드/테스트 최종 + 실제 UI E2E(컨트롤러) + finishing-a-development-branch.

- [ ] **Step 1: 프론트 테스트 + 빌드 최종**

Run: `cd frontend && npm run test -- --run` → 전부 PASS. `npm run build` → 성공.

- [ ] **Step 2: UI E2E (Playwright Node판, 컨트롤러 직접)**

> Python Playwright 불가(greenlet/MSVC). **Node판**(이미 설치됨: `frontend/node_modules/playwright` + chromium 캐시). B2a/B2b/C/D 전례. dev 서버는 `frontend/.env`(현재 레거시 anon 키, 유효 확인됨) 사용. remember_token은 로그인이 issue.

흐름:
1. 시드(Management API): 승인 member(known password). setting_info 행은 **시드하지 않음**(E2E가 최초 저장=INSERT 경로를 태움) 또는 일부 필드 시드 후 수정.
2. dev 서버 기동 → 로그인 → 환경설정(환경설정 네비) 진입.
3. 필드 입력(order_hp_1, 쇼핑몰 URL/ID, 비번) → 저장 → 성공 배너.
4. 재로드(페이지 재진입 또는 새로고침) → 입력값 반영 + 쇼핑몰 비번 **"설정됨" 뱃지** 표시 확인.
5. DB 확인: setting_info에 shopping_mall_password가 암호화 형태(`iv:cipher`)로 저장됨, order_hp_1 일치.
6. 정리(setting_info + member delete), leftover 0.

Expected: 각 단계 PASS, 정리 0. (스크립트는 일회성 — 검증 후 삭제.)

- [ ] **Step 3: 메모리 갱신**

`MEMORY.md` + `project-ggotaiorder.md` 의 '현재 재개 지점'을 E 완료로 갱신(머지 커밋·A~E 전 모듈 anon 하드닝 완료·잔여 후속).

- [ ] **Step 4: finishing-a-development-branch**

REQUIRED: `superpowers:finishing-a-development-branch` — 테스트 검증 → 옵션 제시(머지/PR) → 사용자 선택 실행. PR 본문에 라이브 적용·스모크·권한검증·UI E2E 결과 + 이월(비번 평문 reveal 없음·명시적 클리어 없음) 기재.

---

## 완료 기준 (Definition of Done)
- DB: `get_settings`·`save_settings` 라이브 적용·스모크(라운드트립·비번보존·order_hp_1필수·네거티브)·권한 검증 완료. `setting_info` anon 직접권한 회수(column_privileges 0). 백엔드 service_role 무관.
- 프론트: `settings/client`(+test), `settings.tsx` 재작성(RPC 경유 + 비번 설정됨/미설정 뱃지 + 세션 shopKey + 클라이언트 암호화 보존). 테스트 전부 PASS·빌드 성공.
- UI E2E: 로그인 → 환경설정 로드 → 수정·비번 입력 → 저장 → 재로드 반영 + 비번 뱃지.
- 브랜치 머지(또는 PR) 완료.
- **이월(알려진 잔여)**: 비번 평문 reveal 없음(보안), 비번 명시적 클리어 UX 없음, AES 키 프론트 임베드(기존 제약). **A~E 전 모듈 anon 직접권한 하드닝 완료**(member_info·server_call_history·order_details·setting_info).
```
