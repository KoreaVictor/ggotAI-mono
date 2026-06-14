# 기기 인증 order_hp 게이트 (A안) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기기(앱) 전화번호가 `setting_info.order_hp_1/2`에 등록된 가게에서만 ggotAIhp가 동작하도록 4개 엣지함수의 기기 식별을 `member.mobile_number` → `order_hp` 정규화 매칭으로 전환한다.

**Architecture:** 매칭 로직을 신규 `resolve_device_shop(p_phone)` SECURITY DEFINER RPC 한 곳에 두고(정규화: 숫자만 비교), 공유 TS 헬퍼 `_shared/resolveShop.ts`가 이를 호출한다. 4개 엣지함수(verify-device/get-settings/upload-call/delete-call)는 기존 member 조회 블록을 이 헬퍼로 교체한다. Android·대시보드는 변경 없음(앱은 기존 `AUTH_ERR` 처리로 자동 차단, 대시보드는 게이트 덕에 config 표시가 진실이 됨).

**Tech Stack:** Supabase Postgres(plpgsql/sql RPC), Deno/TypeScript edge functions, Supabase CLI(`npx supabase`), Supabase Management API(SQL 적용), Python(라이브 스모크).

---

## 설계 출처
`ggotAIorder/docs/superpowers/specs/2026-06-14-device-gate-order-hp-design.md`

## 전제 / 환경
- 모노레포 루트: `C:\ggotAI` (git 루트). 작업 브랜치 `feature/device-gate-order-hp`(이미 생성, spec 커밋 `76fed5c`).
- 프로젝트 ref: `suylrznbctrkbxbleapb`. 관리 PAT는 **레지스트리** `HKCU:\Environment` 의 `SUPABASE_ACCESS_TOKEN`(하니스 셸은 부모 env가 옛값일 수 있으므로 **항상 레지스트리에서 읽어 주입**).
- service_role 키·URL: `ggotAIorder/backend/.env`(라이브 스모크 스크립트가 읽음).
- 엣지함수는 Deno라 repo CI(pytest/vitest)에 단위 테스트 인프라가 없음 → **라이브 스모크로 검증**.
- 현재 4개 엣지함수의 기기 식별(교체 대상):
  - `verify-device`: `member_info.select("id, shop_name, representative_name, is_approved").eq("mobile_number", phone)`
  - `get-settings`: `member_info.select("id, is_approved").eq("mobile_number", phone)` → 이후 `member.id`로 setting 조회
  - `upload-call`: `member_info.select("id, shop_name, is_approved").eq("mobile_number", userPhoneNumber)` → `member.id`, `member.shop_name` 사용
  - `delete-call`: `member_info.select("id, shop_name, is_approved").eq("mobile_number", userPhoneNumber)` → `member.id` 사용

## 파일 구조
```
supabase/
├─ migrations/20260614000200_resolve_device_shop.sql   (신규 RPC)
└─ functions/
   ├─ _shared/resolveShop.ts                           (신규 공유 헬퍼)
   ├─ verify-device/index.ts                           (수정)
   ├─ get-settings/index.ts                            (수정)
   ├─ upload-call/index.ts                             (수정)
   └─ delete-call/index.ts                             (수정)
```
헬퍼/스모크 보조 스크립트는 repo 밖(임시)에 둔다.

---

## Task 1: resolve_device_shop RPC 마이그레이션 작성

**Files:**
- Create: `supabase/migrations/20260614000200_resolve_device_shop.sql`

- [ ] **Step 1: 마이그레이션 SQL 작성**

```sql
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
  limit 1;
$$;

revoke all on function resolve_device_shop(text) from anon, authenticated, public;
```

- [ ] **Step 2: 커밋**

```bash
cd /c/ggotAI && git add supabase/migrations/20260614000200_resolve_device_shop.sql
git commit -m "feat(db): resolve_device_shop RPC(기기번호 order_hp 정규화 매칭)"
```

