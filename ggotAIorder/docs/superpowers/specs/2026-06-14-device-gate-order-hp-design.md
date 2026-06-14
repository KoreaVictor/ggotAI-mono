# 기기 인증을 order_hp 등록 기반으로 전환 (A안) 설계

- 작성일: 2026-06-14
- 상태: 설계 승인됨 (구현 계획 작성 전)
- 관련: `ggotai-monorepo-integration`(메모리), `ggotaiya-phone-pipeline-bringup`(메모리)

## 1. 배경 / 문제

상황판(대시보드)에서 핸드폰1·핸드폰2가 "미사용"으로 표시되는데, 실제로는 ggotAIhp가
핸드폰 통화를 수집·업로드하고 있다. 원인은 "미사용" 판정이 **`setting_info.order_hp_1/2`
등록 여부**(config 기반)인데, 데이터 수집은 그 설정과 무관하게 들어오기 때문이다
(현재 기기 인증은 `member_info.mobile_number` 기준).

즉 "설정 안 한 번호인데도 데이터가 들어와서 표시가 어긋난다."

### 해결 방향 (A안)

대시보드 표시 로직을 바꾸는 대신, **등록된 번호에서만 데이터가 들어오도록 게이트**를 둔다:
기기(앱)의 전화번호가 그 가게의 `order_hp_1` 또는 `order_hp_2`에 등록돼 있어야 앱이
동작(로그인 통과)하고, 등록 안 됐으면 차단한다. 그러면 미등록 번호로는 수집 자체가
안 되므로 기존 config 기반 "미사용" 표시가 **자연히 진실**이 된다.

테스트 단계라 기존 운영 가게에 대한 롤아웃 영향은 없다.

## 2. 현재 구조 (조사로 확정)

기기 식별을 4개 엣지함수가 모두 **`member_info.mobile_number = <기기 전화번호>`** +
`is_approved='Y'` 로 수행한다.

| 엣지함수 | 현재 조회 | 키 파라미터 |
|---|---|---|
| `verify-device` | `member_info.mobile_number = phone` | `?phone=` |
| `get-settings` | `member_info.mobile_number = phone` | `?phone=` |
| `upload-call` | `member_info.mobile_number = userPhoneNumber` | `user_phone_number` |
| `delete-call` | (동일 패턴) | `user_phone_number` |

- 앱(Android `LoginActivity`)은 `TelephonyManager.line1Number`로 기기 SIM 번호를 읽어
  숫자만 남겨(`[^0-9]` 제거) 서버로 보낸다. 매칭 실패 시 서버가 `401 AUTH_ERR`를 주고
  앱은 이를 "미승인 단말"로 처리해 로그인/수집을 막는다(`DeviceStatus`).
- `setting_info`는 `shop_key`(= member_info.id)로 가게에 연결된다.
- `order_hp_1/2`는 **웹 환경설정**(`save_settings` RPC)으로 입력되며 `010-1234-5678`처럼
  대시가 포함될 수 있다. 앱이 보내는 기기번호는 숫자만이다 → **정규화 비교 필수**.

## 3. 목표 / 비목표

### 목표
1. 기기 인증 기준을 `member.mobile_number` → `setting_info.order_hp_1/order_hp_2`로 전환(A안).
2. 매칭된 가게의 member가 승인 상태(`is_approved='Y'`)인지 계속 확인(안전장치 유지).
3. 미등록 기기는 4개 엣지함수 전부에서 일관되게 차단(`AUTH_ERR`).
4. 결과적으로 대시보드 "미사용" 표시가 실제 수집 가능 여부와 일치.

### 비목표 (YAGNI)
- 대시보드 hp1/hp2 피드를 `channel_classification`로 분리하는 정밀화(게이트로 표시가
  이미 진실해지므로 불필요).
- 앱의 기기번호 획득 방식(`line1Number`) 개선(기존 메커니즘 유지; A안이 악화시키지 않음).
- 멀티 인스턴스/원자성 등 무관한 리팩터.

## 4. 설계

### 4.1 신규 RPC `resolve_device_shop(p_phone text)`
`SECURITY DEFINER` 함수. 매칭 로직을 DB 한 곳에 두어 4개 엣지함수가 공유(DRY).

```sql
create or replace function resolve_device_shop(p_phone text)
returns table (shop_key int, shop_name text, representative_name text,
               is_approved text, slot int)
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
-- service_role(엣지함수)만 실행
```

- 빈 전화/빈 order_hp는 매칭 제외(`<> ''` 가드)로 "둘 다 빈값이라 우연히 매칭" 방지.
- 마이그레이션 파일: `supabase/migrations/<타임스탬프>_resolve_device_shop.sql`.

