-- 2026-07-21 카톡·문자 주문 채널 추가.
--
-- 텍스트 주문은 손님이 안 적으면 배송일·받는분이 빈 채로 들어온다. FlowerNT 는 그 상태로
-- 등록이 안 되므로 rpa_status='hold' 로 보류하고, 사장님이 ggotAIya 에서 채운 뒤
-- 자동입력한다. 이 마이그레이션은 그 보류 상태와 보완 저장 경로를 만든다.

-- 1) 허용값 문서화 (CHECK 제약이 없어 주석이 유일한 계약 — 코드와 어긋나지 않게 갱신).
comment on column server_call_history.channel_order is
  '''핸드폰'',''가게전화'',''쇼핑몰'',''인터라넷'',''가게음성'',''카톡'',''문자'',''기타''';
comment on column order_details.rpa_status is
  '''ready'',''success'',''manual''(미구동→백업), ''fail'', ''hold''(필수값 누락 — 사장님 보완 대기)';

-- 2) 텍스트 채널 중복 적재 방지.
-- 기존 uq_server_call_history_call 은 WHERE audio_file_name IS NOT NULL 조건이라
-- 오디오가 없는 텍스트 주문에는 걸리지 않는다. 같은 범위의 인덱스를 따로 만든다.
-- 카톡은 발신번호를 알 수 없어(알림이 표시명만 준다) customer_phone_number 가 ''
-- 로 동일해지므로, 서로 다른 발신자가 같은 초에 묶여도 충돌하지 않도록
-- customer_name(발신자 표시명)을 키에 포함한다.
create unique index if not exists uq_server_call_history_text
    on public.server_call_history
       (shop_key, customer_phone_number, customer_name, call_date, call_time)
    nulls not distinct
    where channel_order in ('카톡', '문자');

-- 3) 보류 안내 문구 (rpa_manual_message 선례와 동일한 방식).
alter table setting_info
  add column if not exists rpa_hold_message text
    default '[ggotAI] {channel} 주문 {count}건 확인 필요 — ggotAIya에서 내용을 채워주세요.';

update setting_info
   set rpa_hold_message = '[ggotAI] {channel} 주문 {count}건 확인 필요 — ggotAIya에서 내용을 채워주세요.'
 where rpa_hold_message is null;

-- 4) 대시보드에 보류 건수 추가 (20260620000100 판을 기준으로 stats 한 줄만 확장).
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
    'rpa_ready',   (select count(*) from order_details where shop_key = p_shop_key and created_at >= v_today and rpa_status = 'ready'),
    -- 보류는 사장님이 손대야 넘어가므로 오늘 경계와 무관하게 미처리 전량을 센다.
    'rpa_hold',    (select count(*) from order_details where shop_key = p_shop_key and rpa_status = 'hold')
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
    where sch.shop_key = p_shop_key and sch.created_at >= v_today
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

-- 5) 보류 주문 보완 저장 → 자동입력 대기로 전환.
-- requeue_order 와 같은 샵스코핑 방식이되, 필드를 채운 뒤 상태를 바꾼다.
-- null 인 인자는 '변경 없음'으로 둔다(부분 수정 허용).
create or replace function complete_hold_order(
  p_shop_key              int,
  p_token                 text,
  p_order_id              bigint,
  p_product_name          text default null,
  p_price                 int  default null,
  p_quantity              int  default null,
  p_delivery_at           timestamptz default null,
  p_delivery_place        text default null,
  p_receiver_name         text default null,
  p_receiver_phone_number text default null,
  p_customer_name         text default null,
  p_customer_phone_number text default null,
  p_ribbon_congratulations text default null,
  p_card_message          text default null,
  p_sang_divi             text default null
)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_row    order_details%rowtype;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  update order_details set
    product_name           = coalesce(p_product_name, product_name),
    price                  = coalesce(p_price, price),
    quantity               = coalesce(p_quantity, quantity),
    delivery_at            = coalesce(p_delivery_at, delivery_at),
    delivery_place         = coalesce(p_delivery_place, delivery_place),
    receiver_name          = coalesce(p_receiver_name, receiver_name),
    receiver_phone_number  = coalesce(p_receiver_phone_number, receiver_phone_number),
    customer_name          = coalesce(p_customer_name, customer_name),
    customer_phone_number  = coalesce(p_customer_phone_number, customer_phone_number),
    ribbon_congratulations = coalesce(p_ribbon_congratulations, ribbon_congratulations),
    card_message           = coalesce(p_card_message, card_message),
    sang_divi              = coalesce(p_sang_divi, sang_divi)
   where id = p_order_id and shop_key = p_shop_key
  returning * into v_row;

  if not found then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;

  -- 보완 후에도 필수값이 비어 있으면 자동입력으로 넘기지 않는다(등록 실패 방지).
  -- delivery_at 센티넬(2099-12-31)은 '미상'을 뜻하므로 채워진 것으로 보지 않는다.
  if coalesce(v_row.product_name,'') in ('', '미정')
     or coalesce(v_row.delivery_place,'') in ('', '미정')
     or coalesce(v_row.receiver_name,'') in ('', '미정')
     or v_row.delivery_at >= timestamptz '2099-01-01 00:00:00+09' then
    return json_build_object('ok', false, 'reason', 'still_incomplete',
                             'rpa_status', v_row.rpa_status);
  end if;

  update order_details set rpa_status = 'ready'
   where id = p_order_id and shop_key = p_shop_key;

  return json_build_object('ok', true, 'rpa_status', 'ready');
end;
$$;

grant execute on function complete_hold_order(
  int, text, bigint, text, int, int, timestamptz, text, text, text, text, text, text, text, text
) to anon;
