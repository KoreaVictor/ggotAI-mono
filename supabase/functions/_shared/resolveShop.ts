import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export interface ResolvedShop {
  shop_key: number;
  shop_name: string;
  representative_name: string | null;
  is_approved: string;
  slot: number | null;
}

// 기기 전화번호로 가게를 해석한다. 미등록(0행) 또는 미승인이면 null.
export async function resolveShopByDevicePhone(
  supabase: SupabaseClient,
  phone: string,
): Promise<ResolvedShop | null> {
  const { data, error } = await supabase
    .rpc("resolve_device_shop", { p_phone: phone })
    .maybeSingle();
  if (error || !data) return null;
  const shop = data as ResolvedShop;
  if (shop.is_approved !== "Y") return null;
  return shop;
}
