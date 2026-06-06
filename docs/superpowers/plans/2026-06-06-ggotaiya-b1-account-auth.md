# ggotAIya 서브프로젝트 B1 (회원가입·비밀번호 해싱·영구 자동로그인) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ggotAIya 로그인 게이트(A) 위에 회원가입·서버사이드 비밀번호 해싱·영구 자동로그인을 추가하고, 인증을 Postgres RPC(pgcrypto)로 전환해 anon이 `password`를 직접 읽던 보안 구멍을 닫는다.

**Architecture:** 인증·계정 로직을 Supabase Postgres RPC 함수(SECURITY DEFINER, pgcrypto bcrypt)로 옮긴다. 프론트는 `verify_login`/`signup_member`/`check_username`/`issue|verify|clear_remember_token` RPC만 호출하고 비밀 컬럼을 절대 읽지 않는다(컬럼 권한으로 anon 차단). 영구 자동로그인은 서버 발급 remember_token을 Electron `safeStorage`에 보관하고 앱 시작 시 RPC로 검증해 세션을 복원한다.

**Tech Stack:** React 19 + Vite + Electron + Tailwind v4 + @supabase/supabase-js + Vitest + Supabase Postgres(pgcrypto) + Electron safeStorage + 다음(카카오) 우편번호 API.

**Branch:** `feature/ggotaiya-b1-account-auth` (master에서 분기).

**작업 디렉터리:** `frontend/` (npm 명령은 `cd /c/ggotAI/ggotAIorder/frontend`). DB는 Supabase MCP(`mcp__supabase__*`)로 적용.

**설계서:** `docs/superpowers/specs/2026-06-06-ggotaiya-b1-account-auth-design.md`

---

## 사전 참고 (구현자 필독)

- 프론트에서 `member_info`를 직접 읽는 곳은 **`session/authenticate.ts` 하나뿐**(검증 완료). 이번에 RPC로 대체하므로 컬럼 권한 회수가 다른 화면을 깨지 않는다.
- A의 `authenticate.ts`는 `from('member_info').select(...).eq(...).maybeSingle()` + 평문 비교, `AuthClient`는 그 체이닝 계약. B1에서 **rpc 계약으로 교체**한다.
- A의 `SessionContext`는 `authenticate(supabase as unknown as AuthClient, ...)` 단일 캐스트를 쓴다. 동일 패턴 유지.
- A의 `login.tsx`에는 `autoLogin` 체크박스가 **표시만** 있다(Task 6에서 실제 배선).
- Electron main(`src/main/index.ts`)은 `ipcMain.handle('service:*', ...)` 패턴, preload(`src/main/preload.ts`)는 `ipcRenderer.invoke`로 노출. 동일 패턴으로 `auth:*` 채널 추가.
- 기존 6개 pre-existing tsc(app) 미사용 경고는 B1 범위 밖이 아니라 **이미 PR #11에서 dashboard `X`는 수정됨**. 현재 미사용 경고(dashboard `React`/`AlertCircle`, order_list `Phone`)는 잔존하나 본 작업과 무관 — 본인 신규/수정 파일이 0 신규 에러인지로 판단.
- 빌드 검증: `npm run build`(= `tsc -p tsconfig.main.json && vite build`). 단위테스트: `npm test`(vitest run).
- **DB 마이그레이션은 라이브 Supabase에 적용**된다(MCP). 적용 전 `mcp__supabase__list_tables`로 현 스키마 확인. 컨트롤러(상위 에이전트)가 직접 적용할 수도 있다.

---

## File Structure

| 파일 | 책임 | 작업 |
|------|------|------|
| `docs/migrations/2026-06-06-b1-auth.sql` | B1 DB 마이그레이션 SQL 기록(버전관리) | Create (Task 1) |
| Supabase RPC/스키마 | pgcrypto·컬럼·RPC·권한·평문해싱 | Apply via MCP (Task 1) |
| `frontend/src/session/authenticate.ts` | rpc 기반 로그인 검증 | Modify (Task 2) |
| `frontend/src/session/authenticate.test.ts` | authenticate 단위테스트(fake rpc) | Modify (Task 2) |
| `frontend/src/main/index.ts` | `auth:save|load|clear` IPC(safeStorage) | Modify (Task 3) |
| `frontend/src/main/preload.ts` | remember_token 메서드 노출 | Modify (Task 3) |
| `frontend/src/types/electron.d.ts` | remember_token 메서드 타입 | Modify (Task 3) |
| `frontend/src/session/rememberToken.ts` | `restoreSession` 순수 로직 | Create (Task 4) |
| `frontend/src/session/rememberToken.test.ts` | restoreSession 단위테스트 | Create (Task 4) |
| `frontend/src/session/SessionContext.tsx` | login(rememberMe)/logout/자동로그인/authReady | Modify (Task 4) |
| `frontend/src/signup/validate.ts` | 가입 폼 순수 검증 | Create (Task 5) |
| `frontend/src/signup/validate.test.ts` | 검증 단위테스트 | Create (Task 5) |
| `frontend/src/utils/daumPostcode.ts` | 다음 우편번호 로더 | Create (Task 5) |
| `frontend/src/views/signup.tsx` | 회원가입 화면 | Create (Task 5) |
| `frontend/src/App.tsx` | authReady 게이팅 + signup 임포트 | Modify (Task 6) |
| `frontend/src/views/login.tsx` | autoLogin 배선 | Modify (Task 6) |

