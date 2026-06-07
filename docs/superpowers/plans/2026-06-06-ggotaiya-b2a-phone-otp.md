# ggotAIya B2a (핸드폰 OTP 인프라 + 가입 인증 + 아이디/비번 찾기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 핸드폰 OTP 인프라(테이블+RPC+얇은 Edge Function)를 세우고 그 위에 가입 폰 실인증·아이디 찾기·비밀번호 재설정을 구현한다.

**Architecture:** OTP 코드 생성·해시저장·검증은 Postgres RPC(pgcrypto, B1과 동일 패턴, SECURITY DEFINER)에 두고, SMS 발송 비밀키가 필요한 부분만 얇은 Supabase Edge Function(`send-otp`)으로 격리한다. 검증 성공 시 단기 검증 토큰(랜덤·해시·단일사용·10분)을 발급하고 후속 권한 작업(가입·아이디찾기·비번재설정)이 그 토큰을 소비한다. SMS 제공사는 추상화하고 fake로 먼저 구현한다.

**Tech Stack:** Supabase Postgres(pgcrypto) · Deno Edge Function · React+Vite(TypeScript) · Vitest · `@supabase/supabase-js`

**설계서:** `docs/superpowers/specs/2026-06-06-ggotaiya-b2a-phone-otp-design.md`

**⚠️ 라이브 단계(컨트롤러 직접):** Task 1(DB 마이그레이션)·Task 2 Step 5(Edge Function 배포). 이전 세션에서 Supabase MCP가 Unauthorized였으나 이번 세션엔 `mcp__supabase__*` 도구가 연결됨 → MCP 우선 시도, 실패 시 Management API 직접호출(curl UA, B1 전례)·supabase CLI 폴백.

---

## File Structure

**DB (기록용 SQL, 적용은 MCP/Management API):**
- Create: `docs/migrations/2026-06-06-b2a-otp.sql` — 테이블 + RPC 4개 신규 + `signup_member` DROP/재생성 + 권한

**Edge Function (신규, Deno):**
- Create: `supabase/functions/send-otp/index.ts` — HTTP 핸들러(얇은 시밍)
- Create: `supabase/functions/send-otp/provider.ts` — `SmsProvider` 인터페이스 + Fake/Http 구현 + `getProvider()`
- Create: `supabase/functions/_shared/cors.ts` — CORS 헤더

**프론트 (신규, 순수·테스트 가능 로직 → 컴포넌트 순):**
- Create: `frontend/src/otp/client.ts` — `sendOtp/verifyOtp/findUsername/resetPassword/normalizePhone` 래퍼(주입형 클라이언트)
- Create: `frontend/src/otp/client.test.ts` — Vitest
- Create: `frontend/src/otp/messages.ts` — `reason`→한글 메시지 매퍼
- Create: `frontend/src/otp/messages.test.ts` — Vitest
- Create: `frontend/src/components/PhoneVerify.tsx` — 공유 OTP 컴포넌트(상태머신)
- Create: `frontend/src/views/find_id.tsx` — 아이디 찾기 화면
- Create: `frontend/src/views/find_pw.tsx` — 비밀번호 재설정 화면

**프론트 (수정):**
- Modify: `frontend/src/views/signup.tsx` — 비활성 [인증] → PhoneVerify, `signup_member` 호출에 `p_verification_token` 추가
- Modify: `frontend/src/App.tsx:6,55-56` — `FindIdView`/`FindPwView`를 `_placeholders` → `views/find_id`·`views/find_pw`에서 임포트 + `onDone` 배선

---

## Task 1: DB 마이그레이션 (테이블 + RPC + signup_member 재생성 + 권한) — 라이브

**Files:**
- Create: `docs/migrations/2026-06-06-b2a-otp.sql`

> 이 Task는 Vitest 대상이 아니다. SQL을 파일로 기록하고 MCP(또는 Management API)로 적용한 뒤 `execute_sql` 라운드트립으로 검증한다. **라이브 DB 변경이라 컨트롤러가 직접 적용한다(서브에이전트 위임 금지).**

- [ ] **Step 1: 현 스키마·기존 함수 확인**

Run(MCP): `mcp__supabase__list_tables` (schemas: `["public"]`). `member_info`(12컬럼 + B1의 remember_token_hash/expires_at) 확인, `phone_verification` 부재 확인.
Run(MCP): `mcp__supabase__execute_sql` —
```sql
select p.proname, pg_get_function_identity_arguments(p.oid) as args
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname = 'signup_member';
```
Expected: 현재 `signup_member`이 **9개 text 인자**(`p_username text, ..., p_address_detail text`)임을 확인. (DROP 대상 시그니처 확정.)

- [ ] **Step 2: 마이그레이션 SQL 파일 작성 (기록용)**

