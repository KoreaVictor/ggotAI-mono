# ggotAIya C — 실시간 주문접수 상황판(대시보드) 정교화 설계서

작성일: 2026-06-07
선행: A·B1·B2a·B2b 머지됨(master `923c8ea`). 안티그래비티가 만든 `frontend/src/views/dashboard.tsx`(가짜 상태·하드코딩·미작동 Realtime·`shop_key=1` 고정)를 실데이터·샵 격리·안전 폴링으로 교체.

## 1. 범위 (PRD 화면6 / F6·F7·F8)

로그인 사장님이 **6대 채널(가게전화·핸드폰1·핸드폰2·가게음성·쇼핑몰·인터라넷)**의 실시간 가동 상태·카운트·현재작업을 한 화면에서 모니터링하고, 백그라운드 윈도우 서비스를 켜고/끈다.

- **6채널 그리드**: 각 칸 `작동`(🟢/🔴) + `현재작업`(파이프라인 상태 문자열) + `오늘작업`(금일 성공 누적).
- **상단 통계**: 오늘 총수집/RPA 성공/실패/대기.
- **실시간 피드**: 최근 수집 내역 타임라인.
- **서비스 제어**: net start/stop(Electron IPC) — 기존 유지.
- **데이터 갱신**: 2.5초 RPC 폴링(Supabase Realtime 제거).
- **보안 하드닝**: `server_call_history` anon 직접권한 회수(이번 범위).

비범위: 주문조회(D)·환경설정(E), 백엔드 파이프라인 상태 기록 변경, Supabase Auth 도입.

## 2. 핵심 결정 (브레인스토밍 2026-06-07)

- **데이터 접근 = 샵 범위 RPC + 하드닝** (Q1=A). 대시보드 읽기는 `get_dashboard` RPC 하나로 일원화. anon 직접 테이블 접근 차단.
- **라이브 갱신 = 안전한 RPC 폴링** (Q2=A). 이 앱은 DB 레벨 신원(Supabase Auth JWT)이 없어 Realtime을 샵 단위로 안전 필터 불가(RLS 키 부재) → Realtime 제거, 2.5초 폴링. (현재 Supabase Realtime publication 비어 있어 기존 구독은 무동작이기도 함.)
- **현재작업 = 파생 only** (Q3=A). 기존 DB 필드(is_order·rpa_status·stt_text)로 4단계 파생. "화원관리 입력중"(RPA 타이핑 중)은 `rpa_status` ready→success 직행이라 관찰 불가 → 생략. 백엔드 중간상태 기록은 후속.
- **세션 토큰 = 기존 remember_token 재사용** (접근1). 로그인 시 항상 `issue_remember_token` 발급 → 인메모리 readToken → get_dashboard 인증. B1 인프라 재사용, 신규 DB 표면 최소.
- **하드닝 범위 = `server_call_history`만 지금**. `order_details`(주문조회 D가 직접 SELECT+UPDATE), `setting_info`(환경설정 E가 직접 SELECT+UPSERT)는 D/E에서 RPC화하며 하드닝(알려진 잔여).

## 3. 데이터 한계 (설계에 반영)

`server_call_history.channel_order`는 `핸드폰`/`가게전화`/`쇼핑몰`/`인터라넷`/`가게음성` **5종만** 구분하고, **수신 라인(핸드폰1 vs 2, 일반전화1 vs 2)을 기록하지 않는다.** 따라서:
- 6채널 그리드는 **6칸 표시**하되, `작동` 점등은 `setting_info` 구성 기반(라인별 구성 여부)이고, `카운트`·`현재작업`은 코어스 `channel_order`로 매핑한다.
- **핸드폰1·핸드폰2 칸은 '핸드폰' 집계를 공유**(동일 카운트/현재작업 표시), 가게전화도 일반전화1·2 합산 = '가게전화'. 정확한 라인 분리는 백엔드에 수신라인 필드를 추가하는 후속 과제.

## 4. 아키텍처 & 데이터 흐름

```
로그인(verify_login) ── 이후 항상 issue_remember_token ──▶ readToken(인메모리; rememberMe면 safeStorage도)
DashboardView ── 2.5초 폴링 ──▶ get_dashboard(shop_key, readToken)  [SECURITY DEFINER, anon]
                                   │ 토큰↔shop_key 검증(member_info.remember_token_hash)
                                   │ server_call_history + order_details + setting_info 서버측 집계
                                   ▼
                          { ok, stats, channels[5 by channel_order], config, feed[8] }
DashboardView:
  - 6채널 그리드: 작동(config ∧ 서비스RUNNING→🟢 else🔴) + 오늘작업(channels.success) + 현재작업(deriveCurrentTask)
  - 서비스 상태/시작·중지 = 기존 Electron IPC 유지
```

