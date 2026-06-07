# ggotAIya B2b — 마이페이지(회원정보 관리) 설계서

작성일: 2026-06-07
선행: B2a(핸드폰 OTP 인프라) 머지됨 — master `5d78085`. 본 설계는 B2a의 `phone_verification` 테이블·`send-otp` EF·`PhoneVerify` 컴포넌트를 재사용한다.

## 1. 범위

PRD F5 / 화면7: 로그인한 사장님이 자기 회원정보를 조회하고, **핸드폰 재인증 후** 수정한다. 아이디는 수정 불가.

- **조회**: 로그인 사용자의 회원정보 프리필.
- **수정 가능 필드**: 꽃집명, 대표자명, 전화(유선, 선택), 이메일(선택), 주소, 상세주소(선택).
- **핸드폰 변경**: 가능(아래 보안 모델). — *사용자 결정(2026-06-07)*
- **비밀번호 변경**: 마이페이지에 포함(로그인 상태). — *사용자 결정*
- **아이디**: read-only(수정 불가).
- **기존 보안 구멍 하드닝**: `member_info` anon 직접권한 회수. — *사용자 결정*

비범위: 회원 탈퇴, 승인상태 변경, 알림/설정(=E), 마이페이지 외 화면.

## 2. 보안 모델 (핵심)

수정 RPC는 anon 호출 가능(앱 "로그인"은 클라이언트 상태일 뿐 DB 레벨 JWT 아님). 따라서 **"공격자가 피해자 username으로 RPC 호출"을 막으려면 계정에 묶인 증명이 필요**하다. PRD가 "핸드폰 재인증"을 명시하므로 **현재 등록폰 OTP를 권한 게이트**로 사용한다.

- **권한(계정 바인딩)**: OTP 토큰의 phone이 **계정의 현재 mobile_number와 일치**해야 통과. → 현재 등록폰을 통제하는 사람만 수정 가능.
- **핸드폰 변경**: 현재폰 OTP(권한) + **새 폰 OTP(소유 증명)** 2단계. 새 번호 미검증 시 오타로 인한 영구 락아웃(이후 find_id/find_pw/마이페이지 모두 잠김) 방지.
- **비밀번호 변경**: 현재폰 OTP + **현재 비밀번호 확인**(표준 가드).
- **토큰**: 전부 단일사용(소비). purpose=`update_profile` 공용(현재폰·새폰 모두).

접근법 비교(채택=B):
- A(통합 단일 게이트): 현재폰 OTP 1회로 프로필+새폰+새비번 저장, 새폰 미검증·현재비번 미요구. 단순하나 락아웃 위험.
- **B(섹션 가드, 채택)**: 현재폰 OTP 권한 + 핸드폰 변경 시 새폰 OTP + 비번 변경 시 현재 비번. 견고.

## 3. 아키텍처

B2a 패턴(얇은 Edge Function + 두꺼운 pgcrypto SECURITY DEFINER RPC) 재사용.

```
MyPageView ──get_profile(username)──────────────▶ (프리필)
   │
   ├─ PhoneVerify(purpose=update_profile, 현재폰) ─send-otp(EF)→request_otp / verify_otp ─▶ authToken
   ├─ [핸드폰변경] PhoneVerify(새폰) ─────────────────────────────────────────────▶ newPhoneToken
   ├─ [비번변경] 현재비번 + 새비번
   └─ [저장] ──update_account(username, authToken, 필드…, newMobile?, newPhoneToken?, curPw?, newPw?)──▶
```

- **EF `send-otp`**: 무변경(코드). `VALID_PURPOSES`에 `'update_profile'` 추가 후 재배포(fake 모드, verify_jwt=false 유지).
- **신규 RPC**: `get_profile`, `update_account`.
- **purpose**: `request_otp`의 CHECK에 `'update_profile'` 추가. `verify_otp`는 purpose 목록 미검사 → 무변경.

## 4. 데이터 모델

테이블 변경 없음. `member_info`(기존 컬럼), `phone_verification`(B2a) 그대로 사용.

### RPC: `get_profile(p_username text) → json`
SECURITY DEFINER, `search_path=public,extensions`, anon 실행.
```
성공: { "ok": true, "profile": {
  username, shop_name, representative_name, landline_number,
  mobile_number, email, address, address_detail, is_approved } }
없음: { "ok": false, "reason": "not_found" }
```
- password / remember_token_* 는 **반환 금지**.
- 폼 프리필 + PhoneVerify 앵커(현재 mobile) 제공.