`docs/migrations/2026-06-06-b2a-otp.sql`:
```sql
-- ggotAIya B2a: 핸드폰 OTP 인프라 (phone_verification 테이블 + RPC) + signup_member 재생성
-- (Supabase MCP apply_migration 또는 Management API 로 적용. 본 파일은 버전관리 기록용.)
-- 상수: 코드 6자리 · 코드 만료 3분 · 최대 시도 5회 · 토큰 만료 10분 · 재요청 쓰로틀 30초 · 1시간 5회 상한
create extension if not exists pgcrypto;

-- ===== 테이블 =====
create table if not exists phone_verification (
  id               bigserial primary key,
  phone            text not null,                 -- 정규화(숫자만)
  purpose          text not null,                 -- 'signup' | 'find_id' | 'find_pw'
  code_hash        text not null,                 -- crypt(code, gen_salt('bf'))
  expires_at       timestamptz not null,          -- now()+3분
  attempts         int not null default 0,        -- 오답 횟수(최대 5)
  verified         boolean not null default false,
  token_hash       text,                          -- 검증 성공 시 발급 토큰 해시
  token_expires_at timestamptz,                   -- now()+10분
  created_at       timestamptz not null default now()
);
create index if not exists idx_phone_verification_lookup
  on phone_verification (phone, purpose, created_at desc);

-- RLS 활성 + 정책 미생성 = 모든 직접 접근 거부. SECURITY DEFINER RPC만 우회.
alter table phone_verification enable row level security;

-- ===== RPC: request_otp (service_role 전용) =====
-- 레이트리밋 → 만료행 정리 → 6자리 생성·해시저장 → 평문 코드 반환. Edge Function만 호출.
create or replace function request_otp(p_phone text, p_purpose text)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_phone text := regexp_replace(coalesce(p_phone,''), '\D', '', 'g');
  v_code  text;
  v_recent timestamptz;
  v_hour_count int;
begin
  if p_purpose not in ('signup','find_id','find_pw') then
    raise exception 'INVALID_PURPOSE';
  end if;
  -- 30초 재요청 쓰로틀
  select max(created_at) into v_recent
    from phone_verification where phone = v_phone and purpose = p_purpose;
  if v_recent is not null and v_recent > now() - interval '30 seconds' then
    raise exception 'RATE_LIMIT_THROTTLE';
  end if;
  -- 1시간 5회 상한
  select count(*) into v_hour_count
    from phone_verification
   where phone = v_phone and purpose = p_purpose
     and created_at > now() - interval '1 hour';
  if v_hour_count >= 5 then
    raise exception 'RATE_LIMIT_HOURLY';
  end if;
  -- 레이트 윈도우 밖(1시간 경과) 오래된 행 정리 — 카운트에 무영향
  delete from phone_verification where created_at < now() - interval '1 hour';
  -- 6자리 코드 생성·해시저장
  v_code := lpad((floor(random()*1000000))::int::text, 6, '0');
  insert into phone_verification(phone, purpose, code_hash, expires_at)
  values (v_phone, p_purpose, crypt(v_code, gen_salt('bf')), now() + interval '3 minutes');
  return v_code;
end;
$$;

-- ===== RPC: verify_otp (anon) =====
create or replace function verify_otp(p_phone text, p_purpose text, p_code text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_phone text := regexp_replace(coalesce(p_phone,''), '\D', '', 'g');
  v_row   phone_verification%rowtype;
  v_token text;
begin
  select * into v_row from phone_verification
   where phone = v_phone and purpose = p_purpose and verified = false
   order by created_at desc limit 1;
  if not found then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  if v_row.expires_at < now() then
    return json_build_object('ok', false, 'reason', 'expired');
  end if;
  if v_row.attempts >= 5 then
    return json_build_object('ok', false, 'reason', 'too_many');
  end if;
  if v_row.code_hash <> crypt(p_code, v_row.code_hash) then
    update phone_verification set attempts = attempts + 1 where id = v_row.id;
    return json_build_object('ok', false, 'reason', 'mismatch');
  end if;
  v_token := encode(gen_random_bytes(32), 'hex');
  update phone_verification
     set verified = true,
         token_hash = crypt(v_token, gen_salt('bf')),
         token_expires_at = now() + interval '10 minutes'
   where id = v_row.id;
  return json_build_object('ok', true, 'token', v_token);
end;
$$;

-- ===== RPC: find_username (anon) =====
create or replace function find_username(p_phone text, p_shop_name text, p_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_phone text := regexp_replace(coalesce(p_phone,''), '\D', '', 'g');
  v_row   phone_verification%rowtype;
  v_username text;
begin
  select * into v_row from phone_verification
   where phone = v_phone and purpose = 'find_id' and verified = true
     and token_hash is not null and token_expires_at > now()
   order by created_at desc limit 1;
  if not found or v_row.token_hash <> crypt(p_token, v_row.token_hash) then
    return json_build_object('ok', false, 'reason', 'invalid_token');
  end if;
  update phone_verification set token_expires_at = now() where id = v_row.id;  -- 토큰 소비
  select username into v_username from member_info
   where regexp_replace(coalesce(mobile_number,''), '\D', '', 'g') = v_phone
     and shop_name = p_shop_name
   limit 1;
  if v_username is null then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  return json_build_object('ok', true, 'username', v_username);
end;
$$;

-- ===== RPC: reset_password (anon) =====
create or replace function reset_password(p_phone text, p_username text, p_new_password text, p_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_phone text := regexp_replace(coalesce(p_phone,''), '\D', '', 'g');
  v_row   phone_verification%rowtype;
  v_affected int;
begin
  select * into v_row from phone_verification
   where phone = v_phone and purpose = 'find_pw' and verified = true
     and token_hash is not null and token_expires_at > now()
   order by created_at desc limit 1;
  if not found or v_row.token_hash <> crypt(p_token, v_row.token_hash) then
    return json_build_object('ok', false, 'reason', 'invalid_token');
  end if;
  update phone_verification set token_expires_at = now() where id = v_row.id;  -- 토큰 소비
  update member_info
     set password = crypt(p_new_password, gen_salt('bf'))
   where username = p_username
     and regexp_replace(coalesce(mobile_number,''), '\D', '', 'g') = v_phone;
  get diagnostics v_affected = row_count;
  if v_affected = 0 then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  return json_build_object('ok', true);
end;
$$;

-- ===== signup_member: 9 → 10 인자 (p_verification_token 추가) =====
drop function if exists signup_member(text,text,text,text,text,text,text,text,text);

create or replace function signup_member(
  p_username text, p_password text, p_shop_name text,
  p_representative_name text, p_landline text, p_mobile text,
  p_email text, p_address text, p_address_detail text,
  p_verification_token text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_id    bigint;
  v_phone text := regexp_replace(coalesce(p_mobile,''), '\D', '', 'g');
  v_row   phone_verification%rowtype;
begin
  if exists(select 1 from member_info where username = p_username) then
    raise exception 'USERNAME_TAKEN';
  end if;
  -- 핸드폰 인증 토큰 검증·소비 (purpose=signup, 폰=p_mobile)
  select * into v_row from phone_verification
   where phone = v_phone and purpose = 'signup' and verified = true
     and token_hash is not null and token_expires_at > now()
   order by created_at desc limit 1;
  if not found or v_row.token_hash <> crypt(p_verification_token, v_row.token_hash) then
    raise exception 'PHONE_NOT_VERIFIED';
  end if;
  update phone_verification set token_expires_at = now() where id = v_row.id;
  insert into member_info(username, password, shop_name, representative_name,
    landline_number, mobile_number, email, address, address_detail, is_approved)
  values(p_username, crypt(p_password, gen_salt('bf')), p_shop_name,
    p_representative_name, p_landline, p_mobile, p_email, p_address,
    p_address_detail, 'N')
  returning id into v_id;
  return json_build_object('id', v_id, 'is_approved', 'N');
end;
$$;

-- ===== 권한 =====
-- request_otp: service_role 전용 (anon/public 코드 수확 차단)
revoke execute on function request_otp(text,text) from public;
grant execute on function request_otp(text,text) to service_role;
-- 나머지: anon
grant execute on function
  verify_otp(text,text,text),
  find_username(text,text,text),
  reset_password(text,text,text,text),
  signup_member(text,text,text,text,text,text,text,text,text,text)
  to anon;
```

