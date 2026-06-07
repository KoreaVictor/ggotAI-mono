# ggotAIya B2b 마이페이지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 사용자가 자기 회원정보(아이디 제외)를 핸드폰 재인증 후 수정한다 — 프로필 필드 + 핸드폰 변경(새 폰 인증) + 비밀번호 변경(현재 비번 확인).

**Architecture:** B2a 자산 재사용 — 얇은 Edge Function `send-otp`(purpose 추가만) + 두꺼운 pgcrypto SECURITY DEFINER RPC(`get_profile`, `update_account`) + `PhoneVerify` 컴포넌트. 권한 게이트 = 현재 등록폰 OTP(계정 바인딩). `member_info` anon 직접권한을 회수해 모든 접근을 RPC로 일원화.

**Tech Stack:** Postgres(pgcrypto) RPC, Supabase Edge Function(Deno), React+Vite+TypeScript, Vitest. 라이브 적용=Management API(curl UA, PAT) + `npx supabase functions deploy`.

**설계서:** `docs/superpowers/specs/2026-06-07-ggotaiya-b2b-mypage-design.md`
**브랜치:** `feature/ggotaiya-b2b-mypage` (master `5d78085`에서 분기, 이미 생성됨)

## 파일 구조
- Create: `docs/migrations/2026-06-07-b2b-mypage.sql` — 마이그레이션(버전관리 기록 + 라이브 적용 원본)
- Modify: `supabase/functions/send-otp/index.ts` — `VALID_PURPOSES`에 `'update_profile'`
- Modify: `frontend/src/otp/client.ts` — `Purpose`에 `'update_profile'`
- Create: `frontend/src/profile/client.ts` + `frontend/src/profile/client.test.ts` — RPC 래퍼·메시지 매퍼(순수)
- Create: `frontend/src/views/mypage.tsx` — 마이페이지 화면
- Modify: `frontend/src/session/SessionContext.tsx` — `updateShopName` 노출
- Modify: `frontend/src/App.tsx` — MyPageView import 교체
- Delete: `frontend/src/views/_placeholders.tsx` — 마지막 소비처(MyPageView) 제거 후 고아

---

## Task 1: DB 마이그레이션 (purpose 추가 + get_profile + update_account + 하드닝) — 라이브, 컨트롤러 직접

> 이 Task는 Vitest 대상이 아니다. SQL을 파일로 기록하고 Management API로 적용한 뒤 라운드트립 스모크로 검증한다. **라이브 DB 변경이라 컨트롤러가 직접 적용한다(서브에이전트 위임 금지).** MCP Unauthorized 시 `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query` + `Authorization: Bearer <PAT>` + **User-Agent: curl**(B2a 전례).

**Files:**
- Create: `docs/migrations/2026-06-07-b2b-mypage.sql`

- [ ] **Step 1: 마이그레이션 SQL 파일 작성**

