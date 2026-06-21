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
    const formData = await req.formData();

    const userPhoneNumber = formData.get("user_phone_number") as string;
    const phoneNumber = (formData.get("phone_number") as string) || "";
    const customerName = (formData.get("customer_name") as string) || "신규";
    const callDate = formData.get("call_date") as string;
    const callTime = formData.get("call_time") as string;
    const durationRaw = formData.get("duration_seconds");
    const durationSeconds = durationRaw ? parseInt(durationRaw as string) : null;
    const audioFile = formData.get("audio_file") as File | null;

    // 채널: 미전송/미허용 값이면 '핸드폰'(기존 ggotAIhp 무손상).
    const rawChannel = (formData.get("channel_order") as string) || "";
    const channelOrder = rawChannel === "가게음성" ? "가게음성" : "핸드폰";
    const isStoreSale = channelOrder === "가게음성";

    // 핸드폰은 발신번호 필수, 매장판매(가게음성)는 발신번호 없음.
    const missingCore = !userPhoneNumber || !callDate || !callTime || !audioFile;
    if (missingCore || (!isStoreSale && !phoneNumber)) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "FILE_NOT_FOUND",
          message: "필수 파라미터가 누락됐습니다.",
        }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const shop = await resolveShopByDevicePhone(supabase, userPhoneNumber);

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

    // 파일명 및 스토리지 경로 생성
    // 규칙: {user_phone}_{customer_phone}_{YYYYMMDD}_{HHmmss}.wav
    const dateStr = callDate.replace(/-/g, "");
    const timeStr = callTime.replace(/:/g, "");
    const fileName = `${userPhoneNumber}_${phoneNumber}_${dateStr}_${timeStr}.wav`;
    const yyyyMM = callDate.substring(0, 7).replace("-", "");
    const storagePath = `${userPhoneNumber}/${yyyyMM}/${fileName}`;

    // [멱등성 보장 - 대안 A] 이미 동일한 통화 데이터가 존재하는지 pre-check
    const { data: existingCall, error: checkError } = await supabase
      .from("server_call_history")
      .select("id")
      .eq("shop_key", shop.shop_key)
      .eq("customer_phone_number", phoneNumber)
      .eq("call_date", callDate)
      .eq("call_time", callTime)
      .maybeSingle();

    if (checkError) {
      console.error("Duplicate check query error:", JSON.stringify(checkError));
    }

    if (existingCall) {
      console.log(`[Idempotency] Duplicate call detected for ${fileName}. Skipping upload and returning success.`);
      return new Response(
        JSON.stringify({ status: "success", message: "이미 업로드 완료된 건입니다. (Idempotency 보장)" }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 1단계: DB 먼저 적재 (Storage 업로드 전에 실행하여 고아 파일 방지)
    const insertCustomerName = isStoreSale
      ? ((formData.get("customer_name") as string) || "매장판매")
      : customerName;
    const { error: dbError } = await supabase.from("server_call_history").insert({
      channel_order: channelOrder,
      channel_classification: userPhoneNumber,
      shop_key: shop.shop_key,
      shop_name: shop.shop_name,
      customer_phone_number: phoneNumber, // 매장판매는 '' (빈값)
      customer_name: insertCustomerName,
      call_date: callDate,
      call_time: callTime,
      duration_seconds: durationSeconds,
      audio_file_name: fileName,
    });

    if (dbError) {
      // 동시 업로드 경쟁: pre-check 이후 다른 요청이 먼저 적재(UNIQUE 위반 23505)
      // → 멱등 성공으로 처리한다. (pre-check는 비원자적이라 경쟁을 못 막으므로 제약이 최종 방어선)
      if (dbError.code === "23505") {
        console.log(`[Idempotency] Unique violation for ${fileName}. Concurrent upload detected; returning success.`);
        return new Response(
          JSON.stringify({ status: "success", message: "이미 업로드 완료된 건입니다. (동시성 보장)" }),
          { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      console.error("DB insert error:", JSON.stringify(dbError));
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "데이터 저장 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 2단계: DB 성공 후 Storage 업로드
    const audioBuffer = await audioFile.arrayBuffer();
    const { error: storageError } = await supabase.storage
      .from("audio-files")
      .upload(storagePath, audioBuffer, {
        contentType: "audio/wav",
        upsert: false,
      });

    if (storageError) {
      console.error("Storage upload error:", JSON.stringify(storageError));
      // 롤백: 방금 삽입한 DB 레코드 삭제
      await supabase
        .from("server_call_history")
        .delete()
        .eq("audio_file_name", fileName)
        .eq("shop_key", shop.shop_key);
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "파일 저장 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ status: "success", message: "업로드 성공" }),
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