### 4.2 공유 헬퍼 `supabase/functions/_shared/resolveShop.ts`
```ts
import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export interface ResolvedShop {
  shop_key: number;
  shop_name: string;
  representative_name: string | null;
  is_approved: string;
  slot: number | null;
}

// 기기 전화번호로 가게를 해석한다. 미등록/미승인이면 null.
export async function resolveShopByDevicePhone(
  supabase: SupabaseClient,
  phone: string,
): Promise<ResolvedShop | null> {
  const { data, error } = await supabase
    .rpc("resolve_device_shop", { p_phone: phone })
    .maybeSingle();
  if (error || !data) return null;
  if (data.is_approved !== "Y") return null;
  return data as ResolvedShop;
}
```

### 4.3 엣지함수 4종 수정
각 함수의 `member_info.mobile_number` 조회 블록을 `resolveShopByDevicePhone(...)`로 교체.

- **verify-device**: 성공 시 기존과 동일한 `data{shop_key, shop_name, representative_name,
  is_approved}` 반환(+ 선택적으로 `slot`). 실패 시 `401 AUTH_ERR`,
  메시지: `"주문받는 핸드폰 번호로 등록되지 않은 기기입니다. 환경설정에서 등록해주세요."`
- **get-settings / upload-call / delete-call**: 동일하게 헬퍼로 가게 해석.
  `shop_key`는 이후 로직(INSERT의 shop_key 등)에 그대로 사용. 실패 시 기존과 같은
  `AUTH_ERR` 응답 형식 유지.
- `error_code`는 기존 `AUTH_ERR` 유지 → 앱의 기존 처리(로그인 차단) 그대로 동작.

### 4.4 변경 없는 영역
- **Android 앱**: 기기번호 전송·`AUTH_ERR` 처리 모두 기존 그대로 → 코드 변경 없음.
  (등록 안 된 기기는 자동으로 로그인 차단됨.)
- **대시보드(get_dashboard/프론트)**: 변경 없음. 게이트로 등록된 번호만 수집되므로
  config 기반 "미사용" 표시가 진실이 됨.

## 5. 데이터 흐름 (변경 후)

1. 가게: 웹 회원가입 → 승인(`is_approved='Y'`).
2. 가게: 웹 환경설정에서 `order_hp_1`(필요시 `order_hp_2`)에 **주문받는 핸드폰 번호** 등록.
3. 그 번호의 폰에 ggotAIhp 설치 → 앱이 기기번호 전송 → `verify-device` →
   `resolve_device_shop`가 order_hp와 정규화 매칭 → 승인된 가게면 로그인 통과.
4. 미등록 번호의 폰 → 매칭 실패 → `401 AUTH_ERR` → 앱 로그인 차단.
5. 이후 `upload-call`/`get-settings`/`delete-call`도 동일 게이트 적용.

## 6. 테스트 / 검증 (현실적 접근)

엣지함수는 Deno 런타임이라 본 repo CI(파이썬 pytest / 노드 vitest)에 테스트 인프라가
없다. 따라서 라이브 스모크로 검증한다.

- **RPC 단위(라이브 스모크)**: test꽃집(shop_key=19)에 `order_hp_1`을 임의 번호로 등록 후
  `resolve_device_shop` 호출 →
  - 등록번호(대시 포함/미포함 양식 모두) → shop_key=19, slot=1 반환
  - 미등록번호 → 0행
  - order_hp 미설정 가게 → 0행
  - 빈 문자열 입력 → 0행(빈값 가드)
- **엣지함수(라이브 호출)**: `verify-device?phone=<등록번호>` → 200 success;
  `?phone=<미등록번호>` → 401 `AUTH_ERR`. 동일하게 get-settings도 확인.
- **회귀**: 백엔드 pytest / 프론트 vitest는 이 변경과 무관 → 그린 유지 확인.
- 검증 후 테스트로 넣은 order_hp 값은 원복(또는 정리).

## 7. 위험 / 주의

- **정규화 누락 시 전면 차단**: order_hp와 기기번호 형식이 다른데 정규화를 안 하면 매칭이
  전부 실패해 모든 기기가 로그인 불가가 된다 → RPC의 `regexp_replace` 정규화가 핵심.
- **국가코드 차이**: 기기번호가 `+8210…`로 올 가능성. `line1Number`는 보통 `010…`이나,
  필요 시 정규화에 `+82→0` 변환 추가 고려(우선은 숫자추출만, 스모크에서 실제 값 확인 후 결정).
- **설정 선행 의존**: 이제 웹에서 order_hp를 먼저 등록해야 앱이 동작한다. 앱의 차단
  메시지로 사용자에게 "환경설정에서 등록" 안내 필요(메시지에 포함).
- **member.mobile_number의 역할 축소**: 기기 식별에서 더는 쓰이지 않음(계정 식별/연락처
  용도로만 남음). 회원가입/마이페이지 로직은 그대로 둔다(무관).

## 8. 완료 정의

- 마이그레이션 적용 + `resolve_device_shop` 라이브 스모크 통과(등록=매칭, 미등록=0행).
- 4개 엣지함수 배포 후 등록/미등록 번호로 verify-device 200/401 확인.
- 백엔드 pytest·프론트 vitest 회귀 0.
- 앱 코드 무변경 확인(기기 차단이 기존 AUTH_ERR 경로로 동작).
