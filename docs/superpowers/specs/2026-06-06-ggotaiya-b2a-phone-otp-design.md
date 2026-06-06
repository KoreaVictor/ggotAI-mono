# ggotAIya 서브프로젝트 B2a (핸드폰 OTP 인프라 + 가입 인증 + 아이디/비번 찾기) 설계서

> 작성일 2026-06-06. ggotAIya 인증·계정(B) 분해 중 **B2a**. 마이페이지(프로필 조회·수정 + 재인증)는 **B2b로 이월**. B1(회원가입·비번 해싱·자동로그인)에 이어짐.

## 1. 목표 (Goal)

핸드폰 OTP 인프라를 세우고, 그 위에 **가입 폰 실인증(F2)·아이디 찾기(F4 화면3)·비밀번호 찾기(F4 화면4)**를 구현한다. OTP 코드 생성·해시저장·검증은 Postgres RPC(pgcrypto, B1 패턴)에 두고, SMS 발송 비밀키가 필요한 부분만 얇은 Supabase Edge Function으로 격리한다. SMS 제공사는 추상화하고 fake로 먼저 구현(실발송은 계정 준비 시 연결).

## 2. 범위 결정 (확정된 사용자 선택)

| 결정 | 선택 | 비고 |
|------|------|------|
| SMS 제공사 | **추상화 + fake 우선** | 실발송은 계정 준비 시(B1 notifier 방식) |
| 범위 | **B2a** = OTP 인프라 + 가입 인증 + 아이디/비번 찾기 | 마이페이지 = B2b |
| 찾기 동작 | 아이디=노출, **비번=재설정**(bcrypt 재해싱) | 비번은 B1에서 해싱되어 원본 복구 불가 |
| OTP 아키텍처 | **얇은 Edge Function + 두꺼운 Postgres RPC** | 접근법 1 |

## 3. 아키텍처 개요

OTP 코드의 생성·해시저장·검증은 Postgres RPC(pgcrypto, B1과 동일 패턴)에 두고, SMS 발송 비밀키가 필요한 부분만 얇은 Edge Function으로 격리한다. 검증 성공 시 단기 **검증 토큰**을 발급하고, 후속 권한 작업(가입·아이디찾기·비번재설정)이 그 토큰을 소비한다.

**5개 작업 영역:** ① DB(테이블+RPC) ② Edge Function `send-otp`(제공사 추상화) ③ 공유 컴포넌트 `PhoneVerify` ④ 화면(find_id/find_pw/signup 수정) ⑤ 클라이언트 래퍼·테스트.

### 데이터 흐름 (예: 비밀번호 찾기)
폼(아이디+폰) → PhoneVerify → `send-otp` EF → `request_otp` RPC(코드) → SMS(fake) → 코드 입력 → `verify_otp` RPC → 토큰 → 새 비번 입력 → `reset_password(폰, 아이디, 새비번, 토큰)` → 성공.

## 4. DB (테이블 + RPC)

### 4-1. 테이블 `phone_verification`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | bigserial PK | |
| phone | text | 인증 대상 번호(정규화: 하이픈 제거) |
| purpose | text | `'signup'` / `'find_id'` / `'find_pw'` |
| code_hash | text | `crypt(code, gen_salt('bf'))` |
| expires_at | timestamptz | 코드 만료 = now()+3분 |
| attempts | int default 0 | 오답 횟수(최대 5) |
| verified | bool default false | |
| token_hash | text | 검증 성공 시 발급 토큰 해시 |
| token_expires_at | timestamptz | 토큰 만료 = now()+10분 |
| created_at | timestamptz default now() | |

- RLS 활성, anon 직접 접근 없음(모든 접근은 SECURITY DEFINER RPC 경유). 모든 함수 `set search_path = public, extensions`.
- 상수: 코드 6자리, 코드 만료 3분, 최대 시도 5회, 토큰 만료 10분, 재요청 쓰로틀 30초, 1시간 5회 상한.