- [ ] **Step 3: 마이그레이션 적용**

Run(MCP): `mcp__supabase__apply_migration` — name `b2a_phone_otp`, query = 위 SQL 전체.
Expected: 성공(에러 없음). DROP→CREATE 순서로 `signup_member` 교체됨.
(MCP Unauthorized 시: Management API `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query` + `Authorization: Bearer <PAT>` + **User-Agent: curl** 로 동일 SQL 실행. B1 전례.)

- [ ] **Step 4: 라운드트립 스모크 검증**

Run(MCP): `mcp__supabase__execute_sql` — 순차 실행(각 단계 결과 확인):
```sql
-- 1) 코드 발급(평문 반환). MCP는 elevated role 이라 request_otp 호출 가능.
select request_otp('010-1234-5678', 'find_id');           -- 6자리 코드 반환(예: '042817')
-- 2) 오답
select verify_otp('01012345678', 'find_id', '000000');     -- {"ok":false,"reason":"mismatch"}
-- 3) 정답(1)에서 반환된 코드 사용) → 토큰 발급
select verify_otp('01012345678', 'find_id', '<코드>');     -- {"ok":true,"token":"<t1>"}
-- 4) 스모크 회원 생성(가입 토큰 경로 검증용)
select request_otp('010-9999-0000', 'signup');             -- 코드 c2
select verify_otp('01099990000', 'signup', '<c2>');        -- {"ok":true,"token":"<t2>"}
select signup_member('b2asmoke','pw_smoke_123','스모크꽃집','홍길동',
                     null,'010-9999-0000',null,null,null,'<t2>');  -- {"id":..,"is_approved":"N"}
-- 5) find_username (3)의 토큰 t1 으로 — 단, find_id 토큰의 폰/꽃집과 일치하는 회원 필요)
--    위 b2asmoke 의 폰(01099990000)·꽃집(스모크꽃집)으로 find_id 재인증:
select request_otp('010-9999-0000', 'find_id');            -- 코드 c3
select verify_otp('01099990000', 'find_id', '<c3>');       -- {"ok":true,"token":"<t3>"}
select find_username('01099990000', '스모크꽃집', '<t3>'); -- {"ok":true,"username":"b2asmoke"}
select find_username('01099990000', '스모크꽃집', '<t3>'); -- 두 번째: {"ok":false,"reason":"invalid_token"} (단일사용)
-- 6) reset_password
select request_otp('010-9999-0000', 'find_pw');            -- 코드 c4
select verify_otp('01099990000', 'find_pw', '<c4>');       -- {"ok":true,"token":"<t4>"}
select reset_password('01099990000','b2asmoke','newpw_456','<t4>');  -- {"ok":true}
select verify_login('b2asmoke','newpw_456');               -- 회원 객체(비번 재설정 확인)
-- 7) 정리 (필수)
delete from member_info where username = 'b2asmoke';
delete from phone_verification where phone in ('01012345678','01099990000');
```
Expected: 코드 발급 OK, 오답=mismatch, 정답=token, 토큰 단일사용(두 번째 호출 invalid_token), 비번재설정 후 `verify_login` 성공. **정리 delete 필수.**

