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
-- 검증 먼저(아무것도 변경/소비 안 함) → 전부 통과 시 적용(토큰 소비 + 변경). 비번 오타로 OTP 안 버림.
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
  select * into v_auth from phone_verification
   where phone = v_cur and purpose = 'update_profile' and verified = true
     and token_hash is not null and token_expires_at > now()
   order by created_at desc limit 1;
  if not found or v_auth.token_hash <> crypt(p_auth_token, v_auth.token_hash) then
    return json_build_object('ok', false, 'reason', 'invalid_token');
  end if;

  if v_change_pw then
    if v_row.password is null or v_row.password <> crypt(coalesce(p_current_password,''), v_row.password) then
      return json_build_object('ok', false, 'reason', 'bad_password');
    end if;
  end if;

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
  update phone_verification set token_expires_at = now() where id = v_auth.id;
  if v_change_pw then
    update member_info set password = crypt(p_new_password, gen_salt('bf')) where id = v_row.id;
  end if;
  if v_change_phone then
    update phone_verification set token_expires_at = now() where id = v_np.id;
    update member_info set mobile_number = p_new_mobile where id = v_row.id;
  end if;

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