### RPC: `update_account(...) → json`
SECURITY DEFINER, `search_path=public,extensions`, anon 실행. 함수 본문 단일 트랜잭션(부분쓰기 없음).

인자:
```
p_username text,
p_auth_token text,            -- 현재폰 OTP (필수)
p_shop_name text, p_representative_name text, p_landline text,
p_email text, p_address text, p_address_detail text,
p_new_mobile text,            -- 선택(미변경이면 현재값/NULL)
p_new_phone_token text,       -- 새폰 OTP (핸드폰 변경 시 필수)
p_current_password text,      -- 비번 변경 시 필수
p_new_password text           -- 선택
```

처리:
1. username으로 member_info 현재 행 로드. 없으면 `{ok:false,reason:'not_found'}`.
2. **권한**: `p_auth_token` ↔ phone_verification(purpose='update_profile', phone=정규화(현재 mobile), verified=true, token_hash 일치, token_expires_at>now()). 실패 시 `invalid_token`. 성공 시 token 소비(token_expires_at=now()).
3. **비번 변경(p_new_password 비어있지 않으면)**: `member_info.password = crypt(p_current_password, password)` 검증 실패 시 `bad_password`. 통과 시 `password = crypt(p_new_password, gen_salt('bf'))`.
4. **핸드폰 변경**: `p_new_mobile`이 **비어있지 않고**(정규화 후 길이>0) 정규화값이 현재 mobile과 **다를 때만** 트리거. (null/빈값/동일 → 변경 없음, 토큰 불요.) 트리거 시 `p_new_phone_token` ↔ phone_verification(purpose='update_profile', phone=정규화(새폰), verified, 일치, 미만료). 실패 시 `new_phone_unverified`. 통과 시 token 소비 + `mobile_number = p_new_mobile`.
5. 프로필 6필드 UPDATE(빈 선택값은 NULL 정규화: landline/email/address/address_detail).
6. `{ ok:true, profile:{...최종값} }` 반환(헤더 shop_name 갱신용).

각 실패는 즉시 리턴(이전 단계 변경은 동일 함수 호출 내 미커밋 — plpgsql 함수는 호출 단위 원자성).

## 5. 보안 하드닝 (마이그레이션 포함)

현 상태(라이브 확인): `member_info` **RLS 비활성** + anon에 대부분 컬럼 직접 SELECT/INSERT/UPDATE/REFERENCES 권한 → anon이 임의 회원 조회/수정 가능. 프론트는 member_info 직접접근 0건(전부 RPC), 백엔드는 service_role.

```sql
revoke select, insert, update, delete, references
  on table member_info from anon, authenticated, public;
grant execute on function get_profile(text) to anon;
grant execute on function update_account(text,text,text,text,text,text,text,text,text,text,text,text) to anon;
```
- anon/authenticated는 member_info 직접 접근 불가 → 모든 접근은 SECURITY DEFINER RPC(owner=postgres) 경유.
- service_role(백엔드) 유지.
- **RLS는 켜지 않음**: 테이블 권한 회수가 PostgREST를 막음. SECURITY DEFINER 함수는 owner 실행이라 무관. 단순함 우선. — *사용자 승인*

검증: `has_table_privilege('anon','member_info','select')=false`, `…'update')=false`, `has_function_privilege('anon','get_profile(text)','execute')=true`, `update_account` true. 기존 RPC(verify_login/signup_member/check_username/issue·verify·clear_remember_token)는 회수 후에도 동작(스모크 재확인).

## 6. 프론트엔드

### `frontend/src/profile/client.ts` (신규, 순수 래퍼; B2a `otp/client` 형제)
- `getProfile(rpc, username) → { ok, profile? }`
- `updateAccount(rpc, payload) → { ok, profile?, reason? }`
- `diffProfile(original, form) → 변경필드 부분객체` (불필요 UPDATE 방지; 순수함수, Vitest 대상)
- 주입형 `RpcLike`(B2a/B1 단일 캐스트 패턴).

### `frontend/src/views/mypage.tsx` (신규 — `_placeholders`의 MyPageView 스텁 대체)
- 마운트 시 `getProfile(session.username)` → 프리필. 로딩/에러 상태.
- 필드: 아이디(**disabled**), 꽃집명, 대표자명, 전화(선택), 이메일(선택), 주소(+주소찾기 `openPostcodeSearch` 재사용), 상세주소.
- **상단 권한 게이트**: `PhoneVerify(purpose='update_profile', phone=현재mobile)` → `authToken`. 인증 전 [저장] disabled.
- **핸드폰 변경(토글)**: 새 핸드폰 입력 + 두 번째 `PhoneVerify(purpose='update_profile', phone=새번호)` → `newPhoneToken`.
- **비밀번호 변경(토글)**: 현재 비번 + 새 비번 + 새 비번 확인(불일치 클라 가드).
- **[저장]** → `updateAccount(payload)`:
  - 성공: 세션 shop_name 갱신(헤더 반영), "수정되었습니다" 표시, 핸드폰 변경 시 현재mobile 앵커 갱신.
  - 실패 reason 매핑: `invalid_token`(인증 만료/불일치) / `bad_password`(현재 비번 불일치) / `new_phone_unverified` / `not_found` → 한글 메시지.

