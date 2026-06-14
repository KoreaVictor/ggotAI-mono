# ggotAIya 서브프로젝트 A (기반·셸·암호화 수정) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ggotAIya에 로그인 게이트 셸(상단 헤더) + 인메모리 세션 + 최소 ID/PW 로그인 + HOME을 세우고, AES 암호화 키 계약 버그를 수정(+decrypt)하며 공유 타입을 도입한다.

**Architecture:** 새 라우팅 의존성 없이 React Context(`SessionContext`)로 세션을 들고, 최상위 `App`이 로그인 상태에 따라 로그인 전/후 셸을 분기한다(접근법 1). 인증 로직은 순수 함수 `authenticate()`로 분리해 단위 테스트한다. 암호화는 crypto-js를 백엔드 `bytes.fromhex` 계약(hex 키)에 맞춘다.

**Tech Stack:** React 19 + Vite + Electron + Tailwind v4 + @supabase/supabase-js + crypto-js + **Vitest(신규 도입)** + lucide-react.

**Branch:** `feature/ggotaiya-foundations` (master에서 분기).

**작업 디렉터리:** `frontend/` (모든 npm 명령은 `cd frontend`에서; Bash 툴은 `cd /c/ggotAI/ggotAIorder/frontend`).

**설계서:** `docs/superpowers/specs/2026-06-05-ggotaiya-foundations-design.md`

---

## 사전 참고 (구현자 필독)

- 기존 셸 `frontend/src/App.tsx`는 **사이드바**(로그인 없음, `shop_key=1` 하드코딩)다. 이 작업에서 **상단 헤더 셸 + 로그인 게이트**로 대체한다.
- 기존 뷰 `views/{dashboard,order_list,settings}.tsx`의 **내부는 건드리지 않는다**(로그인 후 셸에서 그대로 렌더만). settings는 `encryptPassword`를 쓰므로 Task 1의 crypto 수정만으로 자동 계약-호환된다.
- 브랜드 Tailwind 토큰(기존 App.tsx에서 사용 중, 그대로 재사용): `bg-brand-bg`, `bg-brand-card`, `bg-brand-card-hover`, `border-brand-border`, `bg-brand-primary`, `text-brand-text-primary`, `text-brand-text-secondary`, `text-brand-text-muted`, `text-brand-success`, `text-brand-error`, `font-display`, `font-sans`.
- `.env`에 `VITE_AES_ENCRYPTION_KEY`(64 hex) 존재 확인됨.
- 빌드 검증: `npm run build`(= `tsc -p tsconfig.main.json && vite build`). 타입 에러 0이어야 함.

---

## Task 1: Vitest 도입 + AES 암호화 계약 버그 수정

**Files:**
- Modify: `frontend/package.json` (devDep `vitest` + `"test"` 스크립트)
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/utils/crypto.test.ts`
- Modify: `frontend/src/utils/crypto.ts`

- [ ] **Step 1: Vitest 설치 + 스크립트**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm install -D vitest`
그 다음 `frontend/package.json`의 `"scripts"`에 `"test": "vitest run"` 한 줄 추가 (기존 줄들 사이, 예: `"preview"` 위):
```json
    "test": "vitest run",
```

- [ ] **Step 2: vitest 설정 생성**

`frontend/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config';

// crypto/authenticate 는 순수 TS(JSX 없음) → node 환경으로 충분.
export default defineConfig({
  test: {
    environment: 'node',
  },
});
```

- [ ] **Step 3: 실패 테스트 작성**