---

## Task 1: DB 마이그레이션 (pgcrypto + RPC + 컬럼 권한 + 평문 해싱)

**Files:**
- Create: `docs/migrations/2026-06-06-b1-auth.sql` (기록용)
- Apply: Supabase MCP `apply_migration` ×2, `execute_sql` 스모크

> 이 Task는 Vitest 대상이 아니다. SQL을 파일로 기록하고 MCP로 적용한 뒤 `execute_sql` 라운드트립으로 검증한다.

- [ ] **Step 1: 현 스키마·RLS 확인**

Run(MCP): `mcp__supabase__list_tables` (schemas: `["public"]`). `member_info` 컬럼과 RLS 활성 여부 확인. (기대: A의 `db.ts`와 동일한 12컬럼.)

- [ ] **Step 2: 마이그레이션 SQL 파일 작성 (기록용)**

`docs/migrations/2026-06-06-b1-auth.sql`:
```sql
-- ggotAIya B1: pgcrypto 인증 RPC + remember_token + 컬럼 권한 + 평문 해싱
-- (Supabase MCP apply_migration 으로 적용. 본 파일은 버전관리 기록용.)

-- ===== 마이그레이션 1: 스키마 + RPC + 권한 =====
create extension if not exists pgcrypto;

alter table member_info
  add column if not exists remember_token_hash       text,
  add column if not exists remember_token_expires_at timestamptz;

-- 아이디 중복확인
create or replace function check_username(p_username text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists(select 1 from member_info where username = p_username);
$$;

-- 회원가입 (비번 bcrypt 해싱, 승인대기 N)
create or replace function signup_member(
  p_username text, p_password text, p_shop_name text,
  p_representative_name text, p_landline text, p_mobile text,
  p_email text, p_address text, p_address_detail text)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare v_id bigint;
begin
  if exists(select 1 from member_info where username = p_username) then
    raise exception 'USERNAME_TAKEN';
  end if;
  insert into member_info(username, password, shop_name, representative_name,
    landline_number, mobile_number, email, address, address_detail, is_approved)
  values(p_username, crypt(p_password, gen_salt('bf')), p_shop_name,
    p_representative_name, p_landline, p_mobile, p_email, p_address,
    p_address_detail, 'N')
  returning id into v_id;
  return json_build_object('id', v_id, 'is_approved', 'N');
end;
$$;

-- 로그인 검증 (비번 자체는 반환 안 함)
create or replace function verify_login(p_username text, p_password text)
returns json
language sql
security definer
set search_path = public
as $$
  select json_build_object('id', id, 'shop_name', shop_name,
                           'username', username, 'is_approved', is_approved)
  from member_info
  where username = p_username
    and password = crypt(p_password, password);
$$;

-- remember_token 발급 (해시 저장, 30일 만료, 평문 반환)
create or replace function issue_remember_token(p_user_id bigint)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare v_token text;
begin
  v_token := encode(gen_random_bytes(32), 'hex');
  update member_info
     set remember_token_hash = crypt(v_token, gen_salt('bf')),
         remember_token_expires_at = now() + interval '30 days'
   where id = p_user_id;
  return v_token;
end;
$$;

-- remember_token 검증 (세션 반환 또는 null)
create or replace function verify_remember_token(p_user_id bigint, p_token text)
returns json
language sql
security definer
set search_path = public
as $$
  select json_build_object('id', id, 'shop_name', shop_name, 'username', username)
  from member_info
  where id = p_user_id
    and remember_token_hash is not null
    and remember_token_expires_at > now()
    and remember_token_hash = crypt(p_token, remember_token_hash);
$$;

-- remember_token 정리 (로그아웃)
create or replace function clear_remember_token(p_user_id bigint)
returns void
language sql
security definer
set search_path = public
as $$
  update member_info
     set remember_token_hash = null, remember_token_expires_at = null
   where id = p_user_id;
$$;

-- 컬럼 권한: anon 의 password/remember_token_* 직접 SELECT 차단
revoke select on member_info from anon;
grant select (id, username, shop_name, representative_name,
              landline_number, mobile_number, email, address,
              address_detail, is_approved, created_at) on member_info to anon;
grant execute on function check_username(text), signup_member(text,text,text,text,text,text,text,text,text),
  verify_login(text,text), issue_remember_token(bigint),
  verify_remember_token(bigint,text), clear_remember_token(bigint) to anon;

-- ===== 마이그레이션 2: 기존 평문 비번 해싱 (멱등 가드) =====
update member_info
   set password = crypt(password, gen_salt('bf'))
 where password is not null
   and password not like '$2%';
```

