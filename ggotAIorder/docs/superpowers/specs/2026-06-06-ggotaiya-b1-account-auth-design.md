# ggotAIya 서브프로젝트 B1 (회원가입·비밀번호 해싱·영구 자동로그인) 설계서

> 작성일 2026-06-06. ggotAIya 인증·계정(B) 분해 중 **B1**. 핸드폰 OTP 의존부(가입 실인증/찾기/마이페이지)는 **B2로 이월**.

## 1. 목표 (Goal)

A가 세운 로그인 게이트 셸 위에 **① 회원가입(member_info 적재) ② 로그인 비밀번호 해싱 ③ 영구 자동로그인**을 추가한다. 인증을 A의 "프론트가 `member_info`를 직접 읽어 평문 비교"하던 방식에서 **Postgres RPC(pgcrypto) 서버사이드 검증**으로 전환하고, 그 과정에서 anon 키로 `password`를 읽을 수 있던 기존 보안 구멍을 닫는다.

## 2. 범위 결정 (확정된 사용자 선택)

| 결정 | 선택 | 비고 |
|------|------|------|
| 첫 범위 | **B1** = 회원가입 + 비번 해싱 + 영구 자동로그인 | OTP·찾기·마이페이지 = B2 |
| 해싱 위치 | **Postgres pgcrypto RPC** | SECURITY DEFINER, RLS/컬럼권한, 평문 마이그레이션 |
| 자동로그인 | **서버 발급 remember_token** | member_info에 해시 컬럼, 시작 시 RPC 검증, 30일 만료 |
| 가입폼 | 다음(카카오) 주소찾기 API 포함, 아이디 중복확인 포함 | 핸드폰 [인증] 버튼은 비활성 스텁(B2) |
| 자동로그인 UX | 검증 중 `authReady` 로딩 게이팅 | 로그인 화면 깜빡임 방지 |

## 3. 아키텍처 개요

핵심 전환: 인증을 **Postgres RPC(pgcrypto) 기반 서버사이드 검증**으로 이동. 비밀번호 해시·remember_token 해시는 **프론트가 절대 읽지 않는다**(컬럼 권한으로 anon 차단). 자동로그인은 **서버 발급 remember_token**을 앱 시작 시 RPC로 검증해 세션을 복원한다.

4개 작업 영역:
1. **DB 계층** — pgcrypto 확장, member_info 컬럼 추가, RPC 함수군, 컬럼 권한, 평문 마이그레이션
2. **프론트 세션 계층** — authenticate를 RPC로 교체, SessionContext에 자동로그인·토큰 수명주기 추가
3. **프론트 화면** — signup.tsx 신규, login.tsx 자동로그인 배선, App.tsx authReady 게이팅
4. **Electron 보안 저장소** — remember_token을 `safeStorage`로 로컬 보관(main + preload + 타입)

### 데이터 흐름
- **가입**: 폼 → `signup_member` RPC → member_info INSERT(해시, `is_approved='N'` 승인대기) → 안내 → 로그인 복귀
- **로그인**: 폼 → `verify_login` RPC → 세션; 자동로그인 체크 시 → `issue_remember_token` → safeStorage 저장
- **시작**: safeStorage 토큰 → `verify_remember_token` RPC → 세션 복원(로그인 건너뜀), 검증 끝까지 `authReady=false`
- **로그아웃**: `clear_remember_token` RPC + safeStorage 삭제

## 4. DB 계층 상세

### 4-1. 확장 + 컬럼 (마이그레이션 1)
```sql
create extension if not exists pgcrypto;

alter table member_info
  add column if not exists remember_token_hash       text,
  add column if not exists remember_token_expires_at timestamptz;
```

### 4-2. RPC 함수군 (SECURITY DEFINER, search_path 고정)

| 함수 | 인자 | 반환 | 동작 |
|------|------|------|------|
| `check_username(p_username)` | text | boolean | 존재 여부(true=중복). 가입 [중복확인]용 |
| `signup_member(p_username, p_password, p_shop_name, p_representative_name, p_landline, p_mobile, p_email, p_address, p_address_detail)` | text… | json `{id, is_approved}` | 중복이면 예외. `password = crypt(p_password, gen_salt('bf'))`, `is_approved='N'` INSERT |
| `verify_login(p_username, p_password)` | text, text | json `{id, shop_name, username, is_approved}` 또는 null | `password = crypt(p_password, password)` 매칭 시 행 반환. 비번 자체는 반환 안 함 |
| `issue_remember_token(p_user_id)` | int | text(평문 토큰) | 랜덤 토큰(`encode(gen_random_bytes(32),'hex')`) 생성→`remember_token_hash=crypt(token, gen_salt('bf'))`, 만료 `now()+interval '30 days'` 저장, 평문 반환 |
| `verify_remember_token(p_user_id, p_token)` | int, text | json 세션 또는 null | 해시 일치 & 미만료면 세션 반환 |
| `clear_remember_token(p_user_id)` | int | void | 토큰 해시/만료 NULL |