`frontend/src/utils/crypto.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { encryptPassword, decryptPassword } from './crypto';

// 백엔드 crypto.py(bytes.fromhex) 와 동일 키
const KEY = '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff';

describe('AES crypto (백엔드 hex 계약 호환)', () => {
  it('encrypt→decrypt 라운드트립으로 원문을 복원한다', () => {
    const plain = 'ggot비밀!Pass_가나다';
    const enc = encryptPassword(plain, KEY);
    expect(enc).toContain(':');               // iv_hex:base64 포맷
    expect(decryptPassword(enc, KEY)).toBe(plain);
  });

  it('백엔드(crypto.py)가 만든 고정 벡터를 복호화한다 (hex 계약 실증)', () => {
    // 백엔드 encrypt("Ggot!Pass123", KEY, iv=00..0f) 로 생성한 결정적 벡터
    const VECTOR = '000102030405060708090a0b0c0d0e0f:cUzGelhg3Ctci6t160pS2g==';
    expect(decryptPassword(VECTOR, KEY)).toBe('Ggot!Pass123');
  });

  it('빈 입력은 빈 문자열을 반환한다', () => {
    expect(encryptPassword('', KEY)).toBe('');
    expect(decryptPassword('', KEY)).toBe('');
  });
});
```

- [ ] **Step 4: 실패 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: FAIL — 현재 `crypto.ts`는 `decryptPassword`가 없어 import 에러, 그리고 키를 `Utf8.parse`로 만들어 벡터 복호 실패.

- [ ] **Step 5: crypto.ts 수정**

`frontend/src/utils/crypto.ts` 전체를 교체:
```ts
import CryptoJS from 'crypto-js';

const ENV_KEY = import.meta.env.VITE_AES_ENCRYPTION_KEY as string | undefined;

/**
 * 64자 hex 키 문자열을 32바이트 WordArray 로 파싱한다.
 * 백엔드(Python `bytes.fromhex`)와 동일한 키여야 호환된다.
 */
function parseKey(key: string | undefined): CryptoJS.lib.WordArray {
  if (!key) throw new Error('AES 키가 없습니다 (VITE_AES_ENCRYPTION_KEY).');
  return CryptoJS.enc.Hex.parse(key);
}

/**
 * 평문을 AES-256-CBC(PKCS7) 로 암호화해 "iv_hex:ciphertext_base64" 를 반환한다.
 * key 미지정 시 환경변수 키 사용(테스트는 명시 키 주입).
 */
export function encryptPassword(plainText: string, key: string | undefined = ENV_KEY): string {
  if (!plainText) return '';
  try {
    const wKey = parseKey(key);
    const iv = CryptoJS.lib.WordArray.random(16);
    const encrypted = CryptoJS.AES.encrypt(plainText, wKey, {
      iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });
    return `${iv.toString(CryptoJS.enc.Hex)}:${encrypted.toString()}`;
  } catch (error) {
    console.error('암호화 실패:', error);
    return '';
  }
}

/**
 * "iv_hex:ciphertext_base64" 를 복호화해 평문을 반환한다(눈 아이콘 가시화용).
 * 실패 시 빈 문자열.
 */
export function decryptPassword(dbValue: string, key: string | undefined = ENV_KEY): string {
  if (!dbValue) return '';
  try {
    const wKey = parseKey(key);
    const sep = dbValue.indexOf(':');
    if (sep < 0) return '';
    const iv = CryptoJS.enc.Hex.parse(dbValue.slice(0, sep));
    const cipherText = dbValue.slice(sep + 1);
    const decrypted = CryptoJS.AES.decrypt(cipherText, wKey, {
      iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });
    return decrypted.toString(CryptoJS.enc.Utf8);
  } catch (error) {
    console.error('복호화 실패:', error);
    return '';
  }
}
```

- [ ] **Step 6: 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: PASS (3 tests). 특히 고정 벡터 복호화가 통과 = 백엔드 hex 계약 호환 실증.

- [ ] **Step 7: 커밋**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/utils/crypto.ts frontend/src/utils/crypto.test.ts
git commit -m "fix(frontend): AES 키 hex 계약 수정 + decryptPassword + Vitest 도입

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 공유 타입 (db.ts + electron.d.ts)

**Files:**
- Create: `frontend/src/types/db.ts`
- Create: `frontend/src/types/electron.d.ts`

