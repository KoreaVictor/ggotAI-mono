# ggotAIya 모듈 E(환경설정) 설계서

- 날짜: 2026-06-10
- 범위: 안티그래비티 `frontend/src/views/settings.tsx`(수집 환경설정 화면, PRD 화면9) 정교화
- 패턴: 모듈 C/D에서 검증된 **샵범위 RPC + remember_token 인증 + anon 직접권한 하드닝** 재사용
- 선행 완료: A·B1·B2a·B2b·C·D (D 머지커밋 `44b07a9`)

---

## 1. 목적과 범위

로그인한 꽃집이 자기 샵의 수집 환경설정(수신 기기, 외부 채널 연동, 알림, 템플릿, 점검 간격)을 조회·저장할 수 있게 한다. 동시에 현재 `settings.tsx`가 사용하는 `setting_info` **anon 직접 SELECT/UPSERT 권한을 회수(하드닝)** 하여 C/D와 동일 보안 수준으로 끌어올린다.

### 핵심 보안 동기
현재 `settings.tsx`는 `setting_info`를 `select('*')`로 직접 읽는다. 이 응답엔 **암호화된 외부 채널 비밀번호**(`shopping_mall_password`/`intranet_password`)가 포함된다. AES 키가 프론트 `.env`(`VITE_AES_ENCRYPTION_KEY`)에 임베드돼 있으므로, anon이 ciphertext를 읽으면 복호화가 가능하다. E는 이 경로를 막는다.

### 범위에 포함
- setting_info 전체 폼 RPC화: 수신 기기(핸드폰1·2/일반전화1·2), 쇼핑몰·인트라넷 연동(URL/ID/비번/점검간격), 알림 사용여부·수신번호·성공/실패 템플릿
- `shop_key=1` 하드코딩 제거 → `session.shopKey`/`readToken`(C/D에서 배선)
- 비밀번호 **가시화 = "🔒 설정됨/미설정" 뱃지**(ciphertext 미반환, write-only 유지)
- `setting_info` anon/authenticated/public 직접권한 회수

### 범위에서 제외 (사용자 결정)
- **눈 아이콘 복호화 표시(평문 reveal)** — get_settings가 ciphertext를 반환하지 않으므로 불가. 가장 안전한 선택. `crypto.ts`의 `decryptPassword`는 프론트 미사용으로 남는다(crypto.test의 계약 벡터로 유지, 제거는 범위 밖).
- 비밀번호 명시적 삭제(클리어) UX — 공란=기존 유지 시맨틱과 충돌. 후속 이월(채널 비활성화는 URL/ID 비우면 됨).
- 서버측 암호화 전환 — 암호화는 클라이언트 유지(AES 계약 보존).

---

## 2. 아키텍처

백엔드(Python, service_role `load_config`) **무변경** — anon 권한 회수에 영향받지 않는다. 신규 DB RPC 2개 + 하드닝 1건, 프론트 1개 신규 모듈 + 1개 뷰 재작성.

| 구성 | 역할 |
|---|---|
| `get_settings(shop_key, token)` RPC | SECURITY DEFINER. 인증 → setting_info 행 반환하되 **비번 ciphertext 2개 제외**, `has_shopping_mall_password`/`has_intranet_password` boolean 추가 |
| `save_settings(shop_key, token, settings jsonb, sm_pw, it_pw)` RPC | SECURITY DEFINER. 인증 → UPDATE(없으면 INSERT) upsert. 비번 파라미터 null=기존 보존 |
| 하드닝 | `revoke all on setting_info from anon, authenticated, public`. 두 RPC만 anon EXECUTE |
| `settings/client.ts` (+test) | `getSettings`/`saveSettings` 순수 래퍼(`DashRpc` 재사용) |
| `views/settings.tsx` (재작성) | shop_key 하드코딩 제거, 비번 설정됨 뱃지, RPC 경유 |

---

## 3. 데이터 계약

