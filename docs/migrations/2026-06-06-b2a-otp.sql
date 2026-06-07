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
-- ⚠️ Supabase는 ALTER DEFAULT PRIVILEGES로 신규 함수에 anon/authenticated EXECUTE를
--    자동 부여하므로 from public 만으로는 부족 — anon/authenticated 명시적 revoke 필수.
revoke execute on function request_otp(text,text) from public, anon, authenticated;
grant execute on function request_otp(text,text) to service_role;
-- 나머지: anon
grant execute on function
  verify_otp(text,text,text),
  find_username(text,text,text),
  reset_password(text,text,text,text),
  signup_member(text,text,text,text,text,text,text,text,text,text)
  to anon;