- [ ] **Step 1: DB Row 타입 작성**

`frontend/src/types/db.ts` (`docs/database_schema.sql` 컬럼 기준):
```ts
// Supabase 4개 테이블 Row 타입 (docs/database_schema.sql 기준)

export interface MemberInfo {
  id: number;
  username: string;
  password: string;
  shop_name: string;
  representative_name: string;
  landline_number: string | null;
  mobile_number: string;
  email: string | null;
  address: string | null;
  address_detail: string | null;
  is_approved: 'Y' | 'N';
  created_at: string;
}

export interface ServerCallHistory {
  id: number;
  channel_order: string;
  channel_classification: string;
  shop_key: number;
  shop_name: string;
  customer_phone_number: string;
  customer_name: string;
  call_date: string;
  call_time: string;
  duration_seconds: number;
  audio_file_name: string | null;
  stt_text: string | null;
  is_order: 'Y' | 'N';
  created_at: string;
}

export interface OrderDetails {
  id: number;
  call_history_id: number;
  shop_key: number;
  shop_name: string;
  customer_name: string;
  customer_phone_number: string;
  product_name: string;
  quantity: number;
  price: number;
  delivery_at: string;
  delivery_place: string;
  receiver_name: string;
  receiver_phone_number: string;
  ribbon_sender: string | null;
  ribbon_congratulations: string | null;
  card_message: string | null;
  rpa_status: 'ready' | 'success' | 'fail';
  created_at: string;
}

export interface SettingInfo {
  id: number;
  shop_key: number;
  use_notification: 'Y' | 'N';
  notification_phone_number: string | null;
  rpa_success_message: string;
  rpa_fail_message: string;
  order_hp_1: string;
  order_hp_2: string | null;
  order_landline_1: string | null;
  order_landline_2: string | null;
  shopping_mall_url: string | null;
  shopping_mall_id: string | null;
  shopping_mall_password: string | null;
  intranet_url: string | null;
  intranet_id: string | null;
  intranet_password: string | null;
  shopping_mall_check_interval: number;
  intranet_check_interval: number;
  created_at: string;
}
```

- [ ] **Step 2: electron API 타입 선언**

`frontend/src/types/electron.d.ts`:
```ts
export {};

export type ServiceStatus = 'RUNNING' | 'STOPPED' | 'NOT_INSTALLED';

declare global {
  interface Window {
    electronAPI?: {
      startService(): Promise<{ success: boolean; error?: string }>;
      stopService(): Promise<{ success: boolean; error?: string }>;
      getServiceStatus(): Promise<{ status: ServiceStatus; error?: string }>;
    };
  }
}
```

- [ ] **Step 3: 타입 검사 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: 에러 0 (신규 타입만 추가, 기존 코드 영향 없음).

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/types/db.ts frontend/src/types/electron.d.ts
git commit -m "feat(frontend): Supabase Row 타입 + window.electronAPI 타입 선언

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 인증 로직(authenticate) + SessionContext

