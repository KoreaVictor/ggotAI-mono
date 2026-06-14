-- ggotAIya B1: pgcrypto 인증 RPC + remember_token + 컬럼 권한 + 평문 해싱
-- (Supabase MCP apply_migration 으로 적용. 본 파일은 버전관리 기록용.)

-- ===== 마이그레이션 1: 스키마 + RPC + 권한 =====
create extension if not exists pgcrypto;

alter table member_info
  add column if not exists remember_token_hash       text,
  add column if not exists remember_token_expires_at timestamptz;

-- 아이디 중복확인
create or replace function check_username(p_username text)
returns boolean
language sql
security definer
set search_path = public, extensions
as $$
  select exists(select 1 from member_info where username = p_username);
$$;

-- 회원가입 (비번 bcrypt 해싱, 승인대기 N)
create or replace function signup_member(
  p_username text, p_password text, p_shop_name text,
  p_representative_name text, p_landline text, p_mobile text,
  p_email text, p_address text, p_address_detail text)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare v_id bigint;
begin
  if exists(select 1 from member_info where username = p_username) then
    raise exception 'USERNAME_TAKEN';
  end if;
  insert into member_info(username, password, shop_name, representative_name,
    landline_number, mobile_number, email, address, address_detail, is_approved)
  values(p_username, crypt(p_password, gen_salt('bf')), p_shop_name,
    p_representative_name, p_landline, p_mobile, p_email, p_address,
    p_address_detail, 'N')
  returning id into v_id;
  return json_build_object('id', v_id, 'is_approved', 'N');
end;
$$;

-- 로그인 검증 (비번 자체는 반환 안 함)
create or replace function verify_login(p_username text, p_password text)
returns json
language sql
security definer
set search_path = public, extensions
as $$
  select json_build_object('id', id, 'shop_name', shop_name,
                           'username', username, 'is_approved', is_approved)
  from member_info
  where username = p_username
    and password = crypt(p_password, password::text);
$$;

-- remember_token 발급 (해시 저장, 30일 만료, 평문 반환)
create or replace function issue_remember_token(p_user_id bigint)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare v_token text;
begin
  v_token := encode(gen_random_bytes(32), 'hex');
  update member_info
     set remember_token_hash = crypt(v_token, gen_salt('bf')),
         remember_token_expires_at = now() + interval '30 days'
   where id = p_user_id;
  return v_token;
end;
$$;

-- remember_token 검증 (세션 반환 또는 null)
create or replace function verify_remember_token(p_user_id bigint, p_token text)
returns json
language sql
security definer
set search_path = public, extensions
as $$
  select json_build_object('id', id, 'shop_name', shop_name, 'username', username)
  from member_info
  where id = p_user_id
    and remember_token_hash is not null
    and remember_token_expires_at > now()
    and remember_token_hash = crypt(p_token, remember_token_hash);
$$;

-- remember_token 정리 (로그아웃)
create or replace function clear_remember_token(p_user_id bigint)
returns void
language sql
security definer
set search_path = public, extensions
as $$
  update member_info
     set remember_token_hash = null, remember_token_expires_at = null
   where id = p_user_id;
$$;

-- 컬럼 권한: anon/authenticated 의 password/remember_token_* 직접 SELECT 차단
revoke select on member_info from anon;
grant select (id, username, shop_name, representative_name,
              landline_number, mobile_number, email, address,
              address_detail, is_approved, created_at) on member_info to anon;
revoke select on member_info from authenticated;
grant select (id, username, shop_name, representative_name,
              landline_number, mobile_number, email, address,
              address_detail, is_approved, created_at) on member_info to authenticated;
grant execute on function check_username(text), signup_member(text,text,text,text,text,text,text,text,text),
  verify_login(text,text), issue_remember_token(bigint),
  verify_remember_token(bigint,text), clear_remember_token(bigint) to anon;

-- ===== 마이그레이션 2: 기존 평문 비번 해싱 (멱등 가드) =====
update member_info
   set password = crypt(password::text, gen_salt('bf'))
 where password is not null
   and password not like '$2%';
