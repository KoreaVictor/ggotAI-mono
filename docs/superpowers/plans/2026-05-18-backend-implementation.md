# ggotAIhp 백엔드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supabase Edge Functions 2개 + DB 테이블 2개 + Storage 버킷을 구축하여 안드로이드 앱의 기기 인증 및 통화 녹음 업로드를 처리하는 백엔드를 완성한다.

**Architecture:** Supabase 단일 플랫폼(PostgreSQL + Edge Functions + Storage)으로 운영. `verify-device`는 기기 인증, `upload-call`은 오디오 파일 저장 및 이력 DB 적재를 담당. 모든 배포는 Supabase MCP 도구로 직접 실행.

**Tech Stack:** Supabase PostgreSQL, Deno(TypeScript) Edge Functions, Supabase Storage, Supabase MCP (`apply_migration`, `execute_sql`, `deploy_edge_function`)

**Project ID:** `suylrznbctrkbxbleapb`

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `supabase/migrations/20260518000000_init.sql` | DB 테이블 생성 SQL (기록용) |
| `supabase/functions/verify-device/index.ts` | 기기 인증 Edge Function |
| `supabase/functions/upload-call/index.ts` | 업로드 Edge Function |

---

## Task 1: DB 마이그레이션

**Files:**
- Create: `supabase/migrations/20260518000000_init.sql`

- [ ] **Step 1: 마이그레이션 SQL 파일 작성**

`supabase/migrations/20260518000000_init.sql` 생성:

```sql
CREATE TABLE IF NOT EXISTS member_info (
    id                      SERIAL PRIMARY KEY,
    shop_name               VARCHAR(100) NOT NULL,
    representative_name     VARCHAR(50)  NOT NULL,
    landline_number         VARCHAR(20),
    mobile_1                VARCHAR(20)  NOT NULL UNIQUE,
    mobile_2                VARCHAR(20)  DEFAULT NULL,
    mobile_3                VARCHAR(20)  DEFAULT NULL,
    mobile_4                VARCHAR(20)  DEFAULT NULL,
    mobile_5                VARCHAR(20)  DEFAULT NULL,
    business_number         VARCHAR(50),
    address                 VARCHAR(255),
    is_approved             CHAR(1)      DEFAULT 'N',
    is_subscribed           CHAR(1)      DEFAULT 'N',
    subscription_type       VARCHAR(20)  DEFAULT NULL,
    free_trial_start_date   DATE,
    current_free_trial_days INT          DEFAULT 0,
    email                   VARCHAR(100),
    created_at              TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS server_call_history (
    id                  SERIAL PRIMARY KEY,
    user_phone_number   VARCHAR(20)  NOT NULL,
    shop_name           VARCHAR(100) NOT NULL,
    phone_number        VARCHAR(20)  NOT NULL,
    customer_name       VARCHAR(50)  DEFAULT '신규',
    call_date           DATE         NOT NULL,
    call_time           TIME         NOT NULL,
    duration_seconds    INT,
    audio_file_name     VARCHAR(255) NOT NULL,
    stt_text            TEXT         DEFAULT NULL,
    is_order            CHAR(1)      DEFAULT 'N',
    created_at          TIMESTAMP    DEFAULT NOW()
);
```

- [ ] **Step 2: MCP `apply_migration`으로 테이블 생성**

`mcp__supabase__apply_migration` 호출:
- `project_id`: `suylrznbctrkbxbleapb`
- `name`: `init`
- `query`: Step 1의 SQL 전체

- [ ] **Step 3: 테이블 생성 확인**

