-- ggotAIya D: 주문조회 — get_orders / requeue_order 샵범위 RPC + order_details 하드닝
-- (Management API 로 적용. 본 파일은 버전관리 기록용.)

-- 1) 주문 목록 조회 (채널/기간/상태 서버필터, server_call_history 조인으로 채널 취득)
create or replace function get_orders(
  p_shop_key int,
  p_token    text,
  p_channel  text default null,        -- null=전체, else server_call_history.channel_order 일치
  p_status   text default null,        -- null=전체, else order_details.rpa_status 일치
  p_start    timestamptz default null, -- 조회 시작(포함)
  p_end      timestamptz default null  -- 조회 종료(미포함)
) returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_member member_info%rowtype;
  v_rows json;
begin
  select * into v_member from member_info where id = p_shop_key;
  if not found
     or v_member.remember_token_hash is null
     or v_member.remember_token_expires_at <= now()
     or v_member.remember_token_hash <> crypt(p_token, v_member.remember_token_hash) then
    return json_build_object('ok', false, 'reason', 'unauthorized');
  end if;

  select coalesce(json_agg(r order by r.created_at desc), '[]'::json) into v_rows
  from (
    select od.id, od.call_history_id, od.customer_name, od.customer_phone_number,
           od.product_name, od.quantity, od.price, od.delivery_at, od.delivery_place,
           od.receiver_name, od.receiver_phone_number, od.ribbon_sender,
           od.ribbon_congratulations, od.card_message, od.rpa_status, od.created_at,
           sch.channel_order
    from order_details od
    left join server_call_history sch on sch.id = od.call_history_id
    where od.shop_key = p_shop_key
      and (p_start   is null or od.created_at >= p_start)
      and (p_end     is null or od.created_at <  p_end)
      and (p_channel is null or sch.channel_order = p_channel)
      and (p_status  is null or od.rpa_status     = p_status)
    order by od.created_at desc
    limit 500
  ) r;

  return json_build_object('ok', true, 'rows', v_rows);
end;
$$;

-- 2) RPA 재큐 (샵스코핑으로 교차샵 차단)
create or replace function requeue_order(p_shop_key int, p_token text, p_order_id bigint)
returns json
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

  update order_details set rpa_status = 'ready'
   where id = p_order_id and shop_key = p_shop_key;
  get diagnostics v_count = row_count;
  if v_count = 0 then
    return json_build_object('ok', false, 'reason', 'not_found');
  end if;
  return json_build_object('ok', true, 'rpa_status', 'ready');
end;
$$;

grant execute on function get_orders(int, text, text, text, timestamptz, timestamptz) to anon;
grant execute on function requeue_order(int, text, bigint) to anon;

-- 하드닝: order_details anon/authenticated 직접권한 회수(조회/재큐는 owner 실행 RPC로만)
revoke all privileges on table order_details from anon, authenticated, public;
