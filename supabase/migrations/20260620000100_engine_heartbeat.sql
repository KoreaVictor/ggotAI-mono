-- 수집엔진 하트비트 + 상황판 '가동중' 표시(engine_alive)
-- 백엔드(orchestrator)가 engine_heartbeat.last_seen 을 주기적으로(20초) upsert 하고,
-- get_dashboard 가 최근 90초 내 신호면 engine_alive=true 로 반환한다.
-- 목적: Electron(데스크톱) 의존 없이 웹(브라우저)에서도 수집엔진 상태를 정확히 표시.
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

create table if not exists engine_heartbeat (
  shop_key  int primary key,
  last_seen timestamptz not null default now()
);

-- 상황판 전용 테이블: anon/authenticated 직접권한 회수.
-- (읽기는 get_dashboard=security definer 경로로만, 쓰기는 record_engine_heartbeat 로만.)
revoke all privileges on table engine_heartbeat from anon, authenticated, public;

-- 하트비트 기록 RPC. last_seen 을 반드시 DB 서버의 now() 로 찍는다
-- (백엔드 PC 시각을 쓰면 PC-서버 시계차로 상황판이 오판할 수 있음).
create or replace function record_engine_heartbeat(p_shop_key int)
returns void
language sql
security definer
set search_path = public
as $$
  insert into engine_heartbeat (shop_key, last_seen)
  values (p_shop_key, now())
  on conflict (shop_key) do update set last_seen = now();
$$;

revoke all on function record_engine_heartbeat(int) from anon, authenticated, public;
grant execute on function record_engine_heartbeat(int) to service_role;

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
  v_alive boolean;
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

  -- engine heartbeat: 최근 90초 내 신호면 가동중(없으면 false)
  select (now() - last_seen) < interval '90 seconds'
    into v_alive from engine_heartbeat where shop_key = p_shop_key;

  return json_build_object('ok', true, 'stats', v_stats, 'channels', v_channels, 'config', v_config, 'feed', v_feed,
                           'engine_alive', coalesce(v_alive, false));
end;
$$;

grant execute on function get_dashboard(int, text) to anon;