- [ ] **Step 5: 권한 검증**

Run(MCP): `mcp__supabase__execute_sql` —
```sql
select has_function_privilege('anon', 'request_otp(text,text)', 'execute')   as anon_request_otp,  -- false 기대
       has_function_privilege('anon', 'verify_otp(text,text,text)', 'execute') as anon_verify_otp,  -- true 기대
       has_function_privilege('anon', 'signup_member(text,text,text,text,text,text,text,text,text,text)', 'execute') as anon_signup; -- true 기대
```
Expected: `anon_request_otp=false`, `anon_verify_otp=true`, `anon_signup=true`.

- [ ] **Step 6: 마이그레이션 SQL 파일 커밋**

```bash
git add docs/migrations/2026-06-06-b2a-otp.sql
git commit -m "feat(db): B2a phone OTP 마이그레이션 SQL (phone_verification + RPC + signup_member 10인자)"
```

---

## Task 2: Edge Function `send-otp` (제공사 추상화 + 배포) — 코드는 일반, 배포는 라이브

**Files:**
- Create: `supabase/functions/_shared/cors.ts`
- Create: `supabase/functions/send-otp/provider.ts`
- Create: `supabase/functions/send-otp/index.ts`

> Deno 자동 테스트 툴체인은 미도입(Vitest/pytest 체계 유지). Edge Function은 얇은 시밍 → 수동 스모크로 검증.

- [ ] **Step 1: CORS 헤더 작성**

`supabase/functions/_shared/cors.ts`:
```ts
export const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
```

- [ ] **Step 2: 제공사 추상화 작성**

`supabase/functions/send-otp/provider.ts`:
```ts
export interface SmsProvider {
  send(to: string, text: string): Promise<void>;
}

// 오프라인/개발: 코드를 로그로 출력(절대 응답에 싣지 않음)
export class FakeSmsProvider implements SmsProvider {
  async send(to: string, text: string): Promise<void> {
    console.log(`[FakeSMS] ${to}: ${text}`);
  }
}

// 골격(계정 준비 시 페이로드 규격 완성)
export class HttpSmsProvider implements SmsProvider {
  async send(to: string, text: string): Promise<void> {
    const url = Deno.env.get('SMS_API_URL');
    const key = Deno.env.get('SMS_API_KEY');
    if (!url || !key) throw new Error('SMS env 미설정');
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, text, from: Deno.env.get('SMS_SENDER') }),
    });
    if (!res.ok) throw new Error(`SMS 발송 실패 ${res.status}`);
  }
}

export function getProvider(): SmsProvider {
  return Deno.env.get('SMS_PROVIDER') === 'http' ? new HttpSmsProvider() : new FakeSmsProvider();
}
```

- [ ] **Step 3: 핸들러 작성**

`supabase/functions/send-otp/index.ts`:
```ts
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { corsHeaders } from '../_shared/cors.ts';
import { getProvider } from './provider.ts';

const VALID_PURPOSES = ['signup', 'find_id', 'find_pw'];

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const { phone, purpose } = await req.json();
    const normPhone = String(phone ?? '').replace(/\D/g, '');
    if (normPhone.length < 10 || !VALID_PURPOSES.includes(purpose)) {
      return json({ success: false, reason: 'bad_request' }, 400);
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );
    const { data: code, error } = await supabase.rpc('request_otp', {
      p_phone: normPhone,
      p_purpose: purpose,
    });
    if (error) {
      const isRate = /RATE_LIMIT/.test(error.message);
      return json({ success: false, reason: isRate ? 'rate_limit' : 'error' }, isRate ? 429 : 400);
    }

    // 코드는 응답에 절대 싣지 않음 — SMS 로만 전달
    await getProvider().send(normPhone, `[꽃아이] 인증번호 ${code} (3분 내 입력)`);
    return json({ success: true }, 200);
  } catch (_e) {
    return json({ success: false, reason: 'send_failed' }, 502);
  }
});
```

- [ ] **Step 4: 배포 (라이브 — 컨트롤러)**

기본 `SMS_PROVIDER` 미설정 = fake 모드(시크릿 불필요). `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` 자동 주입.
Run(MCP): `mcp__supabase__deploy_edge_function` — name `send-otp`, files = 위 3개(`index.ts`, `provider.ts`, `_shared/cors.ts`).
(MCP 불가 시: `supabase functions deploy send-otp` CLI 폴백.)
Expected: 배포 성공, 함수 ACTIVE.

- [ ] **Step 5: 수동 스모크 (fake provider 코드 로그 확인)**

배포 후 curl(또는 `supabase functions serve` 로컬):
```bash
curl -i -X POST "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/send-otp" \
  -H "Authorization: Bearer <ANON_KEY>" -H "Content-Type: application/json" \
  -d '{"phone":"010-1234-5678","purpose":"find_id"}'
```
Expected: `200 {"success":true}`. Run(MCP): `mcp__supabase__get_logs`(service `edge-function`) 에서 `[FakeSMS] 01012345678: [꽃아이] 인증번호 ...` 로그 확인. 그 후 `mcp__supabase__execute_sql` 로 `delete from phone_verification where phone='01012345678';` 정리.

