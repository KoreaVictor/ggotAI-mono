-- ggotAI: order_details 에 배송시간 원본 문구(delivery_at_text) 컬럼 추가
-- (Management API 또는 대시보드 SQL 에디터로 적용. 본 파일은 버전관리 기록용.)
--
-- 배경: Gemini가 배송시간을 "내일 오후 3시" 같은 자연어로 추출 → timestamptz(delivery_at) INSERT 실패.
-- 해결: delivery_at 은 파싱된 ISO 시각(불명확 시 센티넬)으로, 원본 문구는 delivery_at_text 에 그대로 보관.

-- 1) 원본 문구 컬럼 추가
ALTER TABLE order_details
  ADD COLUMN IF NOT EXISTS delivery_at_text VARCHAR(100) DEFAULT NULL;  -- 배송시간 원본 문구(말한 그대로)

-- 2) get_orders RPC 재정의 — 반환에 delivery_at_text 포함
create or replace function get_orders(
  p_shop_key int,
  p_token    text,
  p_channel  text default null,
  p_status   text default null,
  p_start    timestamptz default null,
  p_end      timestamptz default null
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
           od.product_name, od.quantity, od.price, od.delivery_at, od.delivery_at_text,
           od.delivery_place, od.receiver_name, od.receiver_phone_number, od.ribbon_sender,
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

grant execute on function get_orders(int, text, text, text, timestamptz, timestamptz) to anon;