### 세션 갱신
`SessionContext`에 `updateShopName(name: string)` (또는 최소 `setSession` 노출) 추가 — 헤더에 쓰이는 shop_name만 갱신. `Session` 타입은 기존(shopKey/shop_name/username/is_approved) 유지 또는 최소 확장. — *사용자 승인*

### 라우팅/공용
- `App.tsx`의 `route==='mypage' && <MyPageView/>` 배선 기존 유지(import만 신규 파일로 교체).
- `otp/client.ts`의 `Purpose`에 `'update_profile'` 추가 → `PhoneVerify` 무변경 재사용.

## 7. 테스트 & 라이브 단계

### 자동 테스트 (Vitest, 오프라인)
- `profile/client.test.ts`: `diffProfile`(변경필드만), `getProfile`/`updateAccount` 성공·에러 매핑(주입형 fake rpc), reason→메시지.
- 기존 35 passed 유지 + 신규 추가. `npm run build` 성공 게이트.
- DB/EF는 Vitest 대상 아님(라이브 스모크).

### DB 라운드트립 스모크 (Management API, 컨트롤러 직접)
1. 스모크 회원 생성(signup_member) → `get_profile` 프리필 확인.
2. `update_account` 프로필만(현재폰 토큰) → 필드 갱신 확인.
3. 핸드폰 변경: 현재폰 토큰 + 새폰 토큰 → mobile 갱신 + 새 번호 재인증 가능.
4. 비번 변경: 현재 비번 + 현재폰 토큰 → `verify_login` 새 비번 성공 / 틀린 현재 비번 → `bad_password`.
5. 네거티브: 타계정 토큰(다른 폰) → `invalid_token`, 새폰 토큰 누락 → `new_phone_unverified`.
6. **정리 delete 필수**(member_info + phone_verification).

### 권한 검증
`has_table_privilege('anon','member_info','select'|'update')=false`, `has_function_privilege('anon','get_profile/update_account','execute')=true`, 기존 RPC 1건씩 동작 재확인.

### 라이브 단계 (PAT 필요 — B2a 전례: Management API + curl UA)
- ⓐ 마이그레이션 적용: purpose 추가 + `get_profile`/`update_account` + anon 권한 회수 + 신규 RPC grant.
- ⓑ EF `send-otp` 재배포: `VALID_PURPOSES`에 `update_profile` 추가(`npx supabase functions deploy --no-verify-jwt`).
- ⓒ UI E2E(Playwright **Node판** — Python판은 greenlet/MSVC DLL 불가): 로그인 → 마이페이지 → 프로필 수정 / 핸드폰 변경 / 비번 변경 전체. OTP는 `function_logs`에서 추출(직전 소비 코드의 서버 timestamp보다 새 것만 받기).

## 8. 구현 순서(plan 예고)
1. 마이그레이션 SQL 작성 + 라이브 적용 + 스모크/권한 검증 (컨트롤러 직접).
2. EF `VALID_PURPOSES` + 프론트 `Purpose` 'update_profile' 추가 + EF 재배포.
3. `profile/client.ts` (+test) — TDD.
4. `views/mypage.tsx` + `SessionContext` setter — `_placeholders` MyPageView 제거.
5. 전체 검증: Vitest + build + 라이브 스모크 + UI E2E + finishing-a-development-branch(PR/머지).

## 9. 핵심 결정 요약
- 핸드폰 변경 가능 / 비번 변경 포함 / anon 직접권한 회수 — 사용자 결정.
- 권한 게이트=현재 등록폰 OTP(계정 바인딩). 핸드폰 변경=새폰 OTP 추가. 비번 변경=현재 비번 추가.
- 단일 `update_account` RPC(비번 변경 통합). `get_profile` 프리필.
- RLS 미사용, 테이블 권한 회수로 하드닝.
- B2a 자산(send-otp EF, PhoneVerify, phone_verification, otp/messages) 재사용. 브랜치 `feature/ggotaiya-b2b-mypage`(master `5d78085`에서 분기).