- [ ] **Step 6: 커밋**

```bash
git add supabase/functions/send-otp/ supabase/functions/_shared/
git commit -m "feat(edge): send-otp Edge Function (SMS 제공사 추상화, fake 우선)"
```

---

## Task 3: OTP 클라이언트 래퍼 + 메시지 매퍼 (Vitest, TDD)

**Files:**
- Create: `frontend/src/otp/client.ts`
- Test: `frontend/src/otp/client.test.ts`
- Create: `frontend/src/otp/messages.ts`
- Test: `frontend/src/otp/messages.test.ts`

- [ ] **Step 1: client 실패 테스트 작성**

`frontend/src/otp/client.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import {
  normalizePhone, sendOtp, verifyOtp, findUsername, resetPassword,
  type OtpRpc, type FunctionsClient,
} from './client';

function fakeRpc(data: unknown, error: unknown = null): OtpRpc {
  return (async () => ({ data, error })) as OtpRpc;
}
function fakeFns(data: unknown, error: unknown = null): FunctionsClient {
  return { invoke: async () => ({ data, error }) };
}

describe('normalizePhone', () => {
  it('숫자만 남긴다', () => {
    expect(normalizePhone('010-1234-5678')).toBe('01012345678');
  });
});

describe('sendOtp', () => {
  it('success:true 면 ok', async () => {
    const r = await sendOtp(fakeFns({ success: true }), '010-1', 'find_id');
    expect(r.ok).toBe(true);
  });
  it('함수 에러면 send_failed', async () => {
    const r = await sendOtp(fakeFns(null, { message: 'boom' }), '010-1', 'find_id');
    expect(r).toEqual({ ok: false, reason: 'send_failed' });
  });
  it('success:false 면 reason 전달', async () => {
    const r = await sendOtp(fakeFns({ success: false, reason: 'rate_limit' }), '010-1', 'find_id');
    expect(r).toEqual({ ok: false, reason: 'rate_limit' });
  });
});

describe('verifyOtp', () => {
  it('정답이면 토큰', async () => {
    const r = await verifyOtp(fakeRpc({ ok: true, token: 'tk' }), '010-1', 'find_id', '123456');
    expect(r).toEqual({ ok: true, token: 'tk' });
  });
  it('오답이면 reason 전달', async () => {
    const r = await verifyOtp(fakeRpc({ ok: false, reason: 'mismatch' }), '010-1', 'find_id', '0');
    expect(r).toEqual({ ok: false, reason: 'mismatch' });
  });
  it('RPC 에러면 error', async () => {
    const r = await verifyOtp(fakeRpc(null, { message: 'boom' }), '010-1', 'find_id', '0');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('findUsername', () => {
  it('성공이면 username', async () => {
    const r = await findUsername(fakeRpc({ ok: true, username: 'seoul' }), '010-1', '서울꽃집', 'tk');
    expect(r).toEqual({ ok: true, username: 'seoul' });
  });
  it('없음이면 not_found', async () => {
    const r = await findUsername(fakeRpc({ ok: false, reason: 'not_found' }), '010-1', 'x', 'tk');
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
});

describe('resetPassword', () => {
  it('성공이면 ok', async () => {
    const r = await resetPassword(fakeRpc({ ok: true }), '010-1', 'seoul', 'newpw', 'tk');
    expect(r).toEqual({ ok: true });
  });
  it('토큰무효면 invalid_token', async () => {
    const r = await resetPassword(fakeRpc({ ok: false, reason: 'invalid_token' }), '010-1', 'seoul', 'n', 'tk');
    expect(r).toEqual({ ok: false, reason: 'invalid_token' });
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd frontend; npx vitest run src/otp/client.test.ts`
Expected: FAIL — `Cannot find module './client'`.

- [ ] **Step 3: client 구현**

`frontend/src/otp/client.ts`:
```ts
export type Purpose = 'signup' | 'find_id' | 'find_pw';

// 테스트 주입용 최소 계약 (supabase.rpc / supabase.functions 와 호환)
export type OtpRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;
export interface FunctionsClient {
  invoke(name: string, opts: { body: unknown }): Promise<{ data: unknown; error: unknown }>;
}

export function normalizePhone(phone: string): string {
  return phone.replace(/\D/g, '');
}

export async function sendOtp(
  fns: FunctionsClient, phone: string, purpose: Purpose,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await fns.invoke('send-otp', { body: { phone: normalizePhone(phone), purpose } });
  if (error) return { ok: false, reason: 'send_failed' };
  const d = data as { success?: boolean; reason?: string } | null;
  if (!d?.success) return { ok: false, reason: d?.reason ?? 'send_failed' };
  return { ok: true };
}

export async function verifyOtp(
  rpc: OtpRpc, phone: string, purpose: Purpose, code: string,
): Promise<{ ok: boolean; token?: string; reason?: string }> {
  const { data, error } = await rpc('verify_otp', { p_phone: normalizePhone(phone), p_purpose: purpose, p_code: code });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; token?: string; reason?: string } | null) ?? { ok: false, reason: 'error' };
}

export async function findUsername(
  rpc: OtpRpc, phone: string, shopName: string, token: string,
): Promise<{ ok: boolean; username?: string; reason?: string }> {
  const { data, error } = await rpc('find_username', { p_phone: normalizePhone(phone), p_shop_name: shopName, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; username?: string; reason?: string } | null) ?? { ok: false, reason: 'error' };
}

export async function resetPassword(
  rpc: OtpRpc, phone: string, username: string, newPassword: string, token: string,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await rpc('reset_password', {
    p_phone: normalizePhone(phone), p_username: username, p_new_password: newPassword, p_token: token,
  });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; reason?: string } | null) ?? { ok: false, reason: 'error' };
}
```