- [ ] **Step 3: 마이그레이션 1 적용**

Run(MCP): `mcp__supabase__apply_migration` — name `b1_auth_rpc`, query = 위 SQL의 "마이그레이션 1" 블록(`create extension` ~ `grant execute ...`).
Expected: 성공(에러 없음).

- [ ] **Step 4: 마이그레이션 2 적용 (평문 해싱)**

Run(MCP): `mcp__supabase__apply_migration` — name `b1_hash_existing_passwords`, query = "마이그레이션 2" `update` 문.
Expected: 성공. (기존 행이 0개여도 무해.)

- [ ] **Step 5: 라운드트립 스모크 검증**

Run(MCP): `mcp__supabase__execute_sql` 로 순차 실행:
```sql
select signup_member('b1smoke','pw_smoke_123','스모크꽃집','홍길동',null,'01000000000',null,null,null);
select verify_login('b1smoke','pw_smoke_123');   -- {id,...,is_approved:'N'} 반환
select verify_login('b1smoke','wrong');           -- null
update member_info set is_approved='Y' where username='b1smoke';
-- 자동로그인 토큰 라운드트립
select issue_remember_token((select id from member_info where username='b1smoke'));  -- 토큰 t
-- (반환된 t 로) select verify_remember_token(<id>, '<t>');  -- 세션 반환
-- select verify_remember_token(<id>, 'badtoken');           -- null
select clear_remember_token((select id from member_info where username='b1smoke'));
delete from member_info where username='b1smoke';  -- 스모크 데이터 정리
```
Expected: `verify_login` 정상=객체/오답=null, 토큰 검증 정상=세션/오답=null. **정리 delete 필수.**

- [ ] **Step 6: 컬럼 권한 검증**

Run(MCP): `mcp__supabase__execute_sql`:
```sql
set role anon;
select password from member_info limit 1;  -- 권한 거부(permission denied) 기대
reset role;
```
Expected: anon 으로 `password` 조회 시 `permission denied for column password` 또는 그에 준하는 거부. (지원 안 되면 `mcp__supabase__get_advisors` security 로 보조 확인.)

- [ ] **Step 7: 커밋**

```bash
git add docs/migrations/2026-06-06-b1-auth.sql
git commit -m "feat(db): B1 인증 RPC(pgcrypto)+remember_token+컬럼권한 마이그레이션 기록

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: authenticate.ts → RPC 전환

**Files:**
- Modify: `frontend/src/session/authenticate.ts`
- Modify: `frontend/src/session/authenticate.test.ts`

- [ ] **Step 1: 실패 테스트로 재작성**

`frontend/src/session/authenticate.test.ts` 전체 교체:
```ts
import { describe, it, expect } from 'vitest';
import { authenticate, type AuthClient } from './authenticate';

// verify_login RPC 한 번만 호출 → fake rpc 로 주입
function fakeRpc(data: unknown, error: unknown = null): AuthClient {
  return { rpc: async () => ({ data, error }) } as unknown as AuthClient;
}

const APPROVED = { id: 7, shop_name: '서울꽃집', username: 'seoul', is_approved: 'Y' };