---

## Task 2: RPC를 라이브에 적용 + 스모크 (TDD: 적용 전 실패 → 적용 후 통과)

**Files:**
- 임시: `C:\ggotAI_tmp\apply_sql.py`, `C:\ggotAI_tmp\smoke_rpc.py` (repo 밖)

- [ ] **Step 1: (RED) 적용 전 RPC 부재 확인**

`C:\ggotAI_tmp\smoke_rpc.py` 작성:
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import httpx
from dotenv import dotenv_values
e = dotenv_values(r"C:\ggotAI\ggotAIorder\backend\.env")
url, key = e["SUPABASE_URL"].rstrip("/"), e["SUPABASE_SERVICE_ROLE_KEY"]
def rpc(phone):
    r = httpx.post(f"{url}/rest/v1/rpc/resolve_device_shop",
                   headers={"apikey": key, "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"},
                   json={"p_phone": phone}, timeout=30)
    return r.status_code, r.text
print("EMPTY  ->", rpc(""))
print("UNREG  ->", rpc("010-0000-0000"))
print("REG    ->", rpc("010-1234-5678"))
```
Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/smoke_rpc.py
```
Expected: 함수 부재로 404/`PGRST202`(Could not find function) 류 에러. (RPC 아직 없음 = RED.)

- [ ] **Step 2: Management API로 마이그레이션 SQL 적용**

`C:\ggotAI_tmp\apply_sql.py` 작성(레지스트리 PAT 사용, SQL 파일을 읽어 실행):
```python
import sys, io, os, winreg
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import httpx
REF = "suylrznbctrkbxbleapb"
k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
pat, _ = winreg.QueryValueEx(k, "SUPABASE_ACCESS_TOKEN")
sql = open(sys.argv[1], encoding="utf-8").read()
r = httpx.post(f"https://api.supabase.com/v1/projects/{REF}/database/query",
               headers={"Authorization": f"Bearer {pat}", "Content-Type": "application/json"},
               json={"query": sql}, timeout=60)
print(r.status_code, r.text[:300])
```
Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/apply_sql.py "C:\ggotAI\supabase\migrations\20260614000200_resolve_device_shop.sql"
```
Expected: HTTP 200/201 (성공). 실패(권한 등) 시 폴백: 사장님이 Supabase SQL 편집기에 같은 SQL 붙여 실행.

- [ ] **Step 3: 스모크용 order_hp 임시 등록(test꽃집 shop_key=19)**

`C:\ggotAI_tmp\apply_sql.py`로 임시 UPDATE 적용:
```bash
echo "insert into setting_info (shop_key, order_hp_1) values (19,'010-1234-5678') on conflict (shop_key) do update set order_hp_1='010-1234-5678';" > C:/ggotAI_tmp/seed.sql
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/apply_sql.py "C:\ggotAI_tmp\seed.sql"
```
Expected: 200. (setting_info에 shop_key UNIQUE 제약이 있다는 전제 — 없으면 `on conflict` 대신 존재 여부 보고 insert/update. 스모크 종료 후 Task 9에서 원복.)

- [ ] **Step 4: (GREEN) RPC 스모크 재실행**

Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/smoke_rpc.py
```
Expected:
- `EMPTY` → `200 []` (빈 입력 매칭 없음)
- `UNREG` (010-0000-0000) → `200 []` (미등록)
- `REG` (010-1234-5678, 대시 양식) → `200 [{"shop_key":19,...,"slot":1}]`
- 추가 확인: 숫자만 양식도 매칭되는지 smoke_rpc.py에 `print("REGnodash->", rpc("01012345678"))` 한 줄 추가 후 재실행 → 동일하게 shop_key=19 반환(정규화 검증).

---

## Task 3: 공유 헬퍼 _shared/resolveShop.ts

**Files:**
- Create: `supabase/functions/_shared/resolveShop.ts`

- [ ] **Step 1: 헬퍼 작성**