- [ ] **Step 4: client 테스트 통과 확인**

Run: `cd frontend; npx vitest run src/otp/client.test.ts`
Expected: PASS (12 tests).

- [ ] **Step 5: messages 실패 테스트 작성**

`frontend/src/otp/messages.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { otpMessage } from './messages';

describe('otpMessage', () => {
  it('만료', () => expect(otpMessage('expired')).toContain('만료'));
  it('오답', () => expect(otpMessage('mismatch')).toContain('일치'));
  it('시도초과', () => expect(otpMessage('too_many')).toContain('초과'));
  it('없음', () => expect(otpMessage('not_found')).toContain('요청'));
  it('토큰무효', () => expect(otpMessage('invalid_token')).toContain('인증'));
  it('레이트리밋', () => expect(otpMessage('rate_limit')).toContain('잠시'));
  it('발송실패', () => expect(otpMessage('send_failed')).toContain('발송'));
  it('미상', () => expect(otpMessage(undefined)).toContain('오류'));
});
```

- [ ] **Step 6: messages 테스트 실패 확인**

Run: `cd frontend; npx vitest run src/otp/messages.test.ts`
Expected: FAIL — `Cannot find module './messages'`.

- [ ] **Step 7: messages 구현**

`frontend/src/otp/messages.ts`:
```ts
export function otpMessage(reason: string | undefined): string {
  switch (reason) {
    case 'not_found':     return '인증번호를 먼저 요청해주세요';
    case 'expired':       return '인증번호가 만료되었습니다. 다시 요청해주세요';
    case 'mismatch':      return '인증번호가 일치하지 않습니다';
    case 'too_many':      return '시도 횟수를 초과했습니다. 다시 요청해주세요';
    case 'invalid_token': return '인증이 만료되었습니다. 다시 인증해주세요';
    case 'rate_limit':    return '잠시 후 다시 시도해주세요';
    case 'send_failed':   return '인증번호 발송에 실패했습니다';
    default:              return '오류가 발생했습니다. 다시 시도해주세요';
  }
}
```

- [ ] **Step 8: messages 테스트 통과 확인**

Run: `cd frontend; npx vitest run src/otp/messages.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 9: 커밋**

```bash
git add frontend/src/otp/
git commit -m "feat(frontend): OTP 클라이언트 래퍼 + reason 메시지 매퍼 (+test)"
```

---

## Task 4: 공유 컴포넌트 `PhoneVerify`

**Files:**
- Create: `frontend/src/components/PhoneVerify.tsx`

> 컴포넌트 자동 테스트는 미도입(B1과 동일, 순수 로직은 Task 3에서 검증). `npm run build` 타입체크 + Task 8 수동 육안으로 검증.

- [ ] **Step 1: PhoneVerify 작성**

`frontend/src/components/PhoneVerify.tsx`:
```tsx
import { useState, useEffect, useRef } from 'react';
import { supabase } from '../supabase';
import { sendOtp, verifyOtp, type Purpose, type OtpRpc, type FunctionsClient } from '../otp/client';
import { otpMessage } from '../otp/messages';

// supabase.rpc / supabase.functions 를 래퍼 계약으로 단일지점 캐스트 (B1 authenticate 패턴)
const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const fns = supabase.functions as unknown as FunctionsClient;

const CODE_TTL = 180; // 초 (코드 만료 3분)

