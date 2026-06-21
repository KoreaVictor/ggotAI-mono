-- 2026-06-18 RPA 멀티 프로그램: 꽃집별 관리 프로그램 자동입력 설정.
-- setting_info 에 프로그램 종류/주소/계정 추가. 비밀번호는 암호화(iv:ct) 저장하며
-- get_settings 는 평문 대신 has_rpa_login_password 불리언만 노출한다.

alter table setting_info
  add column if not exists rpa_program_type varchar(20) default '',
  add column if not exists rpa_program_url  text,
  add column if not exists rpa_login_id     varchar(100),
  add column if not exists rpa_login_password text,
  add column if not exists rpa_enabled      varchar(1) default 'N',
  add column if not exists rpa_auto_submit  varchar(1) default 'Y';

-- get_settings: RPA 필드 추가(비번은 has_ 불리언만)
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
    'rpa_manual_message', v_set.rpa_manual_message,
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
    'has_intranet_password', coalesce(v_set.intranet_password,'') <> '',
    'rpa_program_type', v_set.rpa_program_type,
    'rpa_program_url', v_set.rpa_program_url,
    'rpa_login_id', v_set.rpa_login_id,
    'rpa_enabled', v_set.rpa_enabled,
    'rpa_auto_submit', v_set.rpa_auto_submit,
    'has_rpa_login_password', coalesce(v_set.rpa_login_password,'') <> ''
  ));
end;
$$;

-- save_settings: rpa_login_password 별도 인자(미전달 시 기존값 보존), 나머지는 jsonb.
-- 기존 5인자 버전이 남아 오버로드 충돌이 나지 않도록 신규 6인자 버전만 유지한다.
drop function if exists save_settings(int, text, jsonb, text, text);

create or replace function save_settings(
  p_shop_key int,
  p_token    text,
  p_settings jsonb,
  p_shopping_mall_password text default null,
  p_intranet_password      text default null,
  p_rpa_login_password     text default null
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
    rpa_manual_message = coalesce(p_settings->>'rpa_manual_message', rpa_manual_message),
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
    intranet_password      = coalesce(p_intranet_password, intranet_password),
    rpa_program_type = coalesce(p_settings->>'rpa_program_type', rpa_program_type),
    rpa_program_url  = nullif(p_settings->>'rpa_program_url',''),
    rpa_login_id     = nullif(p_settings->>'rpa_login_id',''),
    rpa_enabled      = coalesce(p_settings->>'rpa_enabled', rpa_enabled),
    rpa_auto_submit  = coalesce(p_settings->>'rpa_auto_submit', rpa_auto_submit),
    rpa_login_password = coalesce(p_rpa_login_password, rpa_login_password)
  where shop_key = p_shop_key;
  get diagnostics v_count = row_count;

  if v_count = 0 then
    insert into setting_info(
      shop_key, use_notification, notification_phone_number,
      rpa_success_message, rpa_manual_message, rpa_fail_message,
      order_hp_1, order_hp_2, order_landline_1, order_landline_2,
      shopping_mall_url, shopping_mall_id, shopping_mall_password,
      intranet_url, intranet_id, intranet_password,
      shopping_mall_check_interval, intranet_check_interval,
      rpa_program_type, rpa_program_url, rpa_login_id, rpa_login_password,
      rpa_enabled, rpa_auto_submit)
    values(
      p_shop_key,
      coalesce(p_settings->>'use_notification','Y'),
      nullif(p_settings->>'notification_phone_number',''),
      p_settings->>'rpa_success_message',
      coalesce(p_settings->>'rpa_manual_message',
               '[ggotAI] {channel} 주문 {count}건 접수 — 관리 프로그램에 직접 입력해 주세요.'),
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
      coalesce((p_settings->>'intranet_check_interval')::int, 30),
      coalesce(p_settings->>'rpa_program_type',''),
      nullif(p_settings->>'rpa_program_url',''),
      nullif(p_settings->>'rpa_login_id',''),
      p_rpa_login_password,
      coalesce(p_settings->>'rpa_enabled','N'),
      coalesce(p_settings->>'rpa_auto_submit','Y'));
  end if;

  return json_build_object('ok', true);
end;
$$;

grant execute on function get_settings(int, text) to anon;
grant execute on function save_settings(int, text, jsonb, text, text, text) to anon;
