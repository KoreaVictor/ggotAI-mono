# ggotAI 모노레포 통합 설계 (이력보존 · 라이브경로 유지 · DB계약 일원화)

- 작성일: 2026-06-14
- 상태: 설계 승인됨 (구현 계획 작성 전)
- 관련: `ggotaiya-phone-pipeline-bringup`(메모리), `project-ggotaiorder`(메모리)

## 1. 배경 / 문제

ggotAI 제품은 세 개의 실행체로 구성된다.

| 실행체 | 정체 | 스택 | 실행 환경 |
|---|---|---|---|
| ggotAIhp | 통화 수집 안드로이드 앱(녹음·TTS·Supabase INSERT) | Kotlin / Gradle | 사장님 휴대폰 |
| ggotAIorder/backend | 주문 처리 파이프라인(STT→Gemini→주문→RPA) | Python | 매장 PC(상시 가동) |
| ggotAIorder/frontend (= ggotAIya) | 사장님 대시보드 | React/TS/Vite | 브라우저 |

세 실행체는 **오직 공유 Supabase 프로젝트(DB)** 를 통해서만 통신한다(예: hp가
`server_call_history`에 INSERT → backend가 처리 → frontend가 표시).

### 현재 코드/저장소 실태 (조사로 확정)

- **코드 repo는 둘이다.** order와 ya(frontend)는 이미 한 repo(`ggotAIorder`)에 있다.
  - `C:\ggotAI\ggotAIorder` (리모트 `github.com/KoreaVictor/ggotAIorder`):
    `backend/`(Python) + `frontend/`(ya 웹앱, Vite/Vitest) + `supabase/`(config.toml +
    엣지함수 `send-otp`, `_shared/cors`) + `docs/migrations/`(SQL 8건) + 스키마 계약 테스트.
  - `C:\ggotAIhp` (리모트 `github.com/KoreaVictor/ggotAI`):
    `android/`(Kotlin) + `supabase/migrations/`(SQL 2건: init, unique index) +
    `supabase/functions/`(엣지함수 4건: delete-call, get-settings, upload-call, verify-device).
  - `C:\ggotAI\ggotAIya` 폴더: 문서(pdf/pptx/prd)만 — 코드 아님.
  - `C:\ggotAI` 자체는 아직 git repo가 아니다(모노레포 루트로 사용 가능).

### 핵심 문제: DB 계약 분산

공유 DB 스키마/계약이 **세 군데로 쪼개져** 있다.

- 마이그레이션: hp `supabase/migrations/`(타임스탬프 컨벤션) + order `docs/migrations/`
  (날짜-기능 이름) — 위치도 명명 규칙도 다름.
- 엣지함수: 양쪽 `supabase/functions/`로 분산.

결과적으로 "테이블 구조가 바뀌면 어디를 고쳐야 하는지" 단일 출처가 없고, 한쪽만
고치고 다른 쪽을 빠뜨려도 이를 막아줄 구조가 없다.

### "테이블 변경이 세 소스에 자동 반영되는가?" — 명시적 답

**자동 반영은 불가능하다.** 세 실행체가 서로 다른 언어로 각자 스키마를 표현한다
(ya=TS 타입, order=Python dataclass, hp=Kotlin data class). 컬럼 하나를 바꾸면
세 언어의 모델 코드를 각각 손대야 한다. 모노레포가 이를 없애주지는 못한다.

모노레포가 실제로 주는 것은 **"한 곳에서 정의하고, 빠뜨리면 CI가 잡아준다"** 이다:
단일 출처 마이그레이션 + 원자적(한 PR) 변경 + 언어별 타입생성/계약테스트 + 통합 CI.
ya는 생성 타입으로 컴파일 에러 수준의 거의-자동 감지가 가능하고, order는 기존 스키마
계약 테스트로 드리프트를 감지하며, hp는 Kotlin 한계로 수동이되 계약 테스트로 "어긋나면
막기"는 가능하다.

## 2. 목표 / 비목표

### 목표
1. 세 실행체를 **한 git 저장소(모노레포)** 에서 관리.
2. 각 repo의 **커밋 이력 보존**(git subtree merge).
3. **DB 계약 단일 출처** — 마이그레이션·엣지함수·생성 타입을 루트 `supabase/`로 일원화.
4. **드리프트 차단** — 타입 생성 + 계약 테스트 + 통합 CI.
5. **라이브 무중단** — 방금 검증된 무인기동 체인(작업 스케줄러·Autologon·catch-up)을
   건드리지 않는다.

### 비목표 (YAGNI)
- 런타임 통합(불가능 — 폰/PC/브라우저 서로 다른 실행환경).
- hp(Kotlin)의 완전 자동 타입 동기화(언어 한계).
- 멀티 인스턴스 원자적 attempts increment(별도 과제, 현재 단일 PC 전제).
- Nx/Turborepo 등 모노레포 빌드 오케스트레이터 도입(현 규모 과함).

## 3. 목표 디렉터리 구조

```
C:\ggotAI\                      ← git init (새 모노레포 루트, 리모트 ggotAI)
├─ ggotAIorder/                 ← subtree merge (경로 그대로 = 라이브 무중단)
│   ├─ backend/   (Python)
│   └─ frontend/  (ya 웹앱)
├─ ggotAIhp/                    ← subtree merge (C:\ggotAIhp에서 들여옴)
│   └─ android/   (Kotlin)
├─ supabase/                    ← ★ DB 계약 단일 출처(Supabase CLI 표준 레이아웃)
│   ├─ config.toml              (통합 1개)
│   ├─ migrations/              (hp 2 + order 8 → 타임스탬프 순 단일 이력)
│   └─ functions/               (send-otp + delete-call + get-settings + upload-call + verify-device)
├─ docs/                        (PRD·설계서·릴리스 가이드 통합, ya 문서 포함)
└─ .github/workflows/ci.yml     (통합 CI)
```

