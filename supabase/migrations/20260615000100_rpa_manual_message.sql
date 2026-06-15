-- 2026-06-15 RPA 3-state 알림: '백업 생성(수동입력 필요)' 문구 신설.
-- 기존엔 자동입력 실패(fail)만 있어, 관리 프로그램 미구동 시에도 '입력 실패'
-- 문자가 나갔다. manual(수동입력 필요) 문구를 분리해 정상 접수와 진짜 실패를 구분한다.

-- 1) setting_info 에 수동입력 안내 문구 컬럼 추가(기본값 포함 → 기존 행도 즉시 채움)
alter table setting_info
  add column if not exists rpa_manual_message text
  default '[ggotAI] {channel} 주문 {count}건 접수 — 관리 프로그램에 직접 입력해 주세요.';

-- 2) 설정 조회 RPC: rpa_manual_message 포함하여 반환
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
    'has_intranet_password', coalesce(v_set.intranet_password,'') <> ''
  ));
end;
$$;

-- 3) 설정 저장 RPC: rpa_manual_message 도 저장(미전달 시 기존값 보존)
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
    intranet_password      = coalesce(p_intranet_password, intranet_password)
  where shop_key = p_shop_key;
  get diagnostics v_count = row_count;

  if v_count = 0 then
    insert into setting_info(
      shop_key, use_notification, notification_phone_number,
      rpa_success_message, rpa_manual_message, rpa_fail_message,
      order_hp_1, order_hp_2, order_landline_1, order_landline_2,
      shopping_mall_url, shopping_mall_id, shopping_mall_password,
      intranet_url, intranet_id, intranet_password,
      shopping_mall_check_interval, intranet_check_interval)
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
      coalesce((p_settings->>'intranet_check_interval')::int, 30));
  end if;

  return json_build_object('ok', true);
end;
$$;

grant execute on function get_settings(int, text) to anon;
grant execute on function save_settings(int, text, jsonb, text, text) to anon;