`docs/migrations/2026-06-07-b2b-mypage.sql`:
```sql
-- ggotAIya B2b: 마이페이지(회원정보 관리) — get_profile + update_account + purpose 'update_profile' + member_info 하드닝
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

-- ===== request_otp: purpose 'update_profile' 추가 (CREATE OR REPLACE, 본문 동일 + 목록만 확장) =====
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
  if p_purpose not in ('signup','find_id','find_pw','update_profile') then
    raise exception 'INVALID_PURPOSE';
  end if;
  select max(created_at) into v_recent
    from phone_verification where phone = v_phone and purpose = p_purpose;
  if v_recent is not null and v_recent > now() - interval '30 seconds' then
    raise exception 'RATE_LIMIT_THROTTLE';
  end if;
  select count(*) into v_hour_count
    from phone_verification
   where phone = v_phone and purpose = p_purpose
     and created_at > now() - interval '1 hour';
  if v_hour_count >= 5 then
    raise exception 'RATE_LIMIT_HOURLY';
  end if;
  delete from phone_verification where created_at < now() - interval '1 hour';
  v_code := lpad((floor(random()*1000000))::int::text, 6, '0');
  insert into phone_verification(phone, purpose, code_hash, expires_at)
  values (v_phone, p_purpose, crypt(v_code, gen_salt('bf')), now() + interval '3 minutes');
  return v_code;
end;
$$;
revoke execute on function request_otp(text,text) from public, anon, authenticated;
grant execute on function request_otp(text,text) to service_role;

-- ===== get_profile (anon) — 비민감 프로필 반환 =====
create or replace function get_profile(p_username text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare v_row member_info%rowtype;
begin
  select * into v_row from member_info where username = p_username limit 1;
  if not found then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  return json_build_object('ok', true, 'profile', json_build_object(
    'username', v_row.username,
    'shop_name', v_row.shop_name,
    'representative_name', v_row.representative_name,
    'landline_number', v_row.landline_number,
    'mobile_number', v_row.mobile_number,
    'email', v_row.email,
    'address', v_row.address,
    'address_detail', v_row.address_detail,
    'is_approved', v_row.is_approved));
end;
$$;

-- ===== update_account (anon) — 현재폰 OTP 권한 + 조건부 비번/핸드폰 변경 + 프로필 갱신 =====
create or replace function update_account(
  p_username text, p_auth_token text,
  p_shop_name text, p_representative_name text, p_landline text,
  p_email text, p_address text, p_address_detail text,
  p_new_mobile text, p_new_phone_token text,
  p_current_password text, p_new_password text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row     member_info%rowtype;
  v_cur     text;
  v_new     text := regexp_replace(coalesce(p_new_mobile,''), '\D', '', 'g');
  v_auth    phone_verification%rowtype;
  v_np      phone_verification%rowtype;
  v_change_pw    boolean := coalesce(p_new_password,'') <> '';
  v_change_phone boolean;
begin
  select * into v_row from member_info where username = p_username limit 1;
  if not found then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  v_cur := regexp_replace(coalesce(v_row.mobile_number,''), '\D', '', 'g');
  v_change_phone := v_new <> '' and v_new <> v_cur;

  -- ===== 검증 단계(아무것도 변경/소비하지 않음) =====
  -- 권한: 현재폰 OTP 토큰(계정 바인딩)
  select * into v_auth from phone_verification
   where phone = v_cur and purpose = 'update_profile' and verified = true
     and token_hash is not null and token_expires_at > now()
   order by created_at desc limit 1;
  if not found or v_auth.token_hash <> crypt(p_auth_token, v_auth.token_hash) then
    return json_build_object('ok', false, 'reason', 'invalid_token');
  end if;

  -- 비번 변경(요청 시): 현재 비번 확인
  if v_change_pw then
    if v_row.password is null or v_row.password <> crypt(coalesce(p_current_password,''), v_row.password) then
      return json_build_object('ok', false, 'reason', 'bad_password');
    end if;
  end if;

  -- 핸드폰 변경(새 번호가 있고 현재와 다를 때): 새 폰 OTP 소유 증명
  if v_change_phone then
    select * into v_np from phone_verification
     where phone = v_new and purpose = 'update_profile' and verified = true
       and token_hash is not null and token_expires_at > now()
     order by created_at desc limit 1;
    if not found or v_np.token_hash <> crypt(coalesce(p_new_phone_token,''), v_np.token_hash) then
      return json_build_object('ok', false, 'reason', 'new_phone_unverified');
    end if;
  end if;

  -- ===== 적용 단계(검증 전부 통과 → 토큰 소비 + 변경) =====
  update phone_verification set token_expires_at = now() where id = v_auth.id;  -- 권한 토큰 소비
  if v_change_pw then
    update member_info set password = crypt(p_new_password, gen_salt('bf')) where id = v_row.id;
  end if;
  if v_change_phone then
    update phone_verification set token_expires_at = now() where id = v_np.id;  -- 새폰 토큰 소비
    update member_info set mobile_number = p_new_mobile where id = v_row.id;
  end if;

  -- 프로필 필드 갱신(빈 선택값은 NULL)
  update member_info set
    shop_name           = p_shop_name,
    representative_name = p_representative_name,
    landline_number     = nullif(p_landline,''),
    email               = nullif(p_email,''),
    address             = nullif(p_address,''),
    address_detail      = nullif(p_address_detail,'')
   where id = v_row.id;

  select * into v_row from member_info where id = v_row.id;
  return json_build_object('ok', true, 'profile', json_build_object(
    'username', v_row.username,
    'shop_name', v_row.shop_name,
    'representative_name', v_row.representative_name,
    'landline_number', v_row.landline_number,
    'mobile_number', v_row.mobile_number,
    'email', v_row.email,
    'address', v_row.address,
    'address_detail', v_row.address_detail,
    'is_approved', v_row.is_approved));
end;
$$;

-- ===== 하드닝: member_info anon/authenticated 직접권한 회수 (모든 접근을 SECURITY DEFINER RPC 로) =====
revoke select, insert, update, delete, references
  on table member_info from anon, authenticated, public;

-- ===== 신규 RPC 권한 =====
grant execute on function get_profile(text) to anon;
grant execute on function update_account(text,text,text,text,text,text,text,text,text,text,text,text) to anon;
```