핵심 원칙: **앱 코드(`backend`, `frontend`, `android`)는 각 앱 폴더에 그대로 두고,
DB 계약(`supabase/`)만 루트로 끌어올려 단일화**. 작업 스케줄러가 보는
`C:\ggotAI\ggotAIorder\backend\run_dev.py` 경로는 불변 → 라이브 무중단.

## 4. 이력보존 병합 메커니즘

1. `C:\ggotAI`에 `git init`, 새 리모트 `github.com/KoreaVictor/ggotAI` 연결(또는 신규).
2. `git subtree add --prefix=ggotAIorder <ggotAIorder 소스> master` → order 전체 이력 보존.
3. `git subtree add --prefix=ggotAIhp <ggotAIhp 소스> <hp 기본브랜치>` → hp 전체 이력 보존.
4. 병합 후 중첩 `.git`(`ggotAIorder/.git`, 구 `C:\ggotAIhp/.git`) 정리.
   워킹 파일은 그대로라 가동 중 pythonw 프로세스에 영향 없음.
5. 기존 두 리모트는 아카이브/읽기전용으로 보존(롤백 안전망). 새 작업은 모노레포로.

> 주의: `ggotAIhp` 리모트 이름이 이미 `ggotAI`다. 모노레포 리모트로 이 이름을 재사용할지
> 신규 리모트를 만들지는 구현 계획에서 확정한다(기존 hp 단독 푸시 이력과의 충돌 회피).

## 5. DB 계약 단일화 (핵심)

### 5.1 마이그레이션 통합
- 대상: hp `supabase/migrations/`(2) + order `docs/migrations/`(8).
- 방식: order의 날짜-기능 파일을 타임스탬프 컨벤션(`YYYYMMDDHHMMSS_<slug>.sql`)으로
  리네이밍해 `supabase/migrations/`에 **시간순 단일 이력**으로 배치.
  (hp init=2026-05-18 → order 기능들=2026-06-06~14 → 자연 정렬됨.)
- 라이브 DB엔 이미 전부 적용된 상태이므로, 통합본은 **"신규 환경 재현 + 기록용 단일 진실"**
  역할이다. 적용 멱등성/순서는 `supabase db diff`로 라이브 스키마와 일치 검증.

### 5.2 엣지함수 통합
- 양쪽 5개를 루트 `supabase/functions/`로 모음(`_shared/cors.ts` 공용화).
- 배포는 `supabase functions deploy`를 한 곳에서 수행.

### 5.3 타입 생성 (자동에 가깝게)
- `supabase gen types typescript` → `frontend/src/types/database.ts` 갱신.
- ya는 이 타입을 import → 컬럼 rename/삭제 시 **컴파일 에러**로 즉시 감지.

### 5.4 계약 테스트
- order: 기존 `backend/tests/test_phase4_schema_contract.py`(및 `test_phase4_schema.py`)
  를 활용/확장해 라이브 스키마↔Python dataclass 드리프트 감지.
- hp: Kotlin 타입생성 불가 → 같은 PR에서 계약 테스트/스키마 문서로 "어긋나면 막기".

## 6. 통합 CI (`.github/workflows/ci.yml`)

PR 1건에서 세 검증을 동시 실행해, 어느 실행체든 계약이 깨지면 머지 전 차단한다.

- backend: `pytest` (현재 121 passed / 5 skip 기준).
- frontend: `vitest` + `build`.
- (선택) android: `./gradlew assembleDebug`.
- **types-in-sync 체크**: 타입 재생성 후 `git diff`가 비어 있어야 통과
  (스키마를 바꾸고 타입을 안 갱신하면 빨강).

## 7. 라이브 안전 / 롤백

- 병합은 파일 이동이 거의 없다(order 경로 유지) → 작업 스케줄러(`ggotAIorder`),
  Autologon, `backend/.env`, 로그/백업 경로 전부 무변경.
- hp는 상시 서비스가 아님 → Android Studio 프로젝트 경로만 `C:\ggotAI\ggotAIhp\android`
  로 한 번 갱신.
- 롤백: 모노레포 루트 `.git` 제거 시 원래 두 repo 워킹 카피로 복귀(원격 보존).

## 8. 테스트 / 검증 기준 (완료 정의)

- 병합 직후 회귀0: backend 121 passed/5 skip 재현, frontend vitest+build 통과.
- 라이브: pythonw 재기동 없이 정상 가동(경로 불변 확인). 필요 시 작업 스케줄러
  수동 1회 재기동 후 catch-up 로그 정상.
- DB 스모크: `supabase db diff` 결과가 통합 마이그레이션과 라이브 스키마 일치,
  타입 생성 `git diff` 0.

## 9. 결과 흐름 ("컬럼 바꾸면?")

`supabase/migrations`에 마이그레이션 1건 추가 → 타입 재생성(ya 자동 반영)
→ order/hp 모델 수정 → 한 PR → CI가 빠뜨린 곳을 빨갛게 표시.

## 10. 미해결/구현계획에서 확정할 사항

- 모노레포 리모트: 기존 `ggotAI`(hp) 재사용 vs 신규 생성.
- subtree 소스: 로컬 경로 vs 원격 URL.
- order `docs/migrations/` 파일의 정확한 타임스탬프 매핑(라이브 적용 순서 기준).
- android CI를 필수로 둘지 선택으로 둘지(러너 비용/시간).
