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