describe('authenticate (verify_login RPC)', () => {
  it('정상이면 세션을 반환한다', async () => {
    const r = await authenticate(fakeRpc(APPROVED), 'seoul', 'pw123');
    expect(r.ok).toBe(true);
    expect(r.session).toEqual({ shopKey: 7, shopName: '서울꽃집', username: 'seoul' });
  });

  it('불일치(null)면 일반화 에러', async () => {
    const r = await authenticate(fakeRpc(null), 'seoul', 'wrong');
    expect(r.ok).toBe(false);
    expect(r.session).toBeUndefined();
  });

  it('미승인 계정은 승인대기 에러', async () => {
    const r = await authenticate(fakeRpc({ ...APPROVED, is_approved: 'N' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
    expect(r.error).toContain('승인');
  });

  it('RPC 에러면 실패를 반환한다', async () => {
    const r = await authenticate(fakeRpc(null, { message: 'boom' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: FAIL — 기존 `authenticate`는 `.from()` 계약이라 `fakeRpc`(rpc만 가짐)로 호출 시 타입/런타임 불일치.

- [ ] **Step 3: authenticate.ts 교체**

`frontend/src/session/authenticate.ts` 전체 교체:
```ts
export interface Session {
  shopKey: number;
  shopName: string;
  username: string;
}

export interface AuthResult {
  ok: boolean;
  session?: Session;
  error?: string;
}

// authenticate 가 필요로 하는 최소 supabase 계약(verify_login RPC, 테스트 주입용)
export interface AuthClient {
  rpc(fn: string, args: Record<string, unknown>): Promise<{ data: unknown; error: unknown }>;
}

const GENERIC_ERROR = '아이디 또는 비밀번호가 올바르지 않습니다';

interface VerifyLoginRow {
  id: number;
  shop_name: string;
  username: string;
  is_approved: string;
}

export async function authenticate(
  client: AuthClient,
  username: string,
  password: string,
): Promise<AuthResult> {
  const { data, error } = await client.rpc('verify_login', {
    p_username: username,
    p_password: password,
  });

  if (error) return { ok: false, error: '로그인 중 오류가 발생했습니다' };

  const row = data as VerifyLoginRow | null;
  if (!row) return { ok: false, error: GENERIC_ERROR };
  if (row.is_approved !== 'Y') return { ok: false, error: '승인 대기 중인 계정입니다' };

  return {
    ok: true,
    session: { shopKey: row.id, shopName: row.shop_name, username: row.username },
  };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: PASS. (crypto 3 + authenticate 4 + 기타 = 전부 green.)

- [ ] **Step 5: 타입검사 + 커밋**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: `session/authenticate.ts`·`SessionContext.tsx` 신규 에러 0. (SessionContext는 여전히 `supabase as unknown as AuthClient` 캐스트라 호환 — Step 검증만, 수정 없음.)
```bash
git add frontend/src/session/authenticate.ts frontend/src/session/authenticate.test.ts
git commit -m "refactor(frontend): authenticate 를 verify_login RPC 호출로 전환

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Electron 보안 저장소 (remember_token)

**Files:**
- Modify: `frontend/src/main/index.ts`
- Modify: `frontend/src/main/preload.ts`
- Modify: `frontend/src/types/electron.d.ts`

> 프레젠테이션·main 프로세스라 Vitest 대상 아님. `npm run build`로 검증.

- [ ] **Step 1: main 에 auth IPC 추가**

`frontend/src/main/index.ts` 상단 import 교체(파일 1행):
```ts
import { app, BrowserWindow, ipcMain, safeStorage } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { exec } from 'child_process';
```
그리고 파일 **맨 끝**에 추가:
```ts
// ==========================================
// IPC 통신 채널 등록 (remember_token 보안 저장)
// ==========================================

function tokenFilePath(): string {
  return path.join(app.getPath('userData'), 'remember.bin');
}

// 자동로그인 토큰 저장 (OS 암호화)
ipcMain.handle('auth:save', async (_e, payload: { userId: number; token: string }) => {
  try {
    if (!safeStorage.isEncryptionAvailable()) return { success: false, error: 'NO_ENCRYPTION' };
    const enc = safeStorage.encryptString(JSON.stringify(payload));
    fs.writeFileSync(tokenFilePath(), enc);
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});

// 자동로그인 토큰 로드
ipcMain.handle('auth:load', async () => {
  try {
    const p = tokenFilePath();
    if (!fs.existsSync(p) || !safeStorage.isEncryptionAvailable()) return null;
    const dec = safeStorage.decryptString(fs.readFileSync(p));
    return JSON.parse(dec) as { userId: number; token: string };
  } catch {
    return null;
  }
});

// 자동로그인 토큰 삭제
ipcMain.handle('auth:clear', async () => {
  try {
    const p = tokenFilePath();
    if (fs.existsSync(p)) fs.unlinkSync(p);
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});
```

- [ ] **Step 2: preload 노출**

`frontend/src/main/preload.ts` 전체 교체:
```ts
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  startService: () => ipcRenderer.invoke('service:start'),
  stopService: () => ipcRenderer.invoke('service:stop'),
  getServiceStatus: () => ipcRenderer.invoke('service:status'),
  saveRememberToken: (userId: number, token: string) =>
    ipcRenderer.invoke('auth:save', { userId, token }),
  loadRememberToken: () => ipcRenderer.invoke('auth:load'),
  clearRememberToken: () => ipcRenderer.invoke('auth:clear'),
});
```

- [ ] **Step 3: 타입 선언 추가**

`frontend/src/types/electron.d.ts` 의 `electronAPI?: { ... }` 블록에 3개 메서드 추가(기존 3개 아래):
```ts
      saveRememberToken(userId: number, token: string): Promise<{ success: boolean; error?: string }>;
      loadRememberToken(): Promise<{ userId: number; token: string } | null>;
      clearRememberToken(): Promise<{ success: boolean; error?: string }>;
```

- [ ] **Step 4: 빌드 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm run build`
Expected: 성공(tsc main + vite). main 프로세스 타입 에러 0.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/main/index.ts frontend/src/main/preload.ts frontend/src/types/electron.d.ts
git commit -m "feat(frontend): Electron safeStorage 기반 remember_token IPC

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: SessionContext 자동로그인 + restoreSession 순수 로직

**Files:**
- Create: `frontend/src/session/rememberToken.ts`
- Create: `frontend/src/session/rememberToken.test.ts`
- Modify: `frontend/src/session/SessionContext.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/session/rememberToken.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { restoreSession, type RpcLike, type TokenStore } from './rememberToken';

function fakeRpc(data: unknown, error: unknown = null): RpcLike {
  return { rpc: async () => ({ data, error }) };
}
function fakeStore(saved: { userId: number; token: string } | null) {
  return { load: vi.fn(async () => saved), clear: vi.fn(async () => {}) } as TokenStore & {
    load: ReturnType<typeof vi.fn>; clear: ReturnType<typeof vi.fn>;
  };
}

describe('restoreSession', () => {
  it('저장 토큰이 없으면 null', async () => {
    const store = fakeStore(null);
    expect(await restoreSession(fakeRpc(null), store)).toBeNull();
    expect(store.clear).not.toHaveBeenCalled();
  });

  it('검증 성공이면 세션 반환', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    const r = await restoreSession(fakeRpc({ id: 7, shop_name: '서울꽃집', username: 'seoul' }), store);
    expect(r).toEqual({ shopKey: 7, shopName: '서울꽃집', username: 'seoul' });
  });

  it('검증 실패(null)면 null + 로컬 토큰 정리', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    expect(await restoreSession(fakeRpc(null), store)).toBeNull();
    expect(store.clear).toHaveBeenCalled();
  });

  it('RPC 에러면 null + 로컬 토큰 정리', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    expect(await restoreSession(fakeRpc(null, { message: 'boom' }), store)).toBeNull();
    expect(store.clear).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: FAIL — `./rememberToken` 모듈 없음.

- [ ] **Step 3: rememberToken.ts 구현**

`frontend/src/session/rememberToken.ts`:
```ts
import type { Session } from './authenticate';

export interface RpcLike {
  rpc(fn: string, args: Record<string, unknown>): Promise<{ data: unknown; error: unknown }>;
}

export interface TokenStore {
  load(): Promise<{ userId: number; token: string } | null>;
  clear(): Promise<void>;
}

interface RememberRow {
  id: number;
  shop_name: string;
  username: string;
}

/**
 * 로컬 저장 토큰으로 세션을 복원한다. 토큰 없으면 null,
 * 검증 실패/에러면 로컬 토큰을 정리하고 null.
 */
export async function restoreSession(rpc: RpcLike, store: TokenStore): Promise<Session | null> {
  const saved = await store.load();
  if (!saved) return null;

  const { data, error } = await rpc.rpc('verify_remember_token', {
    p_user_id: saved.userId,
    p_token: saved.token,
  });

  if (error || !data) {
    await store.clear();
    return null;
  }
  const row = data as RememberRow;
  return { shopKey: row.id, shopName: row.shop_name, username: row.username };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: PASS (crypto 3 + authenticate 4 + rememberToken 4).

- [ ] **Step 5: SessionContext 개편**

`frontend/src/session/SessionContext.tsx` 전체 교체:
```tsx
import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { supabase } from '../supabase';
import { authenticate, type Session, type AuthResult, type AuthClient } from './authenticate';
import { restoreSession, type RpcLike, type TokenStore } from './rememberToken';

interface SessionContextValue {
  session: Session | null;
  authReady: boolean; // 자동로그인 검증 완료 여부(셸 로딩 게이팅)
  login: (username: string, password: string, rememberMe?: boolean) => Promise<AuthResult>;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// supabase 의 .rpc() 는 구조적으로 AuthClient/RpcLike 를 만족(타입은 단일 캐스트)
const rpcClient = supabase as unknown as AuthClient & RpcLike;

// Electron safeStorage 어댑터(웹 dev 에서는 무음 skip)
const electronStore: TokenStore = {
  load: async () => (await window.electronAPI?.loadRememberToken?.()) ?? null,
  clear: async () => { await window.electronAPI?.clearRememberToken?.(); },
};

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);

  // 앱 시작 1회: 자동로그인 시도
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const restored = await restoreSession(rpcClient, electronStore);
        if (active && restored) setSession(restored);
      } finally {
        if (active) setAuthReady(true);
      }
    })();
    return () => { active = false; };
  }, []);

  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const result = await authenticate(rpcClient, username, password);
    if (result.ok && result.session) {
      setSession(result.session);
      if (rememberMe && window.electronAPI?.saveRememberToken) {
        const { data } = await rpcClient.rpc('issue_remember_token', { p_user_id: result.session.shopKey });
        if (typeof data === 'string') await window.electronAPI.saveRememberToken(result.session.shopKey, data);
      }
    }
    return result;
  }, []);

  const logout = useCallback(() => {
    if (session) void rpcClient.rpc('clear_remember_token', { p_user_id: session.shopKey });
    void window.electronAPI?.clearRememberToken?.();
    setSession(null);
  }, [session]);

  return (
    <SessionContext.Provider value={{ session, authReady, login, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession 은 SessionProvider 내부에서만 사용해야 합니다.');
  return ctx;
}
```

- [ ] **Step 6: 타입검사 + 테스트 + 커밋**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test && npx tsc -p tsconfig.app.json --noEmit`
Expected: 테스트 11 green, 신규 파일 tsc 에러 0. (login.tsx 는 `login(u,p)` 2인자 호출 유지 — rememberMe 기본값으로 호환.)
```bash
git add frontend/src/session/rememberToken.ts frontend/src/session/rememberToken.test.ts frontend/src/session/SessionContext.tsx
git commit -m "feat(frontend): 자동로그인(restoreSession)+remember_token 수명주기+authReady

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 회원가입 화면 (검증 + 주소찾기 + signup.tsx)

**Files:**
- Create: `frontend/src/signup/validate.ts`
- Create: `frontend/src/signup/validate.test.ts`
- Create: `frontend/src/utils/daumPostcode.ts`
- Create: `frontend/src/views/signup.tsx`

- [ ] **Step 1: 검증 실패 테스트**

`frontend/src/signup/validate.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { validateSignup, type SignupForm } from './validate';

const OK: SignupForm = {
  username: 'seoul', password: 'pw123456', passwordConfirm: 'pw123456',
  shopName: '서울꽃집', representativeName: '홍길동', mobile: '01012345678', email: 'a@b.com',
};

describe('validateSignup', () => {
  it('정상 폼은 null(에러 없음)', () => {
    expect(validateSignup(OK)).toBeNull();
  });
  it('필수값(아이디) 누락 시 에러', () => {
    expect(validateSignup({ ...OK, username: '' })).toContain('아이디');
  });
  it('비밀번호 불일치 시 에러', () => {
    expect(validateSignup({ ...OK, passwordConfirm: 'different' })).toContain('비밀번호');
  });
  it('이메일 형식 오류 시 에러', () => {
    expect(validateSignup({ ...OK, email: 'not-an-email' })).toContain('이메일');
  });
  it('이메일 미입력은 허용(선택값)', () => {
    expect(validateSignup({ ...OK, email: '' })).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: FAIL — `./validate` 없음.

- [ ] **Step 3: validate.ts 구현**

`frontend/src/signup/validate.ts`:
```ts
export interface SignupForm {
  username: string;
  password: string;
  passwordConfirm: string;
  shopName: string;
  representativeName: string;
  mobile: string;
  email?: string;
  landline?: string;
  address?: string;
  addressDetail?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** 검증 통과 시 null, 실패 시 사용자 메시지 반환. */
export function validateSignup(f: SignupForm): string | null {
  if (!f.username.trim()) return '아이디를 입력해주세요';
  if (!f.password) return '비밀번호를 입력해주세요';
  if (f.password !== f.passwordConfirm) return '비밀번호가 일치하지 않습니다';
  if (!f.shopName.trim()) return '꽃집명을 입력해주세요';
  if (!f.representativeName.trim()) return '대표자명을 입력해주세요';
  if (!f.mobile.trim()) return '핸드폰 번호를 입력해주세요';
  if (f.email && !EMAIL_RE.test(f.email)) return '이메일 형식이 올바르지 않습니다';
  return null;
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: PASS (crypto 3 + authenticate 4 + rememberToken 4 + validate 5 = 16).

- [ ] **Step 5: 주소찾기 로더**

`frontend/src/utils/daumPostcode.ts`:
```ts
// 다음(카카오) 우편번호 서비스 동적 로더. 실패 시 reject → 호출부에서 수기 입력 폴백.
const SCRIPT_SRC = 'https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';

interface DaumPostcodeResult {
  zonecode: string;
  roadAddress: string;
  jibunAddress: string;
}
interface DaumPostcode {
  new (opts: { oncomplete: (data: DaumPostcodeResult) => void }): { open: () => void };
}
declare global {
  interface Window {
    daum?: { Postcode: DaumPostcode };
  }
}

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.daum?.Postcode) return resolve();
    const s = document.createElement('script');
    s.src = SCRIPT_SRC;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('주소찾기 스크립트 로드 실패'));
    document.head.appendChild(s);
  });
}

/** 우편번호 검색 팝업을 열고 선택된 주소를 반환한다. */
export async function openPostcodeSearch(): Promise<{ zonecode: string; address: string }> {
  await loadScript();
  return new Promise((resolve) => {
    new window.daum!.Postcode({
      oncomplete: (data) => resolve({ zonecode: data.zonecode, address: data.roadAddress || data.jibunAddress }),
    }).open();
  });
}
```

- [ ] **Step 6: signup.tsx 구현**

`frontend/src/views/signup.tsx`:
```tsx
import React, { useState } from 'react';
import { supabase } from '../supabase';
import { validateSignup, type SignupForm } from '../signup/validate';
import { openPostcodeSearch } from '../utils/daumPostcode';

const EMPTY: SignupForm = {
  username: '', password: '', passwordConfirm: '', shopName: '',
  representativeName: '', mobile: '', email: '', landline: '', address: '', addressDetail: '',
};

const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function SignupView({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState<SignupForm>(EMPTY);
  const [dupMsg, setDupMsg] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (k: keyof SignupForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));

  // PRD 6-1: 엔터 시 다음 입력으로 포커스 이동
  const focusNext = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const form = (e.target as HTMLElement).closest('form');
    if (!form) return;
    const fields = Array.from(form.querySelectorAll<HTMLInputElement>('input:not([type=checkbox])'));
    const i = fields.indexOf(e.target as HTMLInputElement);
    if (i >= 0 && i < fields.length - 1) fields[i + 1].focus();
  };

  const checkUsername = async () => {
    setDupMsg('');
    if (!f.username.trim()) { setDupMsg('아이디를 입력해주세요'); return; }
    const { data, error: e } = await supabase.rpc('check_username', { p_username: f.username.trim() });
    if (e) { setDupMsg('확인 중 오류가 발생했습니다'); return; }
    setDupMsg(data ? '이미 사용 중인 아이디입니다' : '사용 가능한 아이디입니다');
  };

  const findAddress = async () => {
    try {
      const r = await openPostcodeSearch();
      setF((p) => ({ ...p, address: r.address }));
    } catch {
      setError('주소찾기를 열 수 없습니다. 주소를 직접 입력해주세요.');
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const v = validateSignup(f);
    if (v) { setError(v); return; }
    setBusy(true);
    const { error: e2 } = await supabase.rpc('signup_member', {
      p_username: f.username.trim(), p_password: f.password, p_shop_name: f.shopName.trim(),
      p_representative_name: f.representativeName.trim(), p_landline: f.landline || null,
      p_mobile: f.mobile.trim(), p_email: f.email || null, p_address: f.address || null,
      p_address_detail: f.addressDetail || null,
    });
    setBusy(false);
    if (e2) {
      setError(/USERNAME_TAKEN/.test(e2.message) ? '이미 사용 중인 아이디입니다' : '회원가입 중 오류가 발생했습니다');
      return;
    }
    alert('회원가입이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.');
    onDone();
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <form onSubmit={submit} className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">회원가입</div>

        <div className="flex gap-2">
          <input value={f.username} onChange={set('username')} onKeyDown={focusNext} placeholder="아이디" autoFocus className={INPUT} />
          <button type="button" onClick={checkUsername} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">중복확인</button>
        </div>
        {dupMsg && <div className="text-xs text-brand-text-muted">{dupMsg}</div>}

        <input value={f.password} onChange={set('password')} onKeyDown={focusNext} type="password" placeholder="비밀번호" className={INPUT} />
        <input value={f.passwordConfirm} onChange={set('passwordConfirm')} onKeyDown={focusNext} type="password" placeholder="비밀번호 확인" className={INPUT} />
        <input value={f.shopName} onChange={set('shopName')} onKeyDown={focusNext} placeholder="꽃집명" className={INPUT} />
        <input value={f.representativeName} onChange={set('representativeName')} onKeyDown={focusNext} placeholder="대표자명" className={INPUT} />
        <input value={f.landline} onChange={set('landline')} onKeyDown={focusNext} placeholder="전화(선택)" className={INPUT} />

        <div className="flex gap-2">
          <input value={f.mobile} onChange={set('mobile')} onKeyDown={focusNext} placeholder="핸드폰" className={INPUT} />
          <button type="button" disabled title="다음 단계(B2)에서 제공됩니다" className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-muted opacity-50 cursor-not-allowed">인증</button>
        </div>

        <input value={f.email} onChange={set('email')} onKeyDown={focusNext} placeholder="이메일(선택)" className={INPUT} />

        <div className="flex gap-2">
          <input value={f.address} onChange={set('address')} onKeyDown={focusNext} placeholder="주소" className={INPUT} />
          <button type="button" onClick={findAddress} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">주소찾기</button>
        </div>
        <input value={f.addressDetail} onChange={set('addressDetail')} onKeyDown={focusNext} placeholder="상세주소(선택)" className={INPUT} />

        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button type="submit" disabled={busy} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 transition disabled:opacity-50">
          {busy ? '처리 중…' : '회원가입'}
        </button>
        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 7: 타입검사 + 커밋**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test && npx tsc -p tsconfig.app.json --noEmit`
Expected: 테스트 16 green, 신규 파일 tsc 에러 0.
```bash
git add frontend/src/signup/ frontend/src/utils/daumPostcode.ts frontend/src/views/signup.tsx
git commit -m "feat(frontend): 회원가입 화면(검증+중복확인+다음 주소찾기)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: App 통합 (authReady 게이팅 + signup 배선 + login autoLogin) + 검증

**Files:**
- Modify: `frontend/src/views/login.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: login.tsx autoLogin 배선**

`frontend/src/views/login.tsx` 의 `submit` 핸들러에서 `login` 호출을 3인자로 변경:
```tsx
    const r = await login(username.trim(), password, autoLogin);
```
(다른 부분은 변경 없음 — `autoLogin` 상태는 이미 존재.)

- [ ] **Step 2: App.tsx authReady 게이팅 + signup 임포트 교체**

`frontend/src/App.tsx` 에서 두 곳 수정:

(a) 스텁 임포트에서 `SignupView` 제거하고 실제 화면 임포트 추가:
```tsx
import { FindIdView, FindPwView, MyPageView } from './views/_placeholders';
import { SignupView } from './views/signup';
```

(b) `Shell()` 에서 `authReady` 사용 — `useSession()` 구조분해에 추가하고, 자동로그인 검증 전 로딩 표출:
```tsx
  const { session, authReady, logout } = useSession();
```
그리고 `return (`의 `<main>` 첫 줄에 게이팅 추가(기존 라우트 분기 위):
```tsx
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!authReady && (
          <div className="flex-1 flex items-center justify-center text-brand-text-muted text-sm">불러오는 중…</div>
        )}
        {authReady && !session && route === 'home' && <HomeView onLogin={() => setRoute('login')} onSignup={() => setRoute('signup')} />}
        {authReady && !session && route === 'login' && <LoginView onFindId={() => setRoute('findId')} onFindPw={() => setRoute('findPw')} />}
        {authReady && !session && route === 'signup' && <SignupView onDone={() => setRoute('login')} />}
        {authReady && !session && route === 'findId' && <FindIdView />}
        {authReady && !session && route === 'findPw' && <FindPwView />}

        {authReady && session && route === 'dashboard' && <DashboardView />}
        {authReady && session && route === 'orders' && <OrderListView />}
        {authReady && session && route === 'settings' && <SettingsView />}
        {authReady && session && route === 'mypage' && <MyPageView />}
      </main>
```
(기존 9개 라우트 줄을 위 블록으로 교체. `SignupView` 는 `onDone` prop 추가.)

- [ ] **Step 3: 타입검사 + 테스트 + 빌드**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test && npm run build`
Expected: 테스트 16 green, tsc(main) 0, vite build 성공.

- [ ] **Step 4: 수동 검증 (개발 모드)**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm run dev`
체크(육안, 라이브 DB 필요):
1. 시작 시 "불러오는 중…" 잠깐 후 HOME(자동로그인 토큰 없으면).
2. [회원가입] → 폼. [중복확인](실제 RPC), 필수값/비번불일치 인라인 에러, [주소찾기] 팝업. 제출 → "승인 후 로그인" 안내 → 로그인 복귀. (Supabase `member_info` 에 `is_approved='N'` 행 생성 확인.)
3. 해당 계정 `is_approved='Y'` 수동 변경 후 로그인 → 셸 진입.
4. [자동로그인] 체크 후 로그인 → 앱 재시작 시 로그인 화면 건너뛰고 바로 셸(remember_token 동작). Electron 패키지가 아닌 순수 web dev 면 자동로그인은 skip(정상).
5. [로그아웃] → 토큰 정리 + HOME 복귀. 재시작 시 자동로그인 안 됨.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/views/login.tsx frontend/src/App.tsx
git commit -m "feat(frontend): App authReady 게이팅 + 회원가입 배선 + 자동로그인 체크박스 연결

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 6: finishing-a-development-branch**

`superpowers:finishing-a-development-branch` 로 머지/PR 옵션 제시.

---

## 라이브/후속 메모 (B1 범위 밖)
- 핸드폰 OTP 인프라(Supabase Edge Function + SMS 제공사), 가입 폰 실인증(F2), 아이디/비번 찾기(F4), 마이페이지 재인증(F5) → **B2**.
- 관리자 승인 UI → 현재 수동(`is_approved` DB 갱신).
- C/D/E(대시보드·조회·설정 정교화) → 별도.
- 다음 우편번호 스크립트는 외부 로드 — Electron 패키지 CSP/오프라인 환경에서 로드 가능 여부는 라이브 검증 항목.