`mcp__supabase__execute_sql` 호출:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('member_info', 'server_call_history');
```
Expected: `member_info`, `server_call_history` 2행 반환

- [ ] **Step 4: 커밋**
```bash
git add supabase/migrations/
git commit -m "feat: add member_info and server_call_history DB migration"
```

---

## Task 2: Supabase Storage 버킷 생성

- [ ] **Step 1: `audio-files` 버킷 생성**

`mcp__supabase__execute_sql` 호출:
```sql
INSERT INTO storage.buckets (id, name, public)
VALUES ('audio-files', 'audio-files', false)
ON CONFLICT (id) DO NOTHING;
```

- [ ] **Step 2: 버킷 생성 확인**

`mcp__supabase__execute_sql` 호출:
```sql
SELECT id, name, public FROM storage.buckets WHERE id = 'audio-files';
```
Expected: `id=audio-files, name=audio-files, public=false` 1행 반환

---

## Task 3: verify-device Edge Function 구현 및 배포

**Files:**
- Create: `supabase/functions/verify-device/index.ts`

- [ ] **Step 1: `verify-device/index.ts` 작성**

`supabase/functions/verify-device/index.ts` 생성:

```typescript
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

    const { data, error } = await supabase
      .from("member_info")
      .select("shop_name, representative_name, is_approved")
      .or(
        `mobile_1.eq.${phone},mobile_2.eq.${phone},mobile_3.eq.${phone},mobile_4.eq.${phone},mobile_5.eq.${phone}`
      )
      .maybeSingle();

    if (error || !data || data.is_approved !== "Y") {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "AUTH_ERR",
          message: "등록되지 않거나 승인되지 않은 단말기입니다.",
        }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({
        status: "success",
        data: {
          shop_name: data.shop_name,
          representative_name: data.representative_name,
          is_approved: data.is_approved,
        },
      }),
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
```

- [ ] **Step 2: MCP로 배포**

`mcp__supabase__deploy_edge_function` 호출:
- `project_id`: `suylrznbctrkbxbleapb`
- `name`: `verify-device`
- `entrypoint_path`: `index.ts`
- `verify_jwt`: `false` (Android 앱은 Supabase JWT 미사용, 자체 phone 인증)
- `files`: `[{ "name": "index.ts", "content": "<Step 1 코드>" }]`

- [ ] **Step 3: 테스트 데이터 시딩**

`mcp__supabase__execute_sql` 호출:
```sql
INSERT INTO member_info (shop_name, representative_name, mobile_1, is_approved)
VALUES ('테스트플라워', '테스트대표', '01099999999', 'Y')
ON CONFLICT (mobile_1) DO NOTHING;
```

- [ ] **Step 4: 인증 성공 케이스 테스트**

PowerShell 실행:
```powershell
Invoke-RestMethod "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/verify-device?phone=01099999999"
```
Expected:
```json
{"status":"success","data":{"shop_name":"테스트플라워","representative_name":"테스트대표","is_approved":"Y"}}
```

- [ ] **Step 5: 인증 실패 케이스 테스트**

PowerShell 실행:
```powershell
Invoke-RestMethod "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/verify-device?phone=01000000000"
```
Expected:
```json
{"status":"error","error_code":"AUTH_ERR","message":"등록되지 않거나 승인되지 않은 단말기입니다."}
```

- [ ] **Step 6: 커밋**
```bash
git add supabase/functions/verify-device/
git commit -m "feat: add verify-device Edge Function"
```

---

## Task 4: upload-call Edge Function 구현 및 배포

**Files:**
- Create: `supabase/functions/upload-call/index.ts`

- [ ] **Step 1: `upload-call/index.ts` 작성**

`supabase/functions/upload-call/index.ts` 생성:

```typescript
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
```

- [ ] **Step 2: MCP로 배포**

`mcp__supabase__deploy_edge_function` 호출:
- `project_id`: `suylrznbctrkbxbleapb`
- `name`: `upload-call`
- `entrypoint_path`: `index.ts`
- `verify_jwt`: `false`
- `files`: `[{ "name": "index.ts", "content": "<Step 1 코드>" }]`

- [ ] **Step 3: 더미 WAV 파일로 업로드 성공 케이스 테스트**

PowerShell 실행:
```powershell
# 최소 WAV 더미 파일 생성
[byte[]]$wav = 0x52,0x49,0x46,0x46,0x24,0x00,0x00,0x00,0x57,0x41,0x56,0x45,
               0x66,0x6D,0x74,0x20,0x10,0x00,0x00,0x00,0x01,0x00,0x01,0x00,
               0x44,0xAC,0x00,0x00,0x88,0x58,0x01,0x00,0x02,0x00,0x10,0x00,
               0x64,0x61,0x74,0x61,0x00,0x00,0x00,0x00
[System.IO.File]::WriteAllBytes("$PWD\test.wav", $wav)

# multipart 업로드
$form = @{
    user_phone_number = "01099999999"
    phone_number      = "01012345678"
    customer_name     = "테스트고객"
    call_date         = "2026-05-18"
    call_time         = "14:30:00"
    duration_seconds  = "120"
    audio_file        = Get-Item ".\test.wav"
}
Invoke-RestMethod -Uri "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/upload-call" `
    -Method POST -Form $form
```
Expected:
```json
{"status":"success","message":"업로드 성공"}
```

- [ ] **Step 4: DB 적재 확인**

`mcp__supabase__execute_sql` 호출:
```sql
SELECT user_phone_number, shop_name, phone_number, customer_name,
       call_date, call_time, duration_seconds, audio_file_name
FROM server_call_history
ORDER BY created_at DESC
LIMIT 1;
```
Expected: `user_phone_number=01099999999, audio_file_name=01099999999_01012345678_20260518_143000.wav` 1행 확인

- [ ] **Step 5: Storage 저장 확인**

`mcp__supabase__execute_sql` 호출:
```sql
SELECT name, bucket_id, created_at
FROM storage.objects
WHERE bucket_id = 'audio-files'
ORDER BY created_at DESC
LIMIT 1;
```
Expected: `name=01099999999/202605/01099999999_01012345678_20260518_143000.wav` 확인

- [ ] **Step 6: 미인증 기기 차단 테스트**

PowerShell 실행:
```powershell
$form = @{
    user_phone_number = "01000000000"
    phone_number      = "01012345678"
    call_date         = "2026-05-18"
    call_time         = "14:30:00"
    audio_file        = Get-Item ".\test.wav"
}
Invoke-RestMethod -Uri "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/upload-call" `
    -Method POST -Form $form
```
Expected:
```json
{"status":"error","error_code":"AUTH_ERR","message":"등록되지 않거나 승인되지 않은 단말기입니다."}
```

- [ ] **Step 7: 커밋**
```bash
git add supabase/functions/upload-call/
git commit -m "feat: add upload-call Edge Function"
```

---

## Task 5: 최종 정리 및 커밋

- [ ] **Step 1: 전체 파일 최종 커밋**
```bash
git add docs/ supabase/
git commit -m "docs: add backend design spec and implementation plan"
```

- [ ] **Step 2: 구현 완료 최종 확인**

`mcp__supabase__execute_sql` 호출:
```sql
SELECT
  (SELECT COUNT(*) FROM member_info)       AS members,
  (SELECT COUNT(*) FROM server_call_history) AS call_history,
  (SELECT COUNT(*) FROM storage.objects WHERE bucket_id = 'audio-files') AS audio_files;
```
Expected: `members=1, call_history=1, audio_files=1`

- [ ] **Step 3: 안드로이드 앱 연동용 최종 엔드포인트 확인**

| API | URL |
|---|---|
| 기기 인증 | `GET https://suylrznbctrkbxbleapb.supabase.co/functions/v1/verify-device?phone={phone}` |
| 업로드 | `POST https://suylrznbctrkbxbleapb.supabase.co/functions/v1/upload-call` |
