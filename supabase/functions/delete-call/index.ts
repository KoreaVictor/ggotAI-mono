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
    const { user_phone_number: userPhoneNumber, audio_file_name: audioFileName } = await req.json();

    if (!userPhoneNumber || !audioFileName) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "BAD_REQUEST",
          message: "필수 파라미터가 누락되었습니다.",
        }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    // 1단계: 기기 인증 및 승인 여부 검증
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

    console.log(`[Delete] DB 삭제 시도 - userPhoneNumber: "${userPhoneNumber}", audioFileName: "${audioFileName}"`);

    // 2단계: DB에서 해당 통화 기록 제거 (Delete) 및 삭제된 개수(count) 추적
    const { error: dbError, count } = await supabase
      .from("server_call_history")
      .delete({ count: "exact" })
      .eq("audio_file_name", audioFileName)
      .eq("user_phone_number", userPhoneNumber);

    console.log(`[Delete] DB 삭제 결과 - error: ${JSON.stringify(dbError)}, 삭제된 행 개수: ${count}`);

    if (dbError) {
      console.error("DB 삭제 실패:", JSON.stringify(dbError));
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "SERVER_500",
          message: "서버 DB 기록 삭제 중 오류가 발생했습니다.",
        }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 3단계: 스토리지에서 오디오 파일 영구 파쇄
    // 파일명 규칙: {user_phone}_{customer_phone}_{YYYYMMDD}_{HHmmss}.wav
    const parts = audioFileName.split("_");
    if (parts.length >= 3) {
      const dateStr = parts[2]; // "YYYYMMDD"
      if (dateStr && dateStr.length >= 6) {
        const yyyyMM = dateStr.substring(0, 6); // "YYYYMM"
        const storagePath = `${userPhoneNumber}/${yyyyMM}/${audioFileName}`;

        console.log(`[Delete] 스토리지 파일 영구 파쇄 실행: ${storagePath}`);
        
        const { error: storageError } = await supabase.storage
          .from("audio-files")
          .remove([storagePath]);

        if (storageError) {
          console.warn("스토리지 파일 삭제 실패 또는 파일이 이미 없음 (무시하고 통과):", JSON.stringify(storageError));
        } else {
          console.log(`[Delete] 스토리지 파일 삭제 성공`);
        }
      }
    }

    return new Response(
      JSON.stringify({ 
        status: "success", 
        message: `성공적으로 삭제되었습니다. (서버 DB ${count ?? 0}건 삭제)` 
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("Unhandled exception:", err);
    return new Response(
      JSON.stringify({
        status: "error",
        error_code: "SERVER_500",
        message: "내부 서버 오류가 발생했습니다.",
      }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
