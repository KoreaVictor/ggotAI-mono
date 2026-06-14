-- 2026-06-14 기기 인증 게이트(A안): 기기 전화번호를 setting_info.order_hp_1/2와
-- 정규화(숫자만) 비교해 가게를 식별. 승인 여부는 호출측(헬퍼)에서 확인.
create or replace function resolve_device_shop(p_phone text)
returns table (
  shop_key int,
  shop_name text,
  representative_name text,
  is_approved text,
  slot int
)
language sql
security definer
set search_path = public
as $$
  select m.id, m.shop_name, m.representative_name, m.is_approved,
         case
           when regexp_replace(coalesce(s.order_hp_1,''),'\D','','g')
                = regexp_replace(coalesce(p_phone,''),'\D','','g')
                and regexp_replace(coalesce(s.order_hp_1,''),'\D','','g') <> '' then 1
           when regexp_replace(coalesce(s.order_hp_2,''),'\D','','g')
                = regexp_replace(coalesce(p_phone,''),'\D','','g')
                and regexp_replace(coalesce(s.order_hp_2,''),'\D','','g') <> '' then 2
         end as slot
  from setting_info s
  join member_info m on m.id = s.shop_key
  where regexp_replace(coalesce(p_phone,''),'\D','','g') <> ''
    and (
      regexp_replace(coalesce(s.order_hp_1,''),'\D','','g')
        = regexp_replace(coalesce(p_phone,''),'\D','','g')
      or
      regexp_replace(coalesce(s.order_hp_2,''),'\D','','g')
        = regexp_replace(coalesce(p_phone,''),'\D','','g')
    )
  order by m.id
  limit 1;
$$;

revoke all on function resolve_device_shop(text) from anon, authenticated, public;