```ts
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
```

- [ ] **Step 2: 커밋**

```bash
cd /c/ggotAI && git add supabase/functions/_shared/resolveShop.ts
git commit -m "feat(edge): resolveShopByDevicePhone 공유 헬퍼"
```

---

## Task 4: verify-device 게이트 교체

**Files:**
- Modify: `supabase/functions/verify-device/index.ts`

- [ ] **Step 1: import 추가**

`index.ts` 상단 import 블록에 추가:
```ts
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";
```

- [ ] **Step 2: member 조회 블록 교체**

기존(34–49행 부근):
```ts
    const { data, error } = await supabase
      .from("member_info")
      .select("id, shop_name, representative_name, is_approved")
      .eq("mobile_number", phone)
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
```
교체 후:
```ts
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
```

- [ ] **Step 3: 성공 응답의 data 매핑 교체**

기존:
```ts
        data: {
          shop_key: data.id,
          shop_name: data.shop_name,
          representative_name: data.representative_name,
          is_approved: data.is_approved,
        },
```
교체 후:
```ts
        data: {
          shop_key: shop.shop_key,
          shop_name: shop.shop_name,
          representative_name: shop.representative_name,
          is_approved: shop.is_approved,
        },
```

- [ ] **Step 4: 커밋**

```bash
cd /c/ggotAI && git add supabase/functions/verify-device/index.ts
git commit -m "feat(edge): verify-device를 order_hp 게이트로 전환"
```

---

## Task 5: get-settings 게이트 교체

**Files:**
- Modify: `supabase/functions/get-settings/index.ts`

- [ ] **Step 1: import 추가**

```ts
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";
```

- [ ] **Step 2: member 조회 블록 교체**

기존(35–50행 부근):
```ts
    const { data: member, error: memberError } = await supabase
      .from("member_info")
      .select("id, is_approved")
      .eq("mobile_number", phone)
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
```
교체 후:
```ts
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
```

- [ ] **Step 3: setting 조회의 shop_key 참조 교체**

기존:
```ts
      .eq("shop_key", member.id)
```
교체 후:
```ts
      .eq("shop_key", shop.shop_key)
```

- [ ] **Step 4: 커밋**

```bash
cd /c/ggotAI && git add supabase/functions/get-settings/index.ts
git commit -m "feat(edge): get-settings를 order_hp 게이트로 전환"
```

---

## Task 6: upload-call 게이트 교체

**Files:**
- Modify: `supabase/functions/upload-call/index.ts`

- [ ] **Step 1: import 추가**

```ts
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";
```

- [ ] **Step 2: member 조회 블록 교체**

기존(43–50행 부근):
```ts
    const { data: member, error: memberError } = await supabase
      .from("member_info")
      .select("id, shop_name, is_approved")
      .eq("mobile_number", userPhoneNumber)
      .maybeSingle();

    if (memberError || !member || member.is_approved !== "Y") {
      return new Response(
```
교체 후(주의: 바로 다음 줄의 `return new Response(`는 그대로 두고 그 안 401 응답도 유지):
```ts
    const shop = await resolveShopByDevicePhone(supabase, userPhoneNumber);

    if (!shop) {
      return new Response(
```
그리고 해당 401 응답의 message를 다음으로 교체:
```ts
          message: "주문받는 핸드폰 번호로 등록되지 않은 기기입니다. 환경설정에서 등록해주세요.",
```

- [ ] **Step 3: INSERT의 shop_key/shop_name 참조 교체**

기존(92–96행 부근 insert payload):
```ts
      shop_key: member.id,
      shop_name: member.shop_name,
```
교체 후:
```ts
      shop_key: shop.shop_key,
      shop_name: shop.shop_name,
```
그리고 롤백 delete의 `.eq("shop_key", member.id)`도 `.eq("shop_key", shop.shop_key)`로 교체.

- [ ] **Step 4: member.id/member.shop_name 잔여 참조 없는지 확인**