- `verify_login`은 `is_approved`를 반환하고 **승인 판정은 프론트**(A의 "미승인=승인대기 에러" 로직)에서 처리한다.

### 4-3. 컬럼 권한 (기존 보안 구멍 차단)
```sql
revoke select on member_info from anon;
grant select (id, username, shop_name, representative_name,
              landline_number, mobile_number, email, address,
              address_detail, is_approved, created_at) on member_info to anon;
-- password, remember_token_hash, remember_token_expires_at 는 anon 미부여
grant execute on function verify_login, signup_member, check_username,
  issue_remember_token, verify_remember_token, clear_remember_token to anon;
```
- RPC는 SECURITY DEFINER라 함수 내부에서는 비밀 컬럼 접근 가능, 외부 직접 SELECT만 차단.
- **구현 전 검증**: settings/dashboard 등이 `member_info`에서 읽는 컬럼이 허용목록에 포함되는지 grep 확인(누락 시 목록 추가). `password`를 직접 읽던 곳은 A의 authenticate뿐이고 이번에 RPC로 대체된다.

### 4-4. 평문 마이그레이션 (마이그레이션 2, 멱등 가드)
```sql
update member_info
   set password = crypt(password, gen_salt('bf'))
 where password is not null
   and password not like '$2%';   -- bcrypt 해시($2…)는 재해싱 제외
```

### 4-5. 적용·검증
- 마이그레이션은 MCP `apply_migration`으로 라이브 DB에 적용. 적용 전 `list_tables`로 현 스키마 확인.
- RPC 동작은 Vitest 단위검증 불가 → MCP `execute_sql` 라운드트립 스모크 + 수동 체크리스트.

## 5. 프론트엔드 상세

### 5-1. 세션 계층 개편
`session/authenticate.ts` — 직접 쿼리/평문비교 제거, RPC 호출로 교체:
```ts
export interface AuthClient {
  rpc(fn: string, args: Record<string, unknown>):
    Promise<{ data: unknown; error: unknown }>;
}
export async function authenticate(client, username, password): Promise<AuthResult> {
  const { data, error } = await client.rpc('verify_login',
    { p_username: username, p_password: password });
  if (error) return { ok:false, error:'로그인 중 오류가 발생했습니다' };
  const row = data as MemberRow | null;        // null = 불일치
  if (!row) return { ok:false, error:'아이디 또는 비밀번호가 올바르지 않습니다' };
  if (row.is_approved !== 'Y') return { ok:false, error:'승인 대기 중인 계정입니다' };
  return { ok:true, session:{ shopKey:row.id, shopName:row.shop_name, username:row.username } };
}
```
- `authenticate.test.ts` 재작성: fake `rpc` 클라이언트로 성공/불일치(null)/미승인/RPC에러 4건. A의 5건 의도 유지.
- 실제 `supabase` 클라이언트의 `.rpc()`가 `AuthClient`에 구조적으로 부합 — A의 단일지점 캐스트 패턴(`as unknown as AuthClient`) 동일 적용.

`session/SessionContext.tsx` — 자동로그인·토큰 수명주기 추가:
```
login(username, password, rememberMe):
  authenticate(supabase,…) → 성공 시
    if rememberMe: token = rpc('issue_remember_token',{p_user_id:id})
                   → window.electronAPI?.saveRememberToken(id, token)
    setSession(...)
logout():
  if session: rpc('clear_remember_token',{p_user_id:session.shopKey})
  window.electronAPI?.clearRememberToken(); setSession(null)
useEffect(앱 시작 1회):                 // 자동로그인
  const saved = await window.electronAPI?.loadRememberToken()  // {userId, token} | null
  if saved: rpc('verify_remember_token',{p_user_id, p_token})
            → 세션 있으면 setSession, 없으면 clearRememberToken
  setAuthReady(true)
```
- 복원 로직은 순수 함수 `restoreSession(rpc, storage)`로 분리해 단위테스트(`session/rememberToken.ts`).
- `Session`/`AuthResult` 형태 불변. 검증 중 `authReady=false`로 셸 로딩 유지.

### 5-2. Electron 보안 저장소
- `src/main/`: `safeStorage`로 `{userId, token}` JSON 암호화→유저데이터 경로 파일 저장. IPC 핸들러 `auth:save|load|clear`.
- `preload.ts`: `electronAPI`에 `saveRememberToken(userId, token)`, `loadRememberToken()`, `clearRememberToken()` 노출.
- `types/electron.d.ts`: 위 3개 메서드 시그니처 추가.
- 웹(브라우저 dev)에서 `electronAPI` 미존재 시: 자동로그인 무음 skip, 로그인 정상 동작.