### 4-2. RPC (전부 SECURITY DEFINER)
| 함수 | 권한 | 동작 |
|------|------|------|
| `request_otp(p_phone text, p_purpose text)` → text(평문 코드) | **service_role 전용**(anon ✗) | 레이트리밋(같은 phone+purpose 30초 내 재요청 차단 + 1시간 5회 상한) → 같은 phone+purpose 과거 행 정리 → 6자리 생성(`lpad((floor(random()*1000000))::int::text,6,'0')`) → 해시 저장(만료 3분, attempts 0, verified false) → 평문 코드 반환. **Edge Function만 호출** |
| `verify_otp(p_phone, p_purpose, p_code)` → json | anon | 최신 미검증 행(created_at desc) 조회 → 없음/만료 → `{ok:false, reason:'not_found'\|'expired'}` → `attempts>=5` → `{ok:false, reason:'too_many'}` → `code_hash = crypt(p_code, code_hash)` 불일치 → attempts+1, `{ok:false, reason:'mismatch'}` → 일치 → `verified=true`, 토큰(`encode(gen_random_bytes(32),'hex')`) 발급·해시 저장(10분), `{ok:true, token}` |
| `find_username(p_phone, p_shop_name, p_token)` → json | anon | 토큰 검증(purpose=find_id, verified, token 미만료, `token_hash=crypt(p_token,token_hash)`) → 실패 시 `{ok:false, reason:'invalid_token'}` → **토큰 소비**(token_expires_at=now()) → `member_info`에서 mobile_number=p_phone & shop_name=p_shop_name 인 username → `{ok:true, username}` 또는 `{ok:false, reason:'not_found'}` |
| `reset_password(p_phone, p_username, p_new_password, p_token)` → json | anon | 토큰 검증(purpose=find_pw)·소비 → `update member_info set password=crypt(p_new_password, gen_salt('bf')) where username=p_username and mobile_number=p_phone` → 영향 0행이면 `{ok:false, reason:'not_found'}` 아니면 `{ok:true}` |
| `signup_member(...)` **수정** | anon | 인자에 `p_verification_token text` 추가. 아이디 중복 체크 후 purpose=signup 토큰 검증·소비(폰=p_mobile). 실패 시 `PHONE_NOT_VERIFIED` 예외. 그 외 B1과 동일. **9인자 함수 DROP 후 10인자로 재생성** → 프론트 signup.tsx 호출 동시 수정 |

### 4-3. 권한
- `phone_verification`: RLS 활성, anon 테이블 권한 없음(SECURITY DEFINER RPC가 우회).
- `request_otp`: **service_role 에만 execute**(anon 미부여) — 클라이언트 코드 수확 차단.
- `verify_otp`, `find_username`, `reset_password`, `signup_member`(10인자): anon execute.

### 4-4. 적용
- B1처럼 라이브 마이그레이션(MCP `apply_migration` 또는 Management API). `signup_member` DROP→CREATE 순서 주의. 적용 후 MCP `execute_sql` 라운드트립 스모크 + 스모크 데이터 정리.

## 5. Edge Function `send-otp`

### 5-1. 구조 (`supabase/functions/send-otp/`)
- `index.ts` — 핸들러
- `provider.ts` — `SmsProvider` 인터페이스 + `FakeSmsProvider` + `HttpSmsProvider`(골격) + `getProvider()`
- `_shared/cors.ts` — 브라우저 호출용 CORS 헤더

