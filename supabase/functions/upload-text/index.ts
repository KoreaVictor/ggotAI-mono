import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";
import { validateTextUpload } from "./validate.ts";

// 카톡·문자 주문 수집구. upload-call 과 같은 server_call_history 에 적재하되
// 오디오가 없어 STT 단계를 건너뛴다(백엔드 engine 이 stt_text 존재 시 바로 추출).

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const formData = await req.formData();
    const valid = validateTextUpload((key) => formData.get(key));

    if (!valid.ok) {
      return json(
        { status: "error", error_code: "BAD_REQUEST", message: valid.message },
        400,
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    const shop = await resolveShopByDevicePhone(supabase, valid.userPhoneNumber);

    if (!shop) {
      return json(
        {
          status: "error",
          error_code: "AUTH_ERR",
          message: "주문받는 핸드폰 번호로 등록되지 않은 기기입니다. 환경설정에서 등록해주세요.",
        },
        401,
      );
    }

    // [멱등성] 같은 가게·발신자·수신일시면 이미 적재된 건으로 본다.
    // 폰이 업로드 성공 응답을 못 받고 재시도해도 중복 주문이 생기지 않는다.
    const { data: existing, error: checkError } = await supabase
      .from("server_call_history")
      .select("id")
      .eq("shop_key", shop.shop_key)
      .eq("customer_phone_number", valid.phoneNumber)
      .eq("call_date", valid.callDate)
      .eq("call_time", valid.callTime)
      .maybeSingle();

    if (checkError) {
      console.error("Duplicate check query error:", JSON.stringify(checkError));
    }

    if (existing) {
      console.log(`[Idempotency] Duplicate text detected for ${valid.callDate} ${valid.callTime}.`);
      return json(
        { status: "success", message: "이미 업로드 완료된 건입니다. (Idempotency 보장)" },
        200,
      );
    }

    // stt_text 를 채워 넣으므로 백엔드는 STT 없이 바로 Gemini 추출로 간다.
    // 오디오가 없어 Storage 단계도, 실패 시 롤백도 필요 없다.
    const { error: dbError } = await supabase.from("server_call_history").insert({
      channel_order: valid.channelOrder,
      channel_classification: valid.userPhoneNumber,
      shop_key: shop.shop_key,
      shop_name: shop.shop_name,
      customer_phone_number: valid.phoneNumber,
      customer_name: valid.senderName || "신규",
      call_date: valid.callDate,
      call_time: valid.callTime,
      duration_seconds: null,
      audio_file_name: null,
      stt_text: valid.sttText,
    });

    if (dbError) {
      // 동시 업로드 경쟁: pre-check 이후 다른 요청이 먼저 적재(UNIQUE 위반 23505).
      if (dbError.code === "23505") {
        console.log("[Idempotency] Unique violation; concurrent upload detected.");
        return json(
          { status: "success", message: "이미 업로드 완료된 건입니다. (동시성 보장)" },
          200,
        );
      }
      console.error("DB insert error:", JSON.stringify(dbError));
      return json(
        {
          status: "error",
          error_code: "SERVER_500",
          message: "데이터 저장 중 오류가 발생했습니다.",
        },
        500,
      );
    }

    return json({ status: "success", message: "업로드 성공" }, 200);
  } catch (_err) {
    console.error("Unhandled exception:", _err);
    return json(
      { status: "error", error_code: "SERVER_500", message: "내부 서버 오류" },
      500,
    );
  }
});