### 3.1 setting_info 컬럼 (19, 확인됨)
`id`(PK), `shop_key`(NOT NULL), `use_notification`(char,'Y'), `notification_phone_number`, `rpa_success_message`(text), `rpa_fail_message`(text), `order_hp_1`(**NOT NULL**), `order_hp_2`, `order_landline_1`, `order_landline_2`, `shopping_mall_url`, `shopping_mall_id`, **`shopping_mall_password`**(secret), `intranet_url`, `intranet_id`, **`intranet_password`**(secret), `shopping_mall_check_interval`(int,10), `intranet_check_interval`(int,30), `created_at`.

### 3.2 `get_settings` RPC

```
get_settings(p_shop_key int, p_token text) returns json
```
- **인증**: C/D와 동일 — member 조회 후 remember_token_hash/만료/`crypt(p_token, hash)` 검사. 실패 시 `{"ok": false, "reason": "unauthorized"}`.
- **동작**: `select * into v_set from setting_info where shop_key = p_shop_key`.
  - 행 없음 → `{"ok": true, "settings": null}` (프론트가 기본값 폼 표시)
  - 행 있음 → `{"ok": true, "settings": { ...비번 2개 제외 전 컬럼..., "has_shopping_mall_password": <bool>, "has_intranet_password": <bool> }}`
  - `has_*` = `coalesce(password,'') <> ''`.
- 반환 settings에 포함되는 필드: `use_notification, notification_phone_number, rpa_success_message, rpa_fail_message, order_hp_1, order_hp_2, order_landline_1, order_landline_2, shopping_mall_url, shopping_mall_id, intranet_url, intranet_id, shopping_mall_check_interval, intranet_check_interval, has_shopping_mall_password, has_intranet_password`. (`id`/`created_at`/`shop_key`/비번 ciphertext는 미반환.)

### 3.3 `save_settings` RPC

```
save_settings(
  p_shop_key int,
  p_token    text,
  p_settings jsonb,              -- 비-비번 편집 필드 일괄
  p_shopping_mall_password text default null,  -- null=기존 유지, 값=교체(ciphertext)
  p_intranet_password      text default null
) returns json
```
- **인증**: 동일.
- **검증**: `order_hp_1`은 NOT NULL → `coalesce(nullif(p_settings->>'order_hp_1',''), '')='' ` 면 `{"ok": false, "reason": "order_hp_1_required"}`.
- **upsert(제약 비의존 패턴)**:
  ```
  update setting_info set
    use_notification = coalesce(p_settings->>'use_notification','Y'),
    notification_phone_number = nullif(p_settings->>'notification_phone_number',''),
    rpa_success_message = p_settings->>'rpa_success_message',
    rpa_fail_message = p_settings->>'rpa_fail_message',
    order_hp_1 = p_settings->>'order_hp_1',
    order_hp_2 = nullif(p_settings->>'order_hp_2',''),
    order_landline_1 = nullif(p_settings->>'order_landline_1',''),
    order_landline_2 = nullif(p_settings->>'order_landline_2',''),
    shopping_mall_url = nullif(p_settings->>'shopping_mall_url',''),
    shopping_mall_id  = nullif(p_settings->>'shopping_mall_id',''),
    intranet_url = nullif(p_settings->>'intranet_url',''),
    intranet_id  = nullif(p_settings->>'intranet_id',''),
    shopping_mall_check_interval = coalesce((p_settings->>'shopping_mall_check_interval')::int, 10),
    intranet_check_interval      = coalesce((p_settings->>'intranet_check_interval')::int, 30),
    shopping_mall_password = coalesce(p_shopping_mall_password, shopping_mall_password),
    intranet_password      = coalesce(p_intranet_password, intranet_password)
  where shop_key = p_shop_key;
  -- GET DIAGNOSTICS; if 0 → INSERT(동일 매핑, 비번은 p_* 그대로)
  ```
- 반환 `{"ok": true}` / `{"ok": false, "reason": ...}`.
- **비번 보존**: 프론트가 비번을 새로 입력했을 때만 `encryptPassword`로 암호화한 ciphertext를 전달, 아니면 null → `coalesce`로 기존 보존.

### 3.4 하드닝