- [ ] **Step 2: 적용 전 스키마 확인 (컨트롤러)**

Run: 현재 `request_otp`/`signup_member` 등 SECURITY DEFINER 함수가 owner=postgres 인지, `member_info` 현재 anon grant 존재를 확인.
```sql
select has_table_privilege('anon','member_info','select') as before_anon_sel;  -- true 기대(회수 전)
```
Expected: `before_anon_sel=true` (회수 전이므로).

- [ ] **Step 3: 마이그레이션 적용 (컨트롤러 직접)**

Run: 위 SQL 전체를 Management API `database/query` 로 실행.
Expected: `[]` (에러 없음).

- [ ] **Step 4: 라운드트립 스모크 (컨트롤러 직접)**

Run: 아래 DO 블록 1회 실행(실패 시 예외 → 에러로 표면화, 성공 시 `[]`).

> 주의: `request_otp` 는 (phone,purpose) 별 30초 쓰로틀이 있어 같은 폰에 연속 호출이 막힌다. 스모크는 superuser 로 실행되므로 **검증된 `phone_verification` 행을 알려진 토큰으로 직접 시드**해 `update_account` 로직만 검증한다(request_otp/verify_otp 의 update_profile 동작은 Task 2 EF 스모크 + B2a 에서 커버).
> ⚠️ 각 시드 insert 에 `created_at = clock_timestamp()` 를 명시한다. DO 블록 단일 트랜잭션에서 `now()`(=created_at 기본값)는 고정값이라 미소비 잔여 토큰과 새 토큰의 `created_at` 이 같아져 `order by created_at desc` 가 엉뚱한 토큰을 골라 `invalid_token` 오탐이 난다. `clock_timestamp()` 는 트랜잭션 내에서 증가하므로 최신 시드가 확정적으로 선택된다.

```sql
do $$
declare
  v_id bigint; r json; login json;
  PH  text := '01077770001';
  PH2 text := '01077770002';
  PHX text := '01099999999';
begin
  insert into member_info(username,password,shop_name,representative_name,mobile_number,is_approved)
  values('b2bsmoke', crypt('pw_old_1', gen_salt('bf')), '스모크B','대표', PH, 'Y') returning id into v_id;

  -- 1) get_profile
  r := get_profile('b2bsmoke');
  if (r#>>'{profile,shop_name}') <> '스모크B' then raise exception 'GP: %', r; end if;

  -- 2) 프로필만 수정 (PH 권한 토큰 TKA1 시드)
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKA1',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKA1','새가게','새대표','02-1','e@e.com','서울','101', null,null, null,null);
  if (r#>>'{profile,shop_name}') <> '새가게' then raise exception 'UA profile: %', r; end if;

  -- 3) 비번 변경 (현재 비번 pw_old_1 → pw_new_2)
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKA2',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKA2','새가게','새대표','02-1','e@e.com','서울','101', null,null, 'pw_old_1','pw_new_2');
  if (r->>'ok')::boolean is not true then raise exception 'UA pwchange: %', r; end if;
  login := verify_login('b2bsmoke','pw_new_2');
  if (login->>'username') <> 'b2bsmoke' then raise exception 'verify_login after pw: %', login; end if;

  -- 4) 틀린 현재 비번 → bad_password (토큰 미소비)
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKA3',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKA3','새가게','새대표','02-1','e@e.com','서울','101', null,null, 'WRONG','pw_x');
  if (r->>'reason') <> 'bad_password' then raise exception 'UA badpw: %', r; end if;

  -- 5) 핸드폰 변경: 새폰 토큰 없음 → new_phone_unverified
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKA4',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKA4','새가게','새대표','02-1','e@e.com','서울','101', PH2, null, null,null);
  if (r->>'reason') <> 'new_phone_unverified' then raise exception 'UA newphone missing: %', r; end if;

  -- 6) 핸드폰 변경 정상(PH 권한 TKA5 + PH2 소유 TKB1)
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKA5',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PH2,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKB1',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKA5','새가게','새대표','02-1','e@e.com','서울','101', PH2, 'TKB1', null,null);
  if (r#>>'{profile,mobile_number}') <> PH2 then raise exception 'UA phonechange: %', r; end if;

  -- 7) 타계정 토큰(다른 폰 PHX) → invalid_token (현재폰은 이제 PH2; PHX 토큰은 권한 조회에서 제외됨)
  insert into phone_verification(phone,purpose,code_hash,expires_at,verified,token_hash,token_expires_at,created_at)
  values (PHX,'update_profile',crypt('c',gen_salt('bf')),now()+interval '3 min',true,crypt('TKX1',gen_salt('bf')),now()+interval '10 min',clock_timestamp());
  r := update_account('b2bsmoke','TKX1','x','y',null,null,null,null, null,null, null,null);
  if (r->>'reason') <> 'invalid_token' then raise exception 'UA wrongacct: %', r; end if;

  -- 정리(필수)
  delete from member_info where username='b2bsmoke';
  delete from phone_verification where phone in (PH, PH2, PHX);
  raise notice 'B2B SMOKE ALL PASSED';
end $$;
```
Expected: `[]`. 어떤 단언이라도 실패하면 에러 JSON 반환.