Run:
```bash
grep -nE "member\.id|member\.shop_name|memberError|member\b" /c/ggotAI/supabase/functions/upload-call/index.ts
```
Expected: 출력 없음(모두 shop.* 로 교체됨).

- [ ] **Step 5: 커밋**

```bash
cd /c/ggotAI && git add supabase/functions/upload-call/index.ts
git commit -m "feat(edge): upload-call을 order_hp 게이트로 전환"
```

---

## Task 7: delete-call 게이트 교체

**Files:**
- Modify: `supabase/functions/delete-call/index.ts`

- [ ] **Step 1: import 추가**

```ts
import { resolveShopByDevicePhone } from "../_shared/resolveShop.ts";
```

- [ ] **Step 2: member 조회 블록 교체**

기존(34–49행 부근):
```ts
    const { data: member, error: memberError } = await supabase
      .from("member_info")
      .select("id, shop_name, is_approved")
      .eq("mobile_number", userPhoneNumber)
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
```
교체 후:
```ts
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
```

- [ ] **Step 3: delete의 shop_key 참조 교체**

기존:
```ts
      .eq("shop_key", member.id);
```
교체 후:
```ts
      .eq("shop_key", shop.shop_key);
```

- [ ] **Step 4: 커밋**

```bash
cd /c/ggotAI && git add supabase/functions/delete-call/index.ts
git commit -m "feat(edge): delete-call을 order_hp 게이트로 전환"
```

---

## Task 8: 4개 엣지함수 배포 + 라이브 스모크

**Files:** 없음(배포/검증)

- [ ] **Step 1: PAT 주입 + 함수 배포**

레지스트리 PAT를 주입해 4개 배포(PowerShell):
```powershell
$env:SUPABASE_ACCESS_TOKEN = (Get-ItemProperty 'HKCU:\Environment' -Name SUPABASE_ACCESS_TOKEN).SUPABASE_ACCESS_TOKEN
Set-Location C:\ggotAI
foreach ($fn in @("verify-device","get-settings","upload-call","delete-call")) {
  npx --yes supabase@latest functions deploy $fn --project-ref suylrznbctrkbxbleapb 2>&1 | Select-Object -Last 3
}
```
Expected: 각 함수 "Deployed Functions on project" 성공 메시지.
폴백: `functions deploy`가 Docker를 요구하면(버전에 따라) → `--use-api` 플래그 시도, 그래도 안 되면 사장님이 Supabase 대시보드 Functions 화면에서 배포하거나 Docker 설치.

- [ ] **Step 2: verify-device 라이브 스모크(등록=200 / 미등록=401)**

`C:\ggotAI_tmp\smoke_edge.py` 작성:
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import httpx
from dotenv import dotenv_values
e = dotenv_values(r"C:\ggotAI\ggotAIorder\backend\.env")
base = e["SUPABASE_URL"].rstrip("/") + "/functions/v1"
key = e["SUPABASE_ANON_KEY"]
def verify(phone):
    r = httpx.get(f"{base}/verify-device", params={"phone": phone},
                  headers={"Authorization": f"Bearer {key}", "apikey": key}, timeout=30)
    return r.status_code, r.json().get("status"), r.json().get("error_code")
print("REG    ->", verify("010-1234-5678"))   # 기대 (200,'success',None)
print("REGnd  ->", verify("01012345678"))      # 기대 (200,'success',None) 정규화
print("UNREG  ->", verify("010-0000-0000"))    # 기대 (401,'error','AUTH_ERR')
```
Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/smoke_edge.py
```
Expected: REG/REGnd → `(200,'success',None)`, UNREG → `(401,'error','AUTH_ERR')`.

- [ ] **Step 3: get-settings 동일 스모크(빠른 확인)**

