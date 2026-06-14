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
    where sch.shop_key = p_shop_key and sch.created_at >= v_today  -- 오늘 경계: 현재작업/피드는 금일 활동만
    order by sch.created_at desc
    limit 8
  ) f;

  return json_build_object('ok', true, 'stats', v_stats, 'channels', v_channels, 'config', v_config, 'feed', v_feed);
end;
$$;

grant execute on function get_dashboard(int, text) to anon;

-- 하드닝: server_call_history anon/authenticated 직접권한 회수(대시보드 전용 테이블; get_dashboard=owner 실행)
revoke all privileges on table server_call_history from anon, authenticated, public;