export function PhoneVerify({
  phone, purpose, onVerified,
}: {
  phone: string;
  purpose: Purpose;
  onVerified: (token: string) => void;
}) {
  const [stage, setStage] = useState<'idle' | 'sent' | 'verified'>('idle');
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const startCountdown = () => {
    setLeft(CODE_TTL);
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => {
      setLeft((s) => {
        if (s <= 1) { if (timer.current) clearInterval(timer.current); return 0; }
        return s - 1;
      });
    }, 1000);
  };

  const request = async () => {
    if (!phone.trim()) { setMsg('핸드폰 번호를 입력해주세요'); return; }
    setBusy(true); setMsg('');
    const r = await sendOtp(fns, phone, purpose);
    setBusy(false);
    if (!r.ok) { setMsg(otpMessage(r.reason)); return; }
    setStage('sent'); setCode(''); startCountdown();
    setMsg('인증번호를 발송했습니다');
  };

  const confirm = async () => {
    if (!code.trim()) { setMsg('인증번호를 입력해주세요'); return; }
    setBusy(true); setMsg('');
    const r = await verifyOtp(rpc, phone, purpose, code.trim());
    setBusy(false);
    if (!r.ok || !r.token) { setMsg(otpMessage(r.reason)); return; }
    if (timer.current) clearInterval(timer.current);
    setStage('verified'); setMsg('');
    onVerified(r.token);
  };

  const mmss = `${String(Math.floor(left / 60)).padStart(1, '0')}:${String(left % 60).padStart(2, '0')}`;

  if (stage === 'verified') {
    return <div className="text-xs text-brand-success">✓ 인증되었습니다</div>;
  }

  return (
    <div className="space-y-2">
      <button
        type="button" onClick={request} disabled={busy}
        className="shrink-0 px-3 py-2 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover disabled:opacity-50"
      >
        {stage === 'sent' ? '재전송' : '인증요청'}
      </button>
      {stage === 'sent' && (
        <div className="flex gap-2 items-center">
          <input
            value={code} onChange={(e) => setCode(e.target.value)} placeholder="인증번호 6자리"
            inputMode="numeric" maxLength={6}
            className="flex-1 px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
          />
          {left > 0 && <span className="text-xs text-brand-text-muted shrink-0">{mmss}</span>}
          <button
            type="button" onClick={confirm} disabled={busy}
            className="shrink-0 px-3 py-2.5 rounded-lg bg-brand-primary text-white text-xs font-semibold hover:opacity-90 disabled:opacity-50"
          >확인</button>
        </div>
      )}
      {msg && <div className="text-xs text-brand-text-muted">{msg}</div>}
    </div>
  );
}
```

- [ ] **Step 2: 타입체크/빌드**

Run: `cd frontend; npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS(에러 없음). (`brand-success` 클래스가 Tailwind 설정에 없으면 `brand-primary` 등 기존 클래스로 대체 — `tailwind.config` 확인.)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/PhoneVerify.tsx
git commit -m "feat(frontend): PhoneVerify 공유 OTP 컴포넌트(상태머신 idle→sent→verified)"
```

---

## Task 5: 아이디 찾기 화면 `find_id.tsx`

**Files:**
- Create: `frontend/src/views/find_id.tsx`

- [ ] **Step 1: FindIdView 작성**

`frontend/src/views/find_id.tsx`:
```tsx
import { useState } from 'react';
import { supabase } from '../supabase';
import { PhoneVerify } from '../components/PhoneVerify';
import { findUsername, type OtpRpc } from '../otp/client';
import { otpMessage } from '../otp/messages';