**Files:**
- Create: `frontend/src/session/authenticate.ts`
- Create: `frontend/src/session/authenticate.test.ts`
- Create: `frontend/src/session/SessionContext.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/session/authenticate.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { authenticate, type AuthClient } from './authenticate';

function fakeClient(row: unknown, error: unknown = null): AuthClient {
  return {
    from: () => ({
      select: () => ({
        eq: () => ({
          maybeSingle: async () => ({ data: row, error }),
        }),
      }),
    }),
  } as unknown as AuthClient;
}

const APPROVED = {
  id: 7, shop_name: '서울꽃집', username: 'seoul', password: 'pw123', is_approved: 'Y',
};

describe('authenticate', () => {
  it('정상 자격증명이면 세션을 반환한다', async () => {
    const r = await authenticate(fakeClient(APPROVED), 'seoul', 'pw123');
    expect(r.ok).toBe(true);
    expect(r.session).toEqual({ shopKey: 7, shopName: '서울꽃집', username: 'seoul' });
  });

  it('비밀번호 불일치면 일반화 에러', async () => {
    const r = await authenticate(fakeClient(APPROVED), 'seoul', 'wrong');
    expect(r.ok).toBe(false);
    expect(r.session).toBeUndefined();
  });

  it('아이디 없으면(행 없음) 일반화 에러', async () => {
    const r = await authenticate(fakeClient(null), 'nobody', 'x');
    expect(r.ok).toBe(false);
  });

  it('미승인 계정은 승인대기 에러', async () => {
    const r = await authenticate(fakeClient({ ...APPROVED, is_approved: 'N' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
    expect(r.error).toContain('승인');
  });

  it('조회 에러면 실패를 반환한다', async () => {
    const r = await authenticate(fakeClient(null, { message: 'boom' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: FAIL — `./authenticate` 모듈 없음.

- [ ] **Step 3: authenticate 구현**

`frontend/src/session/authenticate.ts`:
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

// authenticate 가 필요로 하는 최소 supabase 계약(테스트 주입용)
export interface AuthClient {
  from(table: string): {
    select(cols: string): {
      eq(col: string, val: string): {
        maybeSingle(): Promise<{ data: unknown; error: unknown }>;
      };
    };
  };
}

const GENERIC_ERROR = '아이디 또는 비밀번호가 올바르지 않습니다';

interface MemberRow {
  id: number;
  shop_name: string;
  username: string;
  password: string;
  is_approved: string;
}

export async function authenticate(
  client: AuthClient,
  username: string,
  password: string,
): Promise<AuthResult> {
  const { data, error } = await client
    .from('member_info')
    .select('id, shop_name, username, password, is_approved')
    .eq('username', username)
    .maybeSingle();

  if (error) return { ok: false, error: '로그인 중 오류가 발생했습니다' };

  const row = data as MemberRow | null;
  if (!row || row.password !== password) return { ok: false, error: GENERIC_ERROR };
  if (row.is_approved !== 'Y') return { ok: false, error: '승인 대기 중인 계정입니다' };

  return {
    ok: true,
    session: { shopKey: row.id, shopName: row.shop_name, username: row.username },
  };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test`
Expected: PASS (crypto 3 + authenticate 5 = 8 tests).

- [ ] **Step 5: SessionContext 구현**

`frontend/src/session/SessionContext.tsx`:
```tsx
import React, { createContext, useContext, useState, useCallback } from 'react';
import { supabase } from '../supabase';
import { authenticate, type Session, type AuthResult } from './authenticate';

interface SessionContextValue {
  session: Session | null;
  login: (username: string, password: string) => Promise<AuthResult>;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  const login = useCallback(async (username: string, password: string) => {
    const result = await authenticate(supabase, username, password);
    if (result.ok && result.session) setSession(result.session);
    return result;
  }, []);

  const logout = useCallback(() => setSession(null), []);

  return (
    <SessionContext.Provider value={{ session, login, logout }}>
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

- [ ] **Step 6: 타입 검사 + 커밋**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: 에러 0.
```bash
git add frontend/src/session/
git commit -m "feat(frontend): 인증 로직 authenticate + SessionContext(인메모리 세션)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 셸 컴포넌트 (TopHeader, HOME, 로그인, 스텁)

**Files:**
- Create: `frontend/src/shell/TopHeader.tsx`
- Create: `frontend/src/views/home.tsx`
- Create: `frontend/src/views/login.tsx`
- Create: `frontend/src/views/_placeholders.tsx`

> 이 Task의 컴포넌트는 프레젠테이션 위주라 단위테스트 대신 `npm run build`(Task 5) 로 검증한다. 라우트 타입은 Task 5의 App.tsx와 공유하므로 아래 시그니처를 정확히 지킬 것.