- [ ] **Step 5: 권한 검증 (컨트롤러 직접)**

> ⚠️ `has_table_privilege('anon','member_info','select')` 는 회수 전에도 `false` 다 — 기존 권한이 **컬럼 레벨** grant 라서 테이블 레벨 검사로는 구멍이 안 잡힌다. 반드시 `information_schema.column_privileges` 의 anon/authenticated 행 수가 0 인지로 검증한다. (테이블 레벨 revoke 가 컬럼 grant 까지 정리함 — 실측 확인.)
```sql
select (select count(*) from information_schema.column_privileges
          where table_name='member_info' and grantee in ('anon','authenticated')) as anon_cols,  -- 0 기대
       has_function_privilege('anon','get_profile(text)','execute') as anon_gp,  -- true
       has_function_privilege('anon','update_account(text,text,text,text,text,text,text,text,text,text,text,text)','execute') as anon_ua,  -- true
       has_function_privilege('anon','verify_login(text,text)','execute') as anon_vl,  -- true(기존 RPC 동작)
       (select count(*) from member_info where username='b2bsmoke') as leftover;  -- 0
```
Expected: `anon_cols=0, anon_gp=true, anon_ua=true, anon_vl=true, leftover=0`.

- [ ] **Step 6: 마이그레이션 SQL 파일 커밋**

```bash
git add docs/migrations/2026-06-07-b2b-mypage.sql
git commit -m "feat(db): B2b 마이페이지 마이그레이션(get_profile/update_account + member_info 하드닝)"
```

---

## Task 2: Edge Function purpose 확장 + 프론트 Purpose 타입 + 재배포

**Files:**
- Modify: `supabase/functions/send-otp/index.ts`
- Modify: `frontend/src/otp/client.ts`

- [ ] **Step 1: EF VALID_PURPOSES 확장**

`supabase/functions/send-otp/index.ts` 5번째 줄:
```ts
const VALID_PURPOSES = ['signup', 'find_id', 'find_pw'];
```
→
```ts
const VALID_PURPOSES = ['signup', 'find_id', 'find_pw', 'update_profile'];
```

- [ ] **Step 2: 프론트 Purpose 타입 확장**

`frontend/src/otp/client.ts` 1번째 줄:
```ts
export type Purpose = 'signup' | 'find_id' | 'find_pw';
```
→
```ts
export type Purpose = 'signup' | 'find_id' | 'find_pw' | 'update_profile';
```