### 5-3. 회원가입 화면 `views/signup.tsx` (스텁 대체)
- 필드(PRD 화면5): 아이디+**[중복확인]**(`check_username`), 비밀번호+확인(일치검증), 꽃집명, 대표자, 전화, 핸드폰+**[인증]**(비활성 "B2 예정"), 이메일, 주소+**[주소찾기]**, 상세주소, **[회원가입]**.
- 주소찾기: 다음 우편번호(`postcode.v2.js`) 동적 로드 → 팝업 선택 시 주소/우편번호 채움. 래퍼 `utils/daumPostcode.ts`. 로드 실패 시 수기 입력 폴백.
- 제출 → `signup_member` RPC → 성공 시 "가입 완료, 관리자 승인 후 로그인 가능"(`is_approved='N'`) 안내 → 로그인 화면 복귀.
- 순수 검증 로직(필수값·비번일치·이메일형식)은 `signup/validate.ts`로 분리해 Vitest 단위테스트.
- PRD 6-1 엔터 포커스 이동 적용(A의 `focusNext` 패턴 재사용).

### 5-4. 로그인 화면 `views/login.tsx`
- A에서 표시만이던 `autoLogin` 체크박스를 `login(username, password, autoLogin)`으로 실제 배선.

### 5-5. App.tsx
- `authReady` 게이팅 추가(자동로그인 검증 완료 전 로그인/홈 렌더 보류).
- `SignupView` 임포트를 `_placeholders` → `views/signup`으로 교체.

## 6. 테스트 전략

**Vitest 단위(오프라인, 결정적):**
- `authenticate.test.ts` 재작성 — fake rpc로 성공/불일치/미승인/에러 4건.
- `signup/validate.test.ts` — 필수값·비번불일치·이메일형식·정상.
- `session/rememberToken.test.ts` — `restoreSession` 순수 로직(토큰 있음→검증성공/실패→정리)을 fake rpc + fake storage로.
- 목표: 기존 8건 + B1 신규 전부 green, `npm run build` 성공.

**DB/RPC 검증(라이브, Vitest 밖):**
- MCP `execute_sql` 스모크: `signup_member`→`verify_login`(정상/오답)→`issue_remember_token`→`verify_remember_token`→`clear_remember_token` 라운드트립.
- 컬럼 권한: anon 롤로 `select password from member_info` 거부 확인.
- 마이그레이션 멱등성: 재실행 시 재해싱 없음 확인.
- 수동 체크리스트 문서화: 가입→승인(`is_approved='Y'` 수동)→로그인→자동로그인 재시작→로그아웃.

## 7. 에러 처리
- 가입 아이디 중복 → 인라인 경고, 가입 차단.
- 비번/확인 불일치, 필수값 누락 → 필드 인라인 에러.
- `verify_login` null → 일반화 에러(enumeration 방지).
- remember_token 무효/만료 → 무음 폴백(로컬 토큰 정리 + 로그인 화면).
- RPC 네트워크 에러 → 사용자 메시지.
- 주소찾기 스크립트 로드 실패 → 주소 수기 입력 폴백(가입 진행 가능).
- safeStorage 미가용(웹 dev) → 자동로그인 무음 skip.

## 8. 보안 메모
- anon의 `password`/`remember_token_hash` 직접 SELECT 차단(기존 구멍 해소).
- bcrypt(pgcrypto `gen_salt('bf')`), remember_token은 랜덤·해시저장·30일 만료·서버 무효화 가능.
- `setting_info`의 쇼핑몰/인터라넷 비번은 **AES 양방향 유지**(해싱 대상 아님 — 백엔드가 평문 필요).
- CBC-without-HMAC(A 문서화된 후속)·실 핸드폰 인증은 B1 범위 밖.

## 9. 범위 경계 (B2/이후로 이월)
- 핸드폰 OTP 인프라(Supabase Edge Function + SMS 제공사), 가입 폰 실인증(F2), 아이디/비번 찾기(F4), 마이페이지 재인증 수정(F5).
- 관리자 승인 UI — 현재 수동(`is_approved` DB 갱신). 별도.
- C/D/E(대시보드·조회·설정 정교화) — 별도 서브프로젝트.

## 10. 변경 파일 요약
- **DB**: 마이그레이션 2개(① 스키마+RPC+권한, ② 평문해싱)
- **신규**: `views/signup.tsx`, `signup/validate.ts`(+test), `utils/daumPostcode.ts`, `session/rememberToken.ts`(+test), Electron auth IPC(`src/main/`)
- **수정**: `session/authenticate.ts`(+test 재작성), `session/SessionContext.tsx`, `views/login.tsx`, `App.tsx`, `main/preload.ts`, `types/electron.d.ts`

## 11. 미해결/구현 시 확인 사항
- ⓐ `member_info` 컬럼 허용목록이 기존 화면(settings/dashboard 등)의 읽기 컬럼을 모두 포함하는지 grep 검증(누락 시 추가).
- ⓑ 실제 `supabase.rpc()` 반환 타입이 `AuthClient.rpc` 계약과 호환되는지(불호환 시 A의 단일지점 캐스트 동일 적용).
- ⓒ Electron `safeStorage` 가용성은 OS·세션에 의존 — 미가용 환경 폴백(자동로그인 skip) 확인.
- ⓓ 다음 우편번호 스크립트 외부 로드(오프라인/CSP) — Electron 환경에서 로드 가능 여부 확인.