```
revoke all privileges on table setting_info from anon, authenticated, public;
grant execute on function get_settings(int, text) to anon;
grant execute on function save_settings(int, text, jsonb, text, text) to anon;
```
- 검증: `column_privileges`에서 anon/authenticated의 setting_info count=0 (B2b/D에서 실측 확인된 계약).
- 백엔드 service_role 무관. 프론트 직접 접근 화면은 `settings.tsx` 단 하나(grep 확인) → 회귀 위험 없음.
- 신규 함수 ALTER DEFAULT PRIVILEGES 자동부여 대비 `grant ... to anon` 명시.

---

## 4. 프론트엔드 변경

### 4.1 `settings/client.ts` (+ `settings/client.test.ts`)
C/D의 `client.ts` 형태. `DashRpc`는 `../dashboard/client`에서 import. `SettingsData` 인터페이스(3.2 반환 필드) 정의.
- `getSettings(rpc, shopKey, token) -> {ok, settings?, reason?}`
- `saveSettings(rpc, shopKey, token, settings, smPw, itPw) -> {ok, reason?}`
- 테스트: ok(settings 반환)/settings null/unauthorized/error, save ok/order_hp_1_required/error, 인자 매핑(비번 null 전달 포함).

### 4.2 `views/settings.tsx` 재작성
- `supabase.from('setting_info')` 직접 쿼리 → `getSettings`/`saveSettings` + `useSession()`의 `shopKey`/`readToken`. `defaultShopKey=1` 제거.
- 로드: `getSettings` → settings 있으면 폼 채움(+ `has_*`로 비번 뱃지), 없으면 기본값 폼.
- **비번 필드**: 입력란은 write-only 유지("수정할 때만 입력"). 라벨 옆 **`has_*` 기반 뱃지** — `true`면 "🔒 설정됨", `false`면 "미설정".
- 저장: 폼 상태를 settings 객체로 빌드, 입력된 비번만 `encryptPassword`로 암호화해 전달(아니면 null). `saveSettings` 호출, 성공 시 비번 입력란 비우기 + `has_*` 갱신(입력했으면 true), 성공 배너.
- 미사용 import 정리.

---

## 5. 검증 계획

1. **마이그레이션 SQL** `docs/migrations/2026-06-10-e-settings.sql` 작성 → Management API(curl UA, PAT) 적용.
2. **라운드트립 스모크**: 토큰행 시드 → `save_settings`(신규=INSERT) → `get_settings`로 필드 라운드트립 확인 + `has_*` boolean → `save_settings`(비번 null=기존 보존, 다른 필드만 변경) 후 비번 컬럼 불변 확인 → `order_hp_1` 공란 거부 → 권한검증(`column_privileges`=0) → 스모크 데이터 정리.
3. **프론트**: vitest(settings/client) + `npm run build`.
4. **UI E2E(Playwright Node판)**: 로그인 → 환경설정 진입 → 필드 수정·비번 입력 → 저장 → 재로드 시 반영 + 비번 "설정됨" 뱃지 확인.

---

## 6. 알려진 한계 / 이월

- **비번 평문 reveal 없음**: 보안상 ciphertext 미반환. 설정됨/미설정 뱃지로만.
- **비번 명시적 클리어 UX 없음**: 공란=기존 유지. 후속.
- **암호화 클라이언트측 유지**: AES 키가 프론트 임베드(기존 아키텍처 제약). E는 anon READ 경로만 차단 — authenticated 경로도 ciphertext를 안 받으므로 키 노출 표면이 축소됨.
- **하드닝 완료 후 잔여 anon 직접권한 표면 없음**: member_info(B1·B2b)·server_call_history(C)·order_details(D)·setting_info(E) 전부 회수 완료 예정.

---

## 7. 재사용 자산
- `session.shopKey`/`readToken`(C/D 배선), get_dashboard/get_orders 인증 블록(remember_token_hash + crypt)
- `dashboard/client.ts`의 `DashRpc` 주입 패턴, `utils/crypto.ts`의 `encryptPassword`(기존)
- Management API + curl UA 적용(PAT), `column_privileges` count=0 권한검증
- Playwright **Node판**(Python판 불가)