const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function FindIdView({ onDone }: { onDone: () => void }) {
  const [shopName, setShopName] = useState('');
  const [phone, setPhone] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState('');

  const onVerified = async (token: string) => {
    setError(''); setResult(null);
    const r = await findUsername(rpc, phone, shopName.trim(), token);
    if (r.ok && r.username) { setResult(r.username); return; }
    setError(r.reason === 'not_found' ? '일치하는 계정이 없습니다' : otpMessage(r.reason));
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">아이디 찾기</div>

        {result === null ? (
          <>
            <input value={shopName} onChange={(e) => setShopName(e.target.value)} placeholder="꽃집명" autoFocus className={INPUT} />
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="핸드폰" className={INPUT} />
            <PhoneVerify phone={phone} purpose="find_id" onVerified={onVerified} />
            {error && <div className="text-brand-error text-xs">{error}</div>}
          </>
        ) : (
          <div className="text-sm text-brand-text-primary py-4">
            회원님의 아이디는 <span className="font-bold text-brand-primary">{result}</span> 입니다.
          </div>
        )}

        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `cd frontend; npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/views/find_id.tsx
git commit -m "feat(frontend): 아이디 찾기 화면(find_id) - PhoneVerify + find_username"
```

---

## Task 6: 비밀번호 재설정 화면 `find_pw.tsx`

**Files:**
- Create: `frontend/src/views/find_pw.tsx`

- [ ] **Step 1: FindPwView 작성**

`frontend/src/views/find_pw.tsx`:
```tsx
import { useState } from 'react';
import { supabase } from '../supabase';
import { PhoneVerify } from '../components/PhoneVerify';
import { resetPassword, type OtpRpc } from '../otp/client';
import { otpMessage } from '../otp/messages';

const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function FindPwView({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState('');
  const [phone, setPhone] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError('');
    if (!pw) { setError('새 비밀번호를 입력해주세요'); return; }
    if (pw !== pw2) { setError('비밀번호가 일치하지 않습니다'); return; }
    if (!token) { setError('핸드폰 인증을 먼저 완료해주세요'); return; }
    setBusy(true);
    const r = await resetPassword(rpc, phone, username.trim(), pw, token);
    setBusy(false);
    if (r.ok) { alert('비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해주세요.'); onDone(); return; }
    setError(r.reason === 'not_found' ? '일치하는 계정이 없습니다' : otpMessage(r.reason));
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">비밀번호 찾기</div>

        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="아이디" autoFocus disabled={!!token} className={INPUT} />
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="핸드폰" disabled={!!token} className={INPUT} />

        {!token ? (
          <PhoneVerify phone={phone} purpose="find_pw" onVerified={setToken} />
        ) : (
          <>
            <input value={pw} onChange={(e) => setPw(e.target.value)} type="password" placeholder="새 비밀번호" className={INPUT} />
            <input value={pw2} onChange={(e) => setPw2(e.target.value)} type="password" placeholder="새 비밀번호 확인" className={INPUT} />
            <button type="button" onClick={submit} disabled={busy} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 disabled:opacity-50">
              {busy ? '처리 중…' : '비밀번호 재설정'}
            </button>
          </>
        )}
        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `cd frontend; npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/views/find_pw.tsx
git commit -m "feat(frontend): 비밀번호 재설정 화면(find_pw) - PhoneVerify + reset_password"
```

---

## Task 7: 회원가입 화면 수정 (`signup.tsx`)

**Files:**
- Modify: `frontend/src/views/signup.tsx`

- [ ] **Step 1: import 추가**

`frontend/src/views/signup.tsx` 상단 import 블록(1-4행)에 추가:
```tsx
import { PhoneVerify } from '../components/PhoneVerify';
```

- [ ] **Step 2: 인증 토큰 state 추가**

`const [busy, setBusy] = useState(false);`(17행) 다음 줄에 추가:
```tsx
  const [verifyToken, setVerifyToken] = useState<string | null>(null);
```

- [ ] **Step 3: 핸드폰 행을 PhoneVerify로 교체**

기존 핸드폰 입력 블록(88-91행, `<div className="flex gap-2">` ~ 비활성 [인증] 버튼 `</div>`)을 아래로 교체:
```tsx
        <input
          value={f.mobile}
          onChange={set('mobile')}
          onKeyDown={focusNext}
          placeholder="핸드폰"
          disabled={!!verifyToken}
          className={INPUT}
        />
        <PhoneVerify phone={f.mobile} purpose="signup" onVerified={setVerifyToken} />
```

- [ ] **Step 4: submit 가드 + signup_member 인자 추가**

`submit` 함수(50-69행) 내 `if (v) { setError(v); return; }`(54행) 다음에 인증 가드 추가:
```tsx
    if (!verifyToken) { setError('핸드폰 인증을 완료해주세요'); return; }
```
그리고 `supabase.rpc('signup_member', {...})` 호출(56-61행)의 인자 객체 마지막 `p_address_detail` 다음에 추가:
```tsx
      p_verification_token: verifyToken,
```
그리고 에러 처리(64행)에 PHONE_NOT_VERIFIED 분기 추가:
```tsx
      setError(
        /USERNAME_TAKEN/.test(e2.message) ? '이미 사용 중인 아이디입니다'
        : /PHONE_NOT_VERIFIED/.test(e2.message) ? '핸드폰 인증을 다시 진행해주세요'
        : '회원가입 중 오류가 발생했습니다',
      );
```

- [ ] **Step 5: 타입체크**

Run: `cd frontend; npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/views/signup.tsx
git commit -m "feat(frontend): 회원가입 핸드폰 실인증(PhoneVerify) + signup_member 토큰 인자"
```

---

## Task 8: App.tsx 배선 + 홀리스틱 검증

**Files:**
- Modify: `frontend/src/App.tsx:6,55-56`

- [ ] **Step 1: import 교체**

`frontend/src/App.tsx:6` 의
```tsx
import { FindIdView, FindPwView, MyPageView } from './views/_placeholders';
```
를 분리:
```tsx
import { MyPageView } from './views/_placeholders';
import { FindIdView } from './views/find_id';
import { FindPwView } from './views/find_pw';
```

- [ ] **Step 2: onDone 배선**

`App.tsx:55-56` 의
```tsx
        {authReady && !session && route === 'findId' && <FindIdView />}
        {authReady && !session && route === 'findPw' && <FindPwView />}
```
를 교체:
```tsx
        {authReady && !session && route === 'findId' && <FindIdView onDone={() => setRoute('login')} />}
        {authReady && !session && route === 'findPw' && <FindPwView onDone={() => setRoute('login')} />}
```

- [ ] **Step 3: 전체 테스트**

Run: `cd frontend; npx vitest run`
Expected: PASS — 기존 B1 16건 + Task3 신규 20건(client 12 + messages 8) = **36 passed**.

- [ ] **Step 4: 빌드**

Run: `cd frontend; npm run build`
Expected: 성공(타입에러·번들에러 없음).

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): App에 find_id/find_pw 실화면 배선(onDone→login)"
```

- [ ] **Step 6: 수동 육안 체크리스트 (선택, 라이브)**

`cd frontend; npm run dev` (또는 Electron 패키지) — fake Edge Function 배포 상태에서:
1. 가입: 아이디 중복확인 → 핸드폰 [인증요청] → (서버 로그의 코드 확인) → 코드 입력 [확인] → ✓ → 가입 완료.
2. 아이디 찾기: 꽃집명+핸드폰 → 인증 → "회원님의 아이디는 …".
3. 비번 재설정: 아이디+핸드폰 → 인증 → 새 비번 → 재설정 → 새 비번 로그인.
> 코드는 fake provider 가 Edge Function 로그로만 출력하므로 `mcp__supabase__get_logs`(edge-function)로 확인. 검증 후 `phone_verification` 스모크 행 정리.

---

## 완료 기준
- Vitest **36 passed**(B1 16 + 신규 20), `npm run build` 성공.
- DB: `phone_verification` 테이블 + RPC 4개 + `signup_member`(10인자) 라이브 적용·스모크·권한 검증 완료.
- Edge Function `send-otp` fake 모드 배포·수동 스모크 완료.
- 가입 폰 인증·아이디 찾기·비번 재설정 흐름 동작(수동 육안).

## 범위 경계 (B2b/이후)
- 마이페이지(프로필 조회·수정 + 재인증) → B2b.
- 실 SMS 발송(HttpSmsProvider 페이로드 완성 + 시크릿) → 제공사 계정 준비 시.
- C/D/E(대시보드·조회·설정 정교화) → 별도 서브프로젝트.
