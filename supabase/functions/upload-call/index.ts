import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

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
    const phoneNumber = formData.get("phone_number") as string;
    const customerName = (formData.get("customer_name") as string) || "신규";
    const callDate = formData.get("call_date") as string;
    const callTime = formData.get("call_time") as string;
    const durationRaw = formData.get("duration_seconds");
    const durationSeconds = durationRaw ? parseInt(durationRaw as string) : null;
    const audioFile = formData.get("audio_file") as File | null;

    if (!userPhoneNumber || !phoneNumber || !callDate || !callTime || !audioFile) {
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

    // 기기 인증 검증
    const { data: member, error: memberError } = await supabase
      .from("member_info")
      .select("shop_name, is_approved")
      .or(
        `mobile_1.eq.${userPhoneNumber},mobile_2.eq.${userPhoneNumber},mobile_3.eq.${userPhoneNumber},mobile_4.eq.${userPhoneNumber},mobile_5.eq.${userPhoneNumber}`
      )
      .maybeSingle();

    if (memberError || !member || member.is_approved !== "Y") {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "AUTH_ERR",
          message: "등록되지 않거나 승인되지 않은 단말기입니다.",
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

    // Supabase Storage 업로드
    const audioBuffer = await audioFile.arrayBuffer();
    const { error: storageError } = await supabase.storage
      .from("audio-files")
      .upload(storagePath, audioBuffer, {
        contentType: "audio/wav",
        upsert: false,
      });

    if (storageError) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "파일 저장 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // server_call_history DB 적재
    const { error: dbError } = await supabase.from("server_call_history").insert({
      user_phone_number: userPhoneNumber,
      shop_name: member.shop_name,
      phone_number: phoneNumber,
      customer_name: customerName,
      call_date: callDate,
      call_time: callTime,
      duration_seconds: durationSeconds,
      audio_file_name: fileName,
    });

    if (dbError) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "데이터 저장 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ status: "success", message: "업로드 성공" }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (_err) {
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