- [ ] **Step 3: 기존 테스트 통과 확인(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 기존 35 passed 유지(타입 확장은 런타임 무영향).

- [ ] **Step 4: EF 재배포 (라이브, 컨트롤러 직접)**

Run: `SUPABASE_ACCESS_TOKEN=<PAT> npx supabase functions deploy send-otp --project-ref suylrznbctrkbxbleapb --no-verify-jwt`
Expected: 배포 성공, send-otp ACTIVE. (Docker 경고는 무시 — API 번들러 사용.)

- [ ] **Step 5: EF 스모크 (라이브, 컨트롤러 직접)**

Run: `update_profile` purpose 로 curl(인증 없이, no-verify-jwt).
```bash
curl -s -w " HTTP %{http_code}\n" -X POST "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/send-otp" \
  -H "Content-Type: application/json" -d '{"phone":"010-7777-0009","purpose":"update_profile"}'
```
Expected: `{"success":true} HTTP 200`. 이후 `delete from phone_verification where phone='01077770009';` 정리.

- [ ] **Step 6: 커밋**

```bash
git add supabase/functions/send-otp/index.ts frontend/src/otp/client.ts
git commit -m "feat(edge,frontend): send-otp update_profile purpose 추가"
```

---

## Task 3: profile/client.ts (RPC 래퍼 + 메시지 매퍼) — TDD

**Files:**
- Create: `frontend/src/profile/client.ts`
- Test: `frontend/src/profile/client.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/profile/client.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { getProfile, updateAccount, profileMessage, type ProfileRpc } from './client';

function fakeRpc(data: unknown, error: unknown = null): ProfileRpc {
  return (async () => ({ data, error })) as ProfileRpc;
}

const PROFILE = {
  username: 'seoul', shop_name: '서울꽃집', representative_name: '홍길동',
  landline_number: null, mobile_number: '01011112222', email: null,
  address: null, address_detail: null, is_approved: 'Y',
};

describe('getProfile', () => {
  it('성공이면 profile 반환', async () => {
    const r = await getProfile(fakeRpc({ ok: true, profile: PROFILE }), 'seoul');
    expect(r).toEqual({ ok: true, profile: PROFILE });
  });
  it('없음이면 not_found', async () => {
    const r = await getProfile(fakeRpc({ ok: false, reason: 'not_found' }), 'x');
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getProfile(fakeRpc(null, { message: 'boom' }), 'x');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('updateAccount', () => {
  const base = {
    username: 'seoul', authToken: 'tk', shopName: '새', representativeName: '대표',
    landline: '', email: '', address: '', addressDetail: '',
  };
  it('성공이면 profile 반환', async () => {
    const r = await updateAccount(fakeRpc({ ok: true, profile: PROFILE }), base);
    expect(r).toEqual({ ok: true, profile: PROFILE });
  });
  it('reason 전달(bad_password)', async () => {
    const r = await updateAccount(fakeRpc({ ok: false, reason: 'bad_password' }), base);
    expect(r).toEqual({ ok: false, reason: 'bad_password' });
  });
  it('RPC 에러면 error', async () => {
    const r = await updateAccount(fakeRpc(null, { message: 'boom' }), base);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('profileMessage', () => {
  it('reason 별 한글 매핑', () => {
    expect(profileMessage('bad_password')).toBe('현재 비밀번호가 올바르지 않습니다');
    expect(profileMessage('new_phone_unverified')).toBe('새 핸드폰 인증을 완료해주세요');
    expect(profileMessage('invalid_token')).toBe('인증이 만료되었습니다. 다시 인증해주세요');
    expect(profileMessage('not_found')).toBe('회원 정보를 찾을 수 없습니다');
    expect(profileMessage(undefined)).toBe('저장 중 오류가 발생했습니다. 다시 시도해주세요');
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm run test -- --run profile/client`
Expected: FAIL ("Cannot find module './client'").

- [ ] **Step 3: 구현**

`frontend/src/profile/client.ts`:
```ts
// supabase.rpc 와 호환되는 최소 계약(테스트 주입용)
export type ProfileRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;

export interface Profile {
  username: string;
  shop_name: string;
  representative_name: string;
  landline_number: string | null;
  mobile_number: string | null;
  email: string | null;
  address: string | null;
  address_detail: string | null;
  is_approved: string;
}

export interface UpdatePayload {
  username: string;
  authToken: string;
  shopName: string;
  representativeName: string;
  landline: string;
  email: string;
  address: string;
  addressDetail: string;
  newMobile?: string;
  newPhoneToken?: string;
  currentPassword?: string;
  newPassword?: string;
}

type Result = { ok: boolean; profile?: Profile; reason?: string };

export async function getProfile(rpc: ProfileRpc, username: string): Promise<Result> {
  const { data, error } = await rpc('get_profile', { p_username: username });
  if (error) return { ok: false, reason: 'error' };
  return (data as Result | null) ?? { ok: false, reason: 'error' };
}

export async function updateAccount(rpc: ProfileRpc, p: UpdatePayload): Promise<Result> {
  const { data, error } = await rpc('update_account', {
    p_username: p.username,
    p_auth_token: p.authToken,
    p_shop_name: p.shopName,
    p_representative_name: p.representativeName,
    p_landline: p.landline,
    p_email: p.email,
    p_address: p.address,
    p_address_detail: p.addressDetail,
    p_new_mobile: p.newMobile ?? null,
    p_new_phone_token: p.newPhoneToken ?? null,
    p_current_password: p.currentPassword ?? null,
    p_new_password: p.newPassword ?? null,
  });
  if (error) return { ok: false, reason: 'error' };
  return (data as Result | null) ?? { ok: false, reason: 'error' };
}

export function profileMessage(reason: string | undefined): string {
  switch (reason) {
    case 'invalid_token':       return '인증이 만료되었습니다. 다시 인증해주세요';
    case 'bad_password':        return '현재 비밀번호가 올바르지 않습니다';
    case 'new_phone_unverified': return '새 핸드폰 인증을 완료해주세요';
    case 'not_found':           return '회원 정보를 찾을 수 없습니다';
    default:                    return '저장 중 오류가 발생했습니다. 다시 시도해주세요';
  }
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm run test -- --run profile/client`
Expected: PASS (신규 케이스 전부).

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/profile/client.ts frontend/src/profile/client.test.ts
git commit -m "feat(frontend): profile RPC 래퍼 + 메시지 매퍼 (+test)"
```

---

## Task 4: MyPageView 화면 + SessionContext setter

**Files:**
- Modify: `frontend/src/session/SessionContext.tsx`
- Create: `frontend/src/views/mypage.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/views/_placeholders.tsx`

- [ ] **Step 1: SessionContext 에 updateShopName 추가**

`frontend/src/session/SessionContext.tsx` — `SessionContextValue` 인터페이스에 추가:
```ts
interface SessionContextValue {
  session: Session | null;
  authReady: boolean;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<AuthResult>;
  logout: () => void;
  updateShopName: (name: string) => void;
}
```
Provider 본문에 콜백 추가(`logout` 정의 아래):
```ts
  const updateShopName = useCallback((name: string) => {
    setSession((s) => (s ? { ...s, shopName: name } : s));
  }, []);
```
Provider value 에 포함:
```ts
    <SessionContext.Provider value={{ session, authReady, login, logout, updateShopName }}>
```

- [ ] **Step 2: mypage.tsx 작성**

`frontend/src/views/mypage.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { PhoneVerify } from '../components/PhoneVerify';
import { getProfile, updateAccount, profileMessage, type ProfileRpc } from '../profile/client';
import { openPostcodeSearch } from '../utils/daumPostcode';

const rpc: ProfileRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<ProfileRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary disabled:opacity-60';

export function MyPageView() {
  const { session, updateShopName } = useSession();
  const username = session?.username ?? '';

  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState('');
  const [authToken, setAuthToken] = useState<string | null>(null);

  const [shopName, setShopName] = useState('');
  const [repName, setRepName] = useState('');
  const [landline, setLandline] = useState('');
  const [email, setEmail] = useState('');
  const [address, setAddress] = useState('');
  const [addressDetail, setAddressDetail] = useState('');
  const [curMobile, setCurMobile] = useState('');

  const [changingPhone, setChangingPhone] = useState(false);
  const [newMobile, setNewMobile] = useState('');
  const [newPhoneToken, setNewPhoneToken] = useState<string | null>(null);

  const [changingPw, setChangingPw] = useState(false);
  const [curPw, setCurPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      const r = await getProfile(rpc, username);
      if (!active) return;
      if (!r.ok || !r.profile) { setLoadErr('회원 정보를 불러오지 못했습니다'); setLoading(false); return; }
      const p = r.profile;
      setShopName(p.shop_name ?? ''); setRepName(p.representative_name ?? '');
      setLandline(p.landline_number ?? ''); setEmail(p.email ?? '');
      setAddress(p.address ?? ''); setAddressDetail(p.address_detail ?? '');
      setCurMobile(p.mobile_number ?? '');
      setLoading(false);
    })();
    return () => { active = false; };
  }, [username]);

  const findAddr = async () => {
    try { const r = await openPostcodeSearch(); setAddress(r.address); }
    catch { setError('주소찾기를 열 수 없습니다. 직접 입력해주세요.'); }
  };

  const save = async () => {
    setError(''); setDone('');
    if (!authToken) { setError('핸드폰 인증을 먼저 완료해주세요'); return; }
    if (changingPw) {
      if (!curPw) { setError('현재 비밀번호를 입력해주세요'); return; }
      if (!newPw) { setError('새 비밀번호를 입력해주세요'); return; }
      if (newPw !== newPw2) { setError('새 비밀번호가 일치하지 않습니다'); return; }
    }
    if (changingPhone && !newPhoneToken) { setError('새 핸드폰 인증을 완료해주세요'); return; }
    setBusy(true);
    const r = await updateAccount(rpc, {
      username, authToken,
      shopName, representativeName: repName, landline, email, address, addressDetail,
      newMobile: changingPhone ? newMobile : undefined,
      newPhoneToken: changingPhone ? (newPhoneToken ?? undefined) : undefined,
      currentPassword: changingPw ? curPw : undefined,
      newPassword: changingPw ? newPw : undefined,
    });
    setBusy(false);
    if (!r.ok) {
      setError(profileMessage(r.reason));
      // update_account 는 검증 통과 후에만 토큰을 소비 → 검증 실패(bad_password/new_phone_unverified)면
      // 권한 토큰은 아직 유효하므로 유지. invalid_token(만료/무효)일 때만 재인증 강제.
      if (r.reason === 'invalid_token') setAuthToken(null);
      return;
    }
    updateShopName(r.profile?.shop_name ?? shopName);
    if (changingPhone && r.profile?.mobile_number) {
      setCurMobile(r.profile.mobile_number); setChangingPhone(false); setNewMobile(''); setNewPhoneToken(null);
    }
    if (changingPw) { setChangingPw(false); setCurPw(''); setNewPw(''); setNewPw2(''); }
    setAuthToken(null); // 토큰 단일사용 소비 → 재인증 필요
    setDone('수정되었습니다');
  };

  if (loading) return <div className="flex-1 flex items-center justify-center text-brand-text-muted text-sm">불러오는 중…</div>;
  if (loadErr) return <div className="flex-1 flex items-center justify-center text-brand-error text-sm">{loadErr}</div>;

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">마이페이지</div>

        <input value={username} disabled className={INPUT} />
        <input value={shopName} onChange={(e) => setShopName(e.target.value)} placeholder="꽃집명" className={INPUT} />
        <input value={repName} onChange={(e) => setRepName(e.target.value)} placeholder="대표자명" className={INPUT} />
        <input value={landline} onChange={(e) => setLandline(e.target.value)} placeholder="전화(선택)" className={INPUT} />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="이메일(선택)" className={INPUT} />
        <div className="flex gap-2">
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="주소" className={INPUT} />
          <button type="button" onClick={findAddr} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">주소찾기</button>
        </div>
        <input value={addressDetail} onChange={(e) => setAddressDetail(e.target.value)} placeholder="상세주소(선택)" className={INPUT} />

        <div className="pt-1 text-xs text-brand-text-muted">등록된 핸드폰: {curMobile || '-'}</div>
        {!authToken
          ? <PhoneVerify phone={curMobile} purpose="update_profile" onVerified={setAuthToken} />
          : <div className="text-xs text-brand-success">✓ 본인 인증됨</div>}

        <label className="flex items-center gap-2 text-xs text-brand-text-secondary pt-1">
          <input type="checkbox" checked={changingPhone} onChange={(e) => { setChangingPhone(e.target.checked); setNewPhoneToken(null); setNewMobile(''); }} />
          핸드폰 번호 변경
        </label>
        {changingPhone && (
          <>
            <input value={newMobile} onChange={(e) => setNewMobile(e.target.value)} placeholder="새 핸드폰" disabled={!!newPhoneToken} className={INPUT} />
            {!newPhoneToken
              ? <PhoneVerify phone={newMobile} purpose="update_profile" onVerified={setNewPhoneToken} />
              : <div className="text-xs text-brand-success">✓ 새 핸드폰 인증됨</div>}
          </>
        )}

        <label className="flex items-center gap-2 text-xs text-brand-text-secondary pt-1">
          <input type="checkbox" checked={changingPw} onChange={(e) => setChangingPw(e.target.checked)} />
          비밀번호 변경
        </label>
        {changingPw && (
          <>
            <input value={curPw} onChange={(e) => setCurPw(e.target.value)} type="password" placeholder="현재 비밀번호" className={INPUT} />
            <input value={newPw} onChange={(e) => setNewPw(e.target.value)} type="password" placeholder="새 비밀번호" className={INPUT} />
            <input value={newPw2} onChange={(e) => setNewPw2(e.target.value)} type="password" placeholder="새 비밀번호 확인" className={INPUT} />
          </>
        )}

        {error && <div className="text-brand-error text-xs">{error}</div>}
        {done && <div className="text-brand-success text-xs">{done}</div>}
        <button type="button" onClick={save} disabled={busy || !authToken} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 disabled:opacity-50">
          {busy ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: App.tsx import 교체 + _placeholders 삭제**

`frontend/src/App.tsx` 6번째 줄:
```ts
import { MyPageView } from './views/_placeholders';
```
→
```ts
import { MyPageView } from './views/mypage';
```
그리고 `frontend/src/views/_placeholders.tsx` 삭제(다른 소비처 없음 — `grep -rn _placeholders frontend/src` 가 App.tsx 한 줄뿐이었음).

```bash
git rm frontend/src/views/_placeholders.tsx
```

- [ ] **Step 4: 빌드 + 타입 체크**

Run: `cd frontend && npm run build`
Expected: 성공(타입 에러 없음). `MyPageView` 가 mypage.tsx 에서 export, `updateShopName` 가 SessionContext 에 존재.

- [ ] **Step 5: 전체 테스트(회귀)**

Run: `cd frontend && npm run test -- --run`
Expected: 기존 35 + profile/client 신규 통과(전부 PASS).

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/views/mypage.tsx frontend/src/session/SessionContext.tsx frontend/src/App.tsx
git rm frontend/src/views/_placeholders.tsx
git commit -m "feat(frontend): 마이페이지(MyPageView) — 프로필/핸드폰/비번 수정 + 세션 shop_name 갱신"
```

---

## Task 5: 전체 검증 + 라이브 UI E2E + 브랜치 마무리

> Task 1·2 에서 마이그레이션·EF 는 이미 라이브 적용됨. 이 Task 는 프론트 빌드/테스트 최종 + 실제 UI E2E(컨트롤러 직접) + finishing-a-development-branch.

**Files:** (검증 전용, 영구 코드 변경 없음 — E2E 스크립트는 일회성)

- [ ] **Step 1: 프론트 테스트 + 빌드 최종 확인**

Run: `cd frontend && npm run test -- --run` → 전부 PASS. `npm run build` → 성공.

- [ ] **Step 2: UI E2E (Playwright Node판, 컨트롤러 직접)**

> Python Playwright 는 이 머신에서 greenlet/MSVC DLL 로드 실패 → **Node판 사용**(`npm i --no-save playwright` + `npx playwright install chromium`). B2a 전례.

먼저 마이페이지 진입을 위해 **승인된 로그인 계정**이 필요하다(login 은 `is_approved='Y'` 요구). E2E 스크립트가 직접 시드: signup_member 경로 또는 SQL insert(crypt 비번, is_approved='Y'). 흐름:
1. 시드 회원(승인) 생성(현재폰 PH, 비번 known).
2. dev 서버 기동 → 로그인(아이디/비번) → 헤더 [마이페이지] 클릭(또는 route 전환).
3. 프로필 필드 수정 → 현재폰 PhoneVerify(코드는 `function_logs`에서 추출, 직전 소비 코드의 서버 timestamp보다 새 것만) → [저장] → "수정되었습니다".
4. 비번 변경 토글 → 현재 비번 + 새 비번 → 현재폰 재인증 → [저장] → `verify_login` 새 비번 성공(API 교차확인).
5. 핸드폰 변경 토글 → 새 폰 입력 → 현재폰 인증 + 새 폰 인증 → [저장] → `get_profile` mobile 갱신 확인.
6. 시드/스모크 데이터 정리(member_info + phone_verification).

Expected: 각 단계 PASS, 정리 후 leftover 0.

- [ ] **Step 3: 메모리 갱신**

`project-ggotaiorder.md` 와 `MEMORY.md` 의 '현재 재개 지점' 을 B2b 완료로 갱신(머지 커밋·다음 후보 C/D/E).

- [ ] **Step 4: finishing-a-development-branch**

REQUIRED: `superpowers:finishing-a-development-branch` 스킬로 — 테스트 검증 → 옵션 제시(머지/PR) → 사용자 선택 실행. PR 본문에 라이브 적용·스모크·권한검증·UI E2E 결과 기재. 머지 후 origin 정리.

---

## 완료 기준 (Definition of Done)
- DB: `get_profile`/`update_account` 라이브 적용·스모크·권한 검증 완료. `member_info` anon 직접권한 회수됨(`has_table_privilege` false). `request_otp` purpose 'update_profile' 추가.
- EF `send-otp` 재배포(update_profile purpose 인식).
- 프론트: `profile/client`(+test), `views/mypage.tsx`, `SessionContext.updateShopName`, `_placeholders.tsx` 제거. 테스트 전부 PASS·빌드 성공.
- UI E2E: 프로필/핸드폰/비번 수정 전체 흐름 실제 검증.
- 브랜치 머지(또는 PR) 완료.
```