공유 라우트 타입(아래 컴포넌트와 App.tsx가 동일하게 사용):
```ts
type PreRoute = 'home' | 'login' | 'signup' | 'findId' | 'findPw';
type PostRoute = 'dashboard' | 'orders' | 'settings' | 'mypage';
type Route = PreRoute | PostRoute;
```

- [ ] **Step 1: 스텁 화면**

`frontend/src/views/_placeholders.tsx`:
```tsx
function Stub({ title }: { title: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
      <div className="text-brand-text-primary font-display font-bold text-xl mb-2">{title}</div>
      <div className="text-brand-text-muted text-sm">이 화면은 다음 단계(인증·계정, 서브프로젝트 B)에서 제공됩니다.</div>
    </div>
  );
}

export const SignupView = () => <Stub title="회원가입" />;
export const FindIdView = () => <Stub title="아이디 찾기" />;
export const FindPwView = () => <Stub title="비밀번호 찾기" />;
export const MyPageView = () => <Stub title="마이페이지" />;
```

- [ ] **Step 2: HOME(로그인 전)**

`frontend/src/views/home.tsx`:
```tsx
import heroImg from '../assets/hero.png';

export function HomeView({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-10 gap-6">
      <img src={heroImg} alt="ggotAI 마스코트" className="w-40 h-40 object-contain opacity-90" />
      <div>
        <div className="font-display font-bold text-2xl text-brand-text-primary">ggotAI(꽃아이)</div>
        <div className="text-brand-text-secondary mt-2">24시간 든든한 우리가게 AI 직원</div>
      </div>
      <div className="flex gap-3">
        <button
          onClick={onLogin}
          className="px-6 py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm shadow-lg shadow-brand-primary/20 hover:opacity-90 transition"
        >
          로그인
        </button>
        <button
          onClick={onSignup}
          className="px-6 py-2.5 rounded-lg border border-brand-border text-brand-text-secondary font-semibold text-sm hover:bg-brand-card-hover transition"
        >
          회원가입
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 로그인 화면**

`frontend/src/views/login.tsx`:
```tsx
import React, { useState } from 'react';
import { useSession } from '../session/SessionContext';