### 5-2. 핸들러 흐름 (`index.ts`)
1. CORS preflight(OPTIONS) 처리.
2. body `{phone, purpose}` 파싱·검증(purpose ∈ signup/find_id/find_pw, phone 형식).
3. service-role supabase 클라이언트 생성(자동 주입 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`).
4. `rpc('request_otp', {p_phone, p_purpose})` → 레이트리밋 등 에러면 429/400 + reason.
5. 평문 코드 받음 → `getProvider().send(phone, "[꽃아이] 인증번호 [코드] (3분 내 입력)")`.
6. `{success:true}` 반환. 발송 실패 → 502 `{success:false}`. **코드는 응답에 절대 안 실음.**

### 5-3. 제공사 추상화 (`provider.ts`)
```ts
export interface SmsProvider { send(to: string, text: string): Promise<void>; }

export class FakeSmsProvider implements SmsProvider {       // 오프라인/개발
  async send(to: string, text: string) { console.log(`[FakeSMS] ${to}: ${text}`); }
}
export class HttpSmsProvider implements SmsProvider {        // 골격(계정 준비 시 완성)
  async send(to: string, text: string) {
    const url = Deno.env.get('SMS_API_URL'); const key = Deno.env.get('SMS_API_KEY');
    if (!url || !key) throw new Error('SMS env 미설정');
    const res = await fetch(url, { method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, text, from: Deno.env.get('SMS_SENDER') }) });
    if (!res.ok) throw new Error(`SMS 발송 실패 ${res.status}`);
  }
}
export function getProvider(): SmsProvider {
  return Deno.env.get('SMS_PROVIDER') === 'http' ? new HttpSmsProvider() : new FakeSmsProvider();
}
```
- 기본 `SMS_PROVIDER=fake`(시크릿 불필요) → 지금 바로 전체 흐름 테스트. 계정 준비 시 `SMS_PROVIDER=http` + `SMS_API_URL/KEY/SENDER` + 페이로드 제공사 규격화.

### 5-4. 배포·시크릿
- `SUPABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY` 자동 주입. SMS_* 는 fake 모드면 불필요.
- 배포: `supabase functions deploy send-otp`(CLI) 또는 MCP `deploy_edge_function`/Management API. **라이브 단계**(컨트롤러).

### 5-5. 테스트 경계
- OTP 핵심 로직(생성·저장·검증)은 Postgres RPC → MCP 라운드트립으로 테스트(§4).
- Edge Function은 얇은 시밍 → 수동 스모크(`supabase functions serve` + curl, fake provider가 코드 로그 출력). Deno 자동 테스트 툴체인 미도입(Vitest/pytest 체계 유지).

## 6. 프론트엔드

### 6-1. OTP 클라이언트 래퍼 (`src/otp/client.ts`, 순수·테스트 가능)
- `sendOtp(client, phone, purpose)` → `client.functions.invoke('send-otp', {body:{phone,purpose}})` → `{ok, error?}`
- `verifyOtp(rpc, phone, purpose, code)` → `rpc('verify_otp', …)` → `{ok, token?, reason?}`
- `findUsername(rpc, phone, shopName, token)` → `{ok, username?, reason?}`
- `resetPassword(rpc, phone, username, newPassword, token)` → `{ok, reason?}`
- `src/otp/messages.ts` — `reason`→한글 메시지 매퍼(만료/오답/시도초과/없음/토큰무효).

### 6-2. 공유 컴포넌트 `src/components/PhoneVerify.tsx`
- props `{ phone, purpose, onVerified(token) }`. 상태머신 `idle → sent → verified`.
- [인증요청] → `sendOtp` → 성공 시 코드입력 + 180초 카운트다운 + [확인]. 만료/재전송 처리.
- [확인] → `verifyOtp` → 성공 시 `onVerified(token)` + `verified` 표시. 실패 시 reason 메시지 + 재시도.

### 6-3. `views/find_id.tsx` (`FindIdView({ onDone })`, 스텁 대체)
- 입력: 꽃집명 + 핸드폰 → `PhoneVerify(purpose='find_id')` → `onVerified(token)` → `findUsername(phone, shopName, token)` → "회원님의 아이디는 **[username]**" 또는 "일치하는 계정이 없습니다". [로그인으로].

### 6-4. `views/find_pw.tsx` (`FindPwView({ onDone })`, 스텁 대체)
- 입력: 아이디 + 핸드폰 → `PhoneVerify(purpose='find_pw')` → `onVerified(token)` → 새 비밀번호 + 확인 입력 노출(일치 검증) → [비밀번호 재설정] → `resetPassword(phone, username, newPw, token)` → 성공 alert + `onDone`.

### 6-5. `views/signup.tsx` 수정
- 비활성 [인증] 버튼 → `PhoneVerify(purpose='signup', phone=f.mobile)`로 교체. `onVerified(token)` → state에 토큰 저장 + 핸드폰 필드 잠금.
- `signup_member` 호출에 `p_verification_token` 추가. 인증 미완료 시 가입 차단("핸드폰 인증을 완료해주세요").

### 6-6. `App.tsx` 수정
- `FindIdView`/`FindPwView`를 `_placeholders` → `views/find_id`·`views/find_pw`에서 임포트. `onDone={() => setRoute('login')}` 배선.

## 7. 테스트 전략
- **Vitest(오프라인):** `otp/client.test.ts`(verifyOtp 성공/오답/만료/시도초과/없음, findUsername 성공/없음/토큰무효, resetPassword 성공/없음), `otp/messages.test.ts`(reason→메시지). 기존 B1 16건 + 신규 전부 green, `npm run build` 성공.
- **DB RPC(라이브):** MCP `execute_sql` 라운드트립 — `request_otp`→`verify_otp`(정상/오답/만료)→토큰→`find_username`/`reset_password`/`signup_member(token)`. 레이트리밋·시도초과·토큰 단일사용·만료 검증. 스모크 데이터 정리 필수.
- **Edge Function:** `supabase functions serve` + curl, `SMS_PROVIDER=fake`로 코드 로그 출력 수동 스모크.
- **수동 육안:** fake 배포 후 가입 인증/아이디찾기/비번재설정 전체 흐름.

## 8. 에러 처리
- OTP 오답/만료/시도초과 → PhoneVerify reason별 메시지 + 재전송 허용.
- 레이트리밋(`request_otp`) → "잠시 후 다시 시도해주세요".
- `send-otp` 발송 실패 → "인증번호 발송에 실패했습니다".
- `find_username` 불일치 → "일치하는 계정이 없습니다"(2요소라 enumeration 제한).
- `reset_password` 불일치/토큰만료 → 에러 + 재인증 유도.
- 검증→작업 사이 토큰 만료 → 재인증.
- 함수 미배포(web dev) → "발송 실패" degrade(앱 안 깨짐).

## 9. 보안
- `request_otp` anon 미허용(코드 수확 차단), 코드 해시·3분·5회·레이트리밋.
- 검증 토큰 랜덤·해시·단일사용·10분·purpose 한정.
- 찾기/재설정 2요소(OTP 폰 소유 + 꽃집명/아이디). 비번 재설정은 bcrypt 재해싱(B1 계약 유지).
- SMS 키는 Edge Function 시크릿에만. `phone_verification` anon 직접접근 없음(RLS+RPC).

## 10. 범위 경계 (B2b/이후)
- 마이페이지(프로필 조회·수정 + 재인증) → **B2b**.
- 실 SMS 발송(HttpSmsProvider 페이로드 완성 + 시크릿) → 제공사 계정 준비 시.
- 관리자 승인 UI, `member_info` 전화번호 유니크 강제(현재 phone+2요소로 식별; 다중 일치 시 첫 행) → 별도.
- C/D/E(대시보드·조회·설정 정교화) → 별도 서브프로젝트.

## 11. 변경 파일 요약
- **DB:** 마이그레이션(테이블 + RPC 4개 신규 + `signup_member` DROP/재생성 + 권한)
- **Edge Function(신규):** `supabase/functions/send-otp/index.ts`, `provider.ts`, `_shared/cors.ts`
- **신규 프론트:** `otp/client.ts`(+test), `otp/messages.ts`(+test), `components/PhoneVerify.tsx`, `views/find_id.tsx`, `views/find_pw.tsx`
- **수정:** `views/signup.tsx`, `App.tsx`

## 12. 구현 시 확인 사항
- ⓐ Edge Function 배포·시크릿 주입 경로(MCP unauthorized면 supabase CLI 또는 Management API). 현 세션에서 MCP는 Unauthorized — DB는 Management API 직접호출(curl UA)로 적용한 전례 있음(B1).
- ⓑ `signup_member` 시그니처 변경(9→10인자) — DROP 후 CREATE, 프론트 호출 동시 수정(미수정 시 anon이 옛 함수 못 찾음).
- ⓒ `supabase.functions.invoke` 반환형이 클라이언트 래퍼 계약과 호환되는지(불호환 시 B1식 단일 캐스트).
- ⓓ phone 정규화(하이픈 제거 등) — 발송·조회·member_info 매칭 일관성. member_info.mobile_number 저장 포맷과 맞출 것.
- ⓔ `verify_otp`가 같은 phone+purpose에 여러 행이 있을 때 최신 1건만 대상으로 하는지(과거 행 정리로 보강).
