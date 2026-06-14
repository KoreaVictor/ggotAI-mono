# ggotAIya 서브프로젝트 A — 기반·셸·암호화 수정 설계서

- **작성일:** 2026-06-05
- **대상:** ggotAIya(프론트엔드) 구현의 첫 서브프로젝트 A
- **선행:** `frontend/docs/PRD.md`, `frontend/docs/ggotAIya-design.pptx`(21슬라이드 설계), `docs/ipc_specification.md`
- **상태:** master `073456f` 기준. 기존 `frontend/`(Phase 2: dashboard/order_list/settings + sidebar 셸, 로그인 없음) 위에 구축.

---

## 1. 배경 및 범위

ggotAIya 전체 구현은 여러 독립 서브시스템(인증/상황판/조회/설정 등)이라 단일 설계로는 과대하다. brainstorming에서 다음으로 분해하고 **A부터** 진행하기로 합의했다.

| | 서브프로젝트 | 본 설계 |
|---|---|---|
| **A** | 기반·셸·암호화 수정 | ← 이 문서 |
| B | 인증·계정(가입/찾기/OTP/마이페이지/자동로그인) | 별도 |
| C | 상황판 정교화 | 별도 |
| D | 주문조회 | 별도 |
| E | 환경설정(암호화 가시화 포함) | 별도 |

### A의 목표
선택된 와이어프레임(상단 헤더 셸)에 맞춰 **로그인 게이트 셸 + 인메모리 세션 + 최소 ID/PW 로그인 + HOME**을 세우고, **AES 암호화 계약 버그를 수정**하며 공유 타입을 도입한다. A는 그 자체로 동작·테스트 가능해야 한다.

### A에서 제외(이월)
- 회원가입·아이디/비번찾기·핸드폰 OTP·마이페이지 실로직 → **B**
- 영구 자동로그인(토큰 저장) → **B**
- 비밀번호 해싱 전환 → **B**(가입이 비번을 쓰는 시점에 로그인+가입 동시 적용; A는 현 스키마대로 평문 비교)
- 상황판/조회/설정 뷰 내부 정교화 → C/D/E
- 기존 오암호화 데이터 마이그레이션(없음, fix-forward)

---

## 2. 발견된 결함 (A에서 수정)

**🐞 AES 키 유도 버그** — `frontend/src/utils/crypto.ts:21` 현재:
```ts
const key = CryptoJS.enc.Utf8.parse(ENCRYPTION_KEY.substring(0, 32));
```
계약(`docs/ipc_specification.md` §4-2, 백엔드 `bytes.fromhex`)은 **64hex→32byte**다. 현재 코드는 hex 문자열 앞 32자를 UTF-8로 해석해 **백엔드와 다른 키**를 만든다 → 백엔드 복호화 불가. 또한 `decryptPassword` 부재(눈 아이콘 가시화 불가). A에서 둘 다 수정.

---

## 3. 아키텍처 (접근법 1: 경량 인앱 라우트+세션 컨텍스트)

새 의존성 없이, React Context로 세션을 들고 최상위에서 로그인 상태에 따라 셸을 분기한다(딥링크 불필요한 데스크톱앱이라 라우터 미도입).

```
<SessionProvider>
  <App>
    session == null  → 로그인 전 셸: TopHeader(비활성 내비 + [로그인][회원가입])
                        route ∈ {home, login, signup*, findId*, findPw*}
    session != null  → 로그인 후 셸: TopHeader(상황판/조회/환경설정 + 가게명/마이페이지/로그아웃)
                        route ∈ {dashboard, orders, settings, mypage*}
  </App>
</SessionProvider>
(* = A에서는 "준비중" 스텁, B에서 구현)
```

### 파일 구조
```
frontend/src/
  session/SessionContext.tsx   신규
  shell/TopHeader.tsx          신규
  views/home.tsx               신규
  views/login.tsx              신규
  views/_placeholders.tsx      신규 (Signup/FindId/FindPw/MyPage 스텁)
  types/db.ts                  신규
  types/electron.d.ts          신규
  utils/crypto.ts              수정
  App.tsx                      수정
  views/{dashboard,order_list,settings}.tsx  미변경(로그인 후 셸에서 렌더)
```
원칙: A는 셸/세션/암호화/타입만. 기존 3뷰 내부 미변경(블라스트 반경 최소).

---

## 4. 컴포넌트 명세

### 4.1 `session/SessionContext.tsx`
- 타입: `Session = { shopKey: number; shopName: string; username: string }`
- Context 값: `{ session: Session | null; login(username, password): Promise<{ok: boolean; error?: string}>; logout(): void }`
- `login()`:
  1. `supabase.from('member_info').select('id, shop_name, username, password, is_approved').eq('username', username).maybeSingle()`
  2. 행 없음 → `{ok:false, error:'아이디 또는 비밀번호가 올바르지 않습니다'}`
  3. `password !== input` → 동일 일반화 에러(아이디 존재 여부 비노출)
  4. `is_approved !== 'Y'` → `{ok:false, error:'승인 대기 중인 계정입니다'}`
  5. 성공 → `setSession({shopKey:id, shopName:shop_name, username})`, `{ok:true}`
- `logout()`: `setSession(null)`.
- 평문 비교(현 스키마). 해싱은 B로 이월.

### 4.2 `App.tsx` (수정)
- `<SessionProvider>`로 감싸고, `useSession()`으로 분기.
- `route` 상태(문자열 유니온). 로그인 성공 시 `route='dashboard'`, 로그아웃 시 `route='home'`.
- 로그인 후 본문은 기존 뷰 분기(`dashboard`/`orders`/`settings`) + `mypage` 스텁. 기존 사이드바 마크업은 상단 헤더 셸로 대체.