export function LoginView({ onFindId, onFindPw }: { onFindId: () => void; onFindPw: () => void }) {
  const { login } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [autoLogin, setAutoLogin] = useState(false); // 표시만(영구화는 B)
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // PRD 6-1: 엔터 시 다음 입력으로 포커스 이동
  const focusNext = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const form = (e.target as HTMLElement).closest('form');
    if (!form) return;
    const fields = Array.from(form.querySelectorAll('input'));
    const i = fields.indexOf(e.target as HTMLInputElement);
    if (i >= 0 && i < fields.length - 1) fields[i + 1].focus();
    else (form.querySelector('button[type=submit]') as HTMLButtonElement | null)?.focus();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    const r = await login(username.trim(), password);
    setBusy(false);
    if (!r.ok) setError(r.error ?? '로그인에 실패했습니다');
  };

  return (
    <div className="flex-1 flex items-center justify-center p-10">
      <form onSubmit={submit} className="w-full max-w-sm bg-brand-card border border-brand-border rounded-2xl p-8 space-y-4">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">로그인</div>
        <input
          value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={focusNext}
          placeholder="아이디" autoFocus
          className="w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
        />
        <input
          value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={focusNext}
          type="password" placeholder="비밀번호"
          className="w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
        />
        <label className="flex items-center gap-2 text-xs text-brand-text-secondary">
          <input type="checkbox" checked={autoLogin} onChange={(e) => setAutoLogin(e.target.checked)} />
          자동로그인
        </label>
        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button
          type="submit" disabled={busy}
          className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 transition disabled:opacity-50"
        >
          {busy ? '확인 중…' : '로그인'}
        </button>
        <div className="flex justify-center gap-4 text-xs text-brand-text-muted pt-1">
          <button type="button" onClick={onFindId} className="hover:text-brand-text-secondary">아이디 찾기</button>
          <button type="button" onClick={onFindPw} className="hover:text-brand-text-secondary">비밀번호 찾기</button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: 상단 헤더**

`frontend/src/shell/TopHeader.tsx`:
```tsx
import { CircleDot } from 'lucide-react';
import type { Session } from '../session/authenticate';
import type { ServiceStatus } from '../types/electron';

type Route = 'home' | 'login' | 'signup' | 'findId' | 'findPw' | 'dashboard' | 'orders' | 'settings' | 'mypage';

interface Props {
  session: Session | null;
  route: Route;
  serviceStatus: ServiceStatus | 'LOADING';
  onNavigate: (route: Route) => void;
  onLogout: () => void;
}

const NAV: { key: Route; label: string }[] = [
  { key: 'dashboard', label: '주문접수상황판' },
  { key: 'orders', label: '주문접수조회' },
  { key: 'settings', label: '환경설정' },
];

export function TopHeader({ session, route, serviceStatus, onNavigate, onLogout }: Props) {
  return (
    <header className="h-14 bg-brand-card border-b border-brand-border flex items-center justify-between px-6 shrink-0">
      <button onClick={() => onNavigate(session ? 'dashboard' : 'home')} className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-brand-primary flex items-center justify-center">
          <span className="font-display font-bold text-white text-sm">G</span>
        </div>
        <span className="font-display font-bold text-sm text-brand-text-primary">ggotAIya</span>
      </button>

      {session && (
        <nav className="flex items-center gap-1">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => onNavigate(n.key)}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition ${
                route === n.key
                  ? 'bg-brand-primary text-white'
                  : 'text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-card-hover'
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>
      )}

      <div className="flex items-center gap-3">
        <span className="text-[11px] flex items-center gap-1 font-semibold">
          {serviceStatus === 'RUNNING' ? (
            <span className="text-brand-success flex items-center gap-1"><CircleDot className="h-3 w-3 animate-pulse" /> RUNNING</span>
          ) : (
            <span className="text-brand-error flex items-center gap-1"><CircleDot className="h-3 w-3" /> STOPPED</span>
          )}
        </span>
        {session ? (
          <>
            <span className="text-xs font-semibold text-brand-text-primary">{session.shopName}</span>
            <button onClick={() => onNavigate('mypage')} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">마이페이지</button>
            <button onClick={onLogout} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">로그아웃</button>
          </>
        ) : (
          <>
            <button onClick={() => onNavigate('login')} className="text-xs font-semibold text-brand-text-primary hover:opacity-80">로그인</button>
            <button onClick={() => onNavigate('signup')} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">회원가입</button>
          </>
        )}
      </div>
    </header>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/shell/ frontend/src/views/home.tsx frontend/src/views/login.tsx frontend/src/views/_placeholders.tsx
git commit -m "feat(frontend): 상단 헤더 셸 + HOME + 최소 로그인 + 스텁 화면

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: App.tsx 통합 (셸 분기) + 빌드·수동 검증

**Files:**
- Modify: `frontend/src/App.tsx` (전면 교체)

- [ ] **Step 1: App.tsx 교체**

`frontend/src/App.tsx` 전체를 교체:
```tsx
import { useState, useEffect } from 'react';
import { SessionProvider, useSession } from './session/SessionContext';
import { TopHeader } from './shell/TopHeader';
import { HomeView } from './views/home';
import { LoginView } from './views/login';
import { SignupView, FindIdView, FindPwView, MyPageView } from './views/_placeholders';
import { DashboardView } from './views/dashboard';
import { OrderListView } from './views/order_list';
import { SettingsView } from './views/settings';
import type { ServiceStatus } from './types/electron';

type Route = 'home' | 'login' | 'signup' | 'findId' | 'findPw' | 'dashboard' | 'orders' | 'settings' | 'mypage';

function Shell() {
  const { session, logout } = useSession();
  const [route, setRoute] = useState<Route>('home');
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | 'LOADING'>('LOADING');

  // 서비스 상태 폴링(헤더 뱃지)
  useEffect(() => {
    let active = true;
    const check = async () => {
      if (!window.electronAPI) { if (active) setServiceStatus('STOPPED'); return; }
      try {
        const res = await window.electronAPI.getServiceStatus();
        if (active) setServiceStatus(res.status);
      } catch { if (active) setServiceStatus('STOPPED'); }
    };
    check();
    const t = setInterval(check, 3000);
    return () => { active = false; clearInterval(t); };
  }, []);

  // 로그인/로그아웃 시 기본 라우트 보정
  useEffect(() => {
    setRoute(session ? 'dashboard' : 'home');
  }, [session]);

  const handleLogout = () => { logout(); };

  return (
    <div className="flex flex-col h-screen bg-brand-bg text-brand-text-primary overflow-hidden font-sans">
      <TopHeader
        session={session}
        route={route}
        serviceStatus={serviceStatus}
        onNavigate={setRoute}
        onLogout={handleLogout}
      />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!session && route === 'home' && <HomeView onLogin={() => setRoute('login')} onSignup={() => setRoute('signup')} />}
        {!session && route === 'login' && <LoginView onFindId={() => setRoute('findId')} onFindPw={() => setRoute('findPw')} />}
        {!session && route === 'signup' && <SignupView />}
        {!session && route === 'findId' && <FindIdView />}
        {!session && route === 'findPw' && <FindPwView />}

        {session && route === 'dashboard' && <DashboardView />}
        {session && route === 'orders' && <OrderListView />}
        {session && route === 'settings' && <SettingsView />}
        {session && route === 'mypage' && <MyPageView />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <Shell />
    </SessionProvider>
  );
}
```

- [ ] **Step 2: 타입검사 + 테스트 + 빌드**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm test && npm run build`
Expected: 테스트 8 passed, `tsc` 타입에러 0, `vite build` 성공.
- 만약 기존 뷰(dashboard/order_list/settings) 임포트나 미사용 변수로 빌드가 깨지면, 본 작업이 그 뷰 내부를 바꾼 게 아니므로 import 경로/시그니처만 맞춘다(뷰 내부 로직 변경 금지). 해결 불가하면 DONE_WITH_CONCERNS로 보고.

- [ ] **Step 3: 수동 검증 (개발 모드)**

Run: `cd /c/ggotAI/ggotAIorder/frontend && npm run dev`
체크(육안):
1. 시작 시 HOME(마스코트·[로그인][회원가입]) 표시, 헤더 우측 RUNNING/STOPPED 뱃지.
2. [로그인] → 로그인 폼. 잘못된 자격증명 → 에러 문구. 올바른 member_info 계정(is_approved='Y') → 로그인 후 셸로 전환.
3. 로그인 후: 헤더 내비 [주문접수상황판][주문접수조회][환경설정] 전환 동작, 우측 가게명/마이페이지/로그아웃.
4. [로그아웃] → HOME 복귀.
5. 회원가입/아이디찾기/비번찾기/마이페이지 → "준비중(B)" 스텁.
(개발 DB에 테스트 계정이 없으면 Supabase member_info에 `is_approved='Y'` 행 1개로 확인.)

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): App 셸 분기(로그인 게이트 + 상단 헤더) 통합

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: finishing-a-development-branch**

`superpowers:finishing-a-development-branch` 로 머지/PR 옵션 제시.

---

## 라이브/후속 메모 (A 범위 밖)
- 영구 자동로그인(토큰), 회원가입/찾기/OTP/마이페이지 실로직, 비밀번호 해싱 → 서브프로젝트 B.
- 기존 뷰(dashboard/orders/settings) `any` → `types/db.ts` 타입 적용은 C/D/E에서 점진.
- `npm run build` 외 Electron 패키징(.exe) E2E는 별도.