**책임 분리**: DB(get_dashboard 1개가 샵범위 읽기 캡슐화) / 프론트(데이터=RPC, 현재작업 파생=순수함수) / 서비스 제어(기존 Electron).

## 5. DB: `get_dashboard` RPC

`get_dashboard(p_shop_key int, p_token text) → json` (SECURITY DEFINER, `search_path=public,extensions`, anon 실행)

**인증**: `member_info where id=p_shop_key`. `remember_token_hash` null / `remember_token_expires_at <= now()` / `crypt(p_token, remember_token_hash)` 불일치 → `{ ok:false, reason:'unauthorized' }`.

**오늘 경계**: `v_today := ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'Asia/Seoul'` (KST 자정 timestamptz). `created_at >= v_today` 필터.

**반환**
```json
{
  "ok": true,
  "stats": { "today_total": 0, "rpa_success": 0, "rpa_fail": 0, "rpa_ready": 0 },
  "channels": [ { "channel_order": "핸드폰", "total": 0, "success": 0 }, ... ],
  "config": { "garjeon": false, "hp1": false, "hp2": false, "voice": true, "mall": false, "intranet": false },
  "feed": [ { "id": 0, "channel_order": "핸드폰", "customer_name": "...", "stt_text": "...",
              "is_order": "Y", "rpa_status": "ready", "created_at": "..." } ]
}
```

**집계**
- `stats.today_total` = server_call_history 오늘 count(shop_key). `rpa_success/fail/ready` = order_details 오늘 rpa_status별 count(shop_key).
- `channels` = `server_call_history sch left join order_details od on od.call_history_id = sch.id`, 오늘, `group by sch.channel_order` → `total = count(distinct sch.id)`(call_history 1행이 order_details 다건이어도 중복 방지), `success = count(*) filter (where od.rpa_status='success')`.
- `config` = setting_info 1행: `garjeon = coalesce(order_landline_1,'')<>'' or coalesce(order_landline_2,'')<>''`, `hp1 = coalesce(order_hp_1,'')<>''`, `hp2 = coalesce(order_hp_2,'')<>''`, `voice = true`(상시), `mall = url+id+pw 모두 있음`, `intranet = url+id+pw 모두 있음`. setting_info 없으면 전부 false(voice만 true).
- `feed` = server_call_history 최근 8건(shop_key, created_at desc). 각 행의 `rpa_status`는 **상관 서브쿼리**로 1건만 — `(select od.rpa_status from order_details od where od.call_history_id = sch.id order by od.id desc limit 1)` (left join 시 다건이면 feed 행이 중복되므로 join 대신 서브쿼리 사용).

**현재작업 문자열은 RPC가 만들지 않음** — feed 원시값을 프론트 순수함수가 파생.

**권한**: `grant execute on function get_dashboard(int,text) to anon`.

## 6. 보안 하드닝 (이번 범위 = server_call_history)

현 상태: 3개 테이블 RLS 비활성 + anon 전권(SELECT/INSERT/UPDATE/DELETE/TRUNCATE) → anon이 아무 샵 데이터 조회·변조·삭제 가능.

```sql
revoke all privileges on table server_call_history from anon, authenticated, public;
grant execute on function get_dashboard(int, text) to anon;
```
- `server_call_history`는 프론트에서 대시보드만 직접 읽었음 → get_dashboard(owner 실행)로 전환하므로 anon 불필요. 백엔드(service_role)는 BYPASS → 수집 INSERT 계속 동작.
- get_dashboard는 owner 권한으로 order_details·setting_info도 읽음 → 그 테이블 anon 권한과 무관하게 대시보드 정상.
- **이월(알려진 잔여)**: `order_details`(D), `setting_info`(E)의 anon 직접권한은 각 모듈에서 RPC화하며 하드닝.

검증: `has_table_privilege('anon','server_call_history','select'|'update'|'delete')=false`, column_privileges anon 0, `has_function_privilege('anon','get_dashboard(integer,text)','execute')=true`, 백엔드 service_role 수집 경로 무관.

## 7. 프론트엔드

### 세션 토큰 배선 (`session/SessionContext.tsx`, `session/rememberToken.ts`)
- `login()`: 성공 시 **항상** `issue_remember_token(p_user_id=shopKey)` 호출 → 인메모리 `readToken` 설정. `rememberMe`이면 기존대로 safeStorage 저장.
- `restoreSession()`: 반환을 `{ session, token } | null`로 확장(현재 `Session|null`) → 자동로그인 복원 시 토큰을 `readToken`으로.
- `logout()`: `readToken=null` + 기존 `clear_remember_token`.
- 컨텍스트에 `readToken: string | null` 노출.