`smoke_edge.py`에 추가:
```python
def settings(phone):
    r = httpx.get(f"{base}/get-settings", params={"phone": phone},
                  headers={"Authorization": f"Bearer {key}", "apikey": key}, timeout=30)
    return r.status_code, r.json().get("status")
print("SET REG  ->", settings("010-1234-5678"))  # (200,'success')
print("SET UNREG->", settings("010-0000-0000"))   # (401,'error')
```
Run: 위와 동일 스크립트 재실행.
Expected: REG `(200,'success')`, UNREG `(401,'error')`.

---

## Task 9: 회귀 + 정리 + PR

**Files:** 없음

- [ ] **Step 1: 백엔드·프론트 회귀(이 변경과 무관 → 그린 유지)**

Run:
```bash
cd /c/ggotAI/ggotAIorder/backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -2
cd /c/ggotAI/ggotAIorder/frontend && npx vitest run 2>&1 | tail -3
```
Expected: backend `121 passed, 5 skipped`, frontend `75 passed`.

- [ ] **Step 2: 스모크용 임시 order_hp 원복**

test꽃집은 원래 setting_info 행이 없었으므로 삽입한 행을 제거:
```bash
echo "delete from setting_info where shop_key=19;" > C:/ggotAI_tmp/cleanup.sql
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe /c/ggotAI_tmp/apply_sql.py "C:\ggotAI_tmp\cleanup.sql"
```
Expected: 200. (원상태=설정 행 없음 복원. 만약 원래 행이 있었다면 delete 대신 order_hp_1만 NULL로 UPDATE.)

- [ ] **Step 3: 임시 스크립트 폴더 삭제**

```bash
rm -rf /c/ggotAI_tmp && echo "tmp removed"
```

- [ ] **Step 4: 푸시 + PR**

```bash
cd /c/ggotAI && git push -u origin feature/device-gate-order-hp
gh pr create --base master --head feature/device-gate-order-hp \
  --title "feat(edge): 기기 인증을 order_hp 등록 기반으로 전환(A안)" \
  --body "기기 전화번호가 setting_info.order_hp_1/2에 등록된 가게에서만 앱 동작. resolve_device_shop RPC(정규화 매칭)+공유 헬퍼로 4개 엣지함수 게이트 일원화. 라이브 스모크(등록200/미등록401) 통과, 백엔드 121·프론트 75 회귀0. Android/대시보드 무변경."
```
Expected: PR 생성 URL 출력.

---

## Self-Review (스펙 대조)

- 스펙 §4.1 RPC → Task 1·2 ✓
- 스펙 §4.2 공유 헬퍼 → Task 3 ✓
- 스펙 §4.3 4개 엣지함수 → Task 4·5·6·7 ✓
- 스펙 §4.4 Android/대시보드 무변경 → 작업 없음(의도) ✓
- 스펙 §3 정규화 → Task 1 RPC regexp_replace + Task 2·8 정규화 스모크(REGnd) ✓
- 스펙 §6 라이브 스모크 검증 → Task 2·8 ✓
- 스펙 §8 완료정의(스모크+회귀) → Task 8·9 ✓

## 위험 / 주의
- **배포 메커니즘 불확실**: `supabase functions deploy`가 일부 버전/환경에서 Docker를 요구할 수 있음. 실패 시 폴백(대시보드 배포/Docker)을 Task 8 Step 1에 명시.
- **Management API SQL 적용**: `/v1/projects/{ref}/database/query`가 권한/엔드포인트 문제로 막히면 사장님이 SQL 편집기에 붙여 실행(폴백).
- **정규화가 핵심**: REGnd(숫자만) 스모크가 실패하면 매칭이 형식에 취약한 것 → RPC 정규화 점검.
- **setting_info UNIQUE(shop_key)**: Task 2 seed의 `on conflict`는 shop_key 유니크 전제. 없으면 존재여부 확인 후 insert/update로 대체.
- **member.mobile_number 역할 축소**: 기기 식별에서 빠짐. 회원가입/마이페이지는 무관하니 건드리지 않음.