### 4.3 `shell/TopHeader.tsx`
- props: `{ session, route, onNavigate, onLogout }`.
- 로그인 전: 좌측 브랜드, 중앙 내비(비활성), 우측 [로그인][회원가입].
- 로그인 후: 중앙 내비 [주문접수상황판][주문접수조회][환경설정](active 표시), 우측 `가게명`·[마이페이지]·[로그아웃].
- 서비스 상태 뱃지(RUNNING/STOPPED)는 기존 `window.electronAPI.getServiceStatus()` 폴링 유지(헤더로 이동).

### 4.4 `views/home.tsx`
- 로그인 전 중앙: 마스코트/로고(`assets/hero.png`), 가치 카피("24시간 든든한 우리가게 AI 직원"), [로그인][회원가입] 진입(와이어프레임 slide 10).

### 4.5 `views/login.tsx`
- username/password 입력, 엔터 시 다음 필드 포커스 이동(PRD 6-1), [로그인].
- `[자동로그인]` 체크박스: 표시만(영구화 B). 아이디/비번 찾기 링크 → 스텁 route.
- 제출 → `useSession().login()`; 실패 시 인라인 에러.

### 4.6 `views/_placeholders.tsx`
- `Signup`, `FindId`, `FindPw`, `MyPage` — 각각 "이 화면은 다음 단계(B)에서 제공됩니다" 안내 + 뒤로가기. 셸 내비가 완결되도록 함.

### 4.7 `utils/crypto.ts` (수정)
```ts
const key = CryptoJS.enc.Hex.parse(ENCRYPTION_KEY);   // 64hex → 32byte
// encryptPassword: IV 16바이트 랜덤, CBC/PKCS7, return `${ivHex}:${base64}`
// decryptPassword(dbValue): split(':') → Hex IV/key → CBC 복호 → Utf8 평문, 실패 시 ''
```
- env 미설정 시 기존처럼 경고 로깅 + 안전 폴백.

### 4.8 `types/db.ts`, `types/electron.d.ts`
- `MemberInfo/ServerCallHistory/OrderDetails/SettingInfo` Row 타입(`docs/database_schema.sql` 컬럼 기준).
- `window.electronAPI` 3메서드 타입 전역 선언.
- A에선 정의만(기존 뷰의 `any` 강제 교체는 안 함).

---

## 5. 데이터 흐름
1. 앱 시작 → session=null → HOME 렌더, 서비스 상태 폴링 시작.
2. [로그인] → login.tsx → `login(u,p)` → member_info 조회·검증 → session 설정 → route='dashboard'.
3. 로그인 후 셸: 헤더 내비로 dashboard/orders/settings 전환(기존 뷰), 가게명=session.shopName.
4. [로그아웃] → session=null → HOME.
5. 설정 저장(E, 후속) 시 `encryptPassword`가 이제 계약-호환 암호문 생성 → 백엔드 복호 가능.

## 6. 에러 처리
- 로그인: 일반화 에러(아이디 존재 비노출), 미승인 별도 안내, 네트워크 예외 캐치 → 사용자 메시지.
- crypto: 키 미설정/복호 실패 시 throw 대신 안전값(평문 폴백/'') + 콘솔 경고(기존 패턴 유지).
- supabase 조회 실패: 로그인 실패로 처리(앱 비중단).

## 7. 테스트 · 검증
- **Vitest 도입**(devDependency). 설정 최소(`vitest` + jsdom 불요 — 순수 함수/모킹 위주).
- 테스트:
  1. `crypto` 라운드트립: `decryptPassword(encryptPassword(x)) === x`.
  2. **백엔드 상호호환 벡터**: 백엔드 `crypto.py`로 생성한 고정 `iv_hex:base64`(동일 64hex 키, 알려진 평문)를 `decryptPassword`가 복원 → hex 계약 픽스 실증. (구현 시 백엔드로 벡터 생성해 테스트 상수로 고정.)
  3. `SessionContext.login()`: fake supabase 주입으로 성공 / 비번불일치 / 미승인 / 행없음 4분기.
- **수동 검증 체크리스트**(`npm run dev`): HOME→로그인→로그인 후 셸 전환, 헤더 내비 3탭, 로그아웃→HOME 왕복, (선택)설정 저장 후 백엔드 복호 확인.

## 8. 완료 기준 (DoD)
1. crypto.ts 키가 Hex.parse로 수정 + decryptPassword 구현, Vitest(라운드트립+상호호환벡터) 그린.
2. SessionContext + 로그인 전/후 셸(상단 헤더) + HOME + 최소 로그인 동작, login() 테스트 그린.
3. signup/findId/findPw/mypage 스텁으로 셸 내비 완결.
4. 공유 타입(db/electron) 도입.
5. `npm run build` 성공(타입 에러 0), 수동 체크리스트 1회 통과.

## 9. 비범위 (Out of Scope)
- 가입/찾기/OTP/마이페이지/자동로그인/해싱 → B
- 상황판·조회·설정 뷰 내부 변경 → C/D/E
- ggotAIhp(안드로이드)·hp_call_history → 별도 컴포넌트
- 오암호화 데이터 마이그레이션(없음)

## 10. 미해결/이월 메모
- **비밀번호 해싱**: A는 평문 비교(현 스키마/기존 데이터 호환). B에서 가입+로그인 동시 해싱 전환 결정.
- **`is_approved` 발급 주체**: 승인 플로우(ggotAIhp/관리자)는 본 범위 밖 — A는 'Y'만 통과시킴.
