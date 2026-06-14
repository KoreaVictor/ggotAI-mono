import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const phone = url.searchParams.get("phone");

    if (!phone) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "AUTH_ERR",
          message: "phone 파라미터가 필요합니다.",
        }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const shop = await resolveShopByDevicePhone(supabase, phone);

    if (!shop) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "AUTH_ERR",
          message: "주문받는 핸드폰 번호로 등록되지 않은 기기입니다. 환경설정에서 등록해주세요.",
        }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 환경설정 조회 (shop_key 기준). 행이 없으면 기본값 반환.
    const { data: setting, error: settingError } = await supabase
      .from("setting_info")
      .select("use_notification, notification_phone_number")
      .eq("shop_key", shop.shop_key)
      .maybeSingle();

    if (settingError) {
      console.error("setting_info query error:", JSON.stringify(settingError));
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "환경설정 조회 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({
        status: "success",
        data: {
          use_notification: setting?.use_notification ?? "Y",
          notification_phone_number: setting?.notification_phone_number ?? null,
        },
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (_err) {
    console.error("Unhandled exception:", _err);
    return new Response(
      JSON.stringify({
        status: "error",
        error_code: "SERVER_500",
        message: "내부 서버 오류",
      }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