### `dashboard/client.ts` (신규, 순수 래퍼)
- `getDashboard(rpc, shopKey, token) → { ok, data?, reason? }`.
- 타입: `Stats`, `ChannelAgg{channel_order,total,success}`, `Config{garjeon,hp1,hp2,voice,mall,intranet}`, `FeedRow{id,channel_order,customer_name,stt_text,is_order,rpa_status,created_at}`, `DashboardData{stats,channels,config,feed}`.

### `dashboard/currentTask.ts` (신규, 순수함수, Vitest)
- `deriveCurrentTask(row?: FeedRow) → string`:
  - 행 없음 → `'대기'`
  - `is_order` null/undefined: `stt_text` 비었으면 `'STT 분석중'`, 있으면 `'주문정보 분석중'`
  - `'N'` → `'주문 아님'`
  - `'Y'`: `rpa_status` `ready`→`'입력 대기'`, `success`→`'입력 완료'`, `fail`→`'입력 실패'`, 그 외→`'대기'`
- `CHANNELS: {label, channelOrder, configKey}[]` 6칸:
  `가게전화/가게전화/garjeon`, `핸드폰1/핸드폰/hp1`, `핸드폰2/핸드폰/hp2`, `가게음성/가게음성/voice`, `쇼핑몰/쇼핑몰/mall`, `인터라넷/인터라넷/intranet`.
- `latestForChannel(feed, channelOrder) → FeedRow | undefined` (feed는 created_at desc 전제, 첫 매치).

### `views/dashboard.tsx` 재작성
- `useSession()`의 `session.shopKey` + `readToken`으로 `getDashboard` **2.5초 폴링**(setInterval + cleanup). 토큰 없음/`unauthorized` → 에러 표시.
- 6채널 그리드: 칸별 `작동`(config[configKey] ∧ 서비스 RUNNING → 🟢, else 🔴) + `오늘작업`(channels success by channelOrder; 핸드폰1·2 동일값) + `현재작업`(deriveCurrentTask(latestForChannel)).
- 상단 통계 카드·피드 타임라인 = RPC 데이터.
- 서비스 상태/시작·중지 버튼 = 기존 Electron IPC 유지.
- 기존 Supabase Realtime 구독 코드 제거.

## 8. 테스트 & 라이브 단계

### 자동 테스트 (Vitest)
- `currentTask.test.ts`: deriveCurrentTask 전 상태, latestForChannel, CHANNELS 6칸.
- `client.test.ts`: getDashboard 성공/unauthorized/error 매핑(fake rpc).
- 기존 42 passed 유지 + 신규. `npm run build` 성공.

### DB 스모크 (Management API, 컨트롤러)
- 시드: member(알려진 remember_token) + setting_info(일부 채널) + server_call_history 다상태 행 + order_details(ready/success/fail).
- `get_dashboard(shop_key,'토큰')` → stats/channels/config/feed 검증. 네거티브: 틀린/만료 토큰 → unauthorized. 정리 delete.

### 권한 검증
server_call_history anon select/update/delete=false, column_privileges anon 0, get_dashboard anon execute=true, 백엔드 service_role 무관.

### 라이브 단계 (PAT, 컨트롤러 — B2a/B2b 전례)
- ⓐ 마이그레이션: get_dashboard 생성 + server_call_history anon 회수 + grant. (EF 변경 없음, Realtime 활성화 불필요.)
- ⓑ UI E2E(Playwright Node): 로그인 → 대시보드 → 시드 데이터로 6채널·통계·피드·현재작업 렌더 + 폴링 확인.

## 9. 구현 순서 (plan 예고)
1. 마이그레이션(get_dashboard + server_call_history 회수) — 라이브, 컨트롤러.
2. `dashboard/client.ts` + `dashboard/currentTask.ts`(+test) — TDD, 서브에이전트.
3. `SessionContext`/`rememberToken` readToken 배선 — 서브에이전트(세션 영역 주의, 기존 자동로그인 회귀 확인).
4. `dashboard.tsx` 재작성(폴링·그리드, Realtime 제거) — 서브에이전트.
5. 전체 검증 + DB 스모크 + UI E2E + finishing-a-development-branch.

브랜치 `feature/ggotaiya-c-dashboard`(master `923c8ea`에서 분기).
