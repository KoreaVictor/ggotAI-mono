# ggotAI 모노레포 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `C:\ggotAI`를 git 모노레포 루트로 만들어 ggotAIorder(backend+frontend)와 ggotAIhp(android)를 커밋 이력 보존으로 병합하고, DB 계약(supabase 마이그레이션·엣지함수·생성타입)을 루트 `supabase/`로 일원화한다.

**Architecture:** 핵심은 **history-preserving in-place 병합**이다. `git read-tree --prefix=<dir>/`를 **`-u` 없이(인덱스만)** 사용하면 워킹트리 파일을 건드리지 않으므로, 라이브로 가동 중인 backend(pythonw, Task Scheduler `ggotAIorder`)를 **멈추지 않고** order를 `ggotAIorder/` 경로 그대로 모노레포에 편입할 수 있다. hp는 `C:\ggotAIhp`에서 `C:\ggotAI\ggotAIhp`로 물리 이동 후 동일 기법으로 편입. 이후 `supabase/`를 루트로 통합하고 타입생성·계약테스트·통합 CI로 스키마 드리프트를 차단한다.

**Tech Stack:** git (subtree/merge -s ours/read-tree), Supabase CLI(`supabase gen types`, `db diff`, `functions deploy`), Python/pytest(backend), Vite/Vitest(frontend), Gradle(android), GitHub Actions(CI).

---

## 설계 출처

`docs/superpowers/specs/2026-06-14-monorepo-integration-design.md` 를 구현한다.

## 전제 / 사실 (조사로 확정, 2026-06-14)

- `C:\ggotAI` 는 git repo 아님(루트로 사용 가능). 하위에 `ggotAIorder/`(git repo, 리모트 `…/ggotAIorder`), `ggotAIya/`(문서만).
- `C:\ggotAIhp` 는 git repo(리모트 `…/ggotAI`, 기본 브랜치 `master`).
- order/frontend = ya 웹앱(이미 같은 repo).
- **이력에 없는(gitignore) 로컬 전용 파일 — 반드시 보존**:
  order `backend/.env`, `frontend/.env`, `backend/.venv/`, `frontend/node_modules/`;
  hp `.env`, `android/local.properties`, `android/build/`, `android/.gradle/`.
- 라이브: Task Scheduler `ggotAIorder` → `C:\ggotAI\ggotAIorder\backend\run_dev.py`(pythonw). `load_config()` 가 매 호출마다 `backend/.env` 를 디스크에서 읽음 → **backend 워킹파일은 가동 중 변경 금지**.

## 파일/디렉터리 구조 (완료 후)

```
C:\ggotAI\
├─ .git/                         (신규 모노레포)
├─ .gitignore                    (루트 통합 — 각 앱 .gitignore는 하위 유지)
├─ README.md                     (모노레포 안내)
├─ ggotAIorder/                  (이력보존 편입, 경로 불변)
│   ├─ backend/  frontend/  docs/ ...
├─ ggotAIhp/                     (이력보존 편입, C:\ggotAIhp에서 이동)
│   └─ android/ ...
├─ supabase/                     (DB 계약 단일 출처)
│   ├─ config.toml
│   ├─ migrations/               (hp 2 + order 8, 타임스탬프 정렬)
│   └─ functions/                (send-otp, delete-call, get-settings, upload-call, verify-device)
├─ docs/                         (통합 문서)
└─ .github/workflows/ci.yml
```

> 주의: order 기존 `supabase/`(config.toml + send-otp)와 `docs/migrations/`, hp 기존 `supabase/`는 **루트 `supabase/`로 이동**하며, 이동 후 하위 위치엔 남기지 않는다(단일 출처).

---

## Phase 0 — 안전망 (되돌릴 수 없는 작업 전 필수)

### Task 0.1: 두 원격 백업 동기화

**Files:** 없음(git 원격 작업)

- [ ] **Step 1: order 작업본을 origin에 푸시**

이 plan/spec 커밋이 있는 브랜치를 origin에 올려 보존한다.

Run:
```bash
git -C /c/ggotAI/ggotAIorder push -u origin docs/monorepo-integration-design
```
Expected: 브랜치가 origin에 생성됨(`* [new branch]`).

- [ ] **Step 2: order master가 origin과 일치하는지 확인**

Run:
```bash
git -C /c/ggotAI/ggotAIorder fetch origin && git -C /c/ggotAI/ggotAIorder rev-parse master origin/master
```
Expected: 두 해시가 동일(로컬 master = origin/master). 다르면 master 푸시 먼저.

- [ ] **Step 3: hp master가 origin과 일치하는지 확인**

Run:
```bash
git -C /c/ggotAIhp fetch origin && git -C /c/ggotAIhp rev-parse master origin/master
```
Expected: 두 해시 동일. 다르면 `git -C /c/ggotAIhp push origin master`.

### Task 0.2: 로컬 전용 파일 + 워킹카피 풀 백업

**Files:** `C:\ggotAI_backup_2026-06-14\` (백업 대상)

- [ ] **Step 1: 워킹카피 전체를 백업 폴더로 복사(.venv/node_modules/.env 포함)**

Run (PowerShell, 시간 소요):
```powershell
$dst = "C:\ggotAI_backup_2026-06-14"
New-Item -ItemType Directory -Force $dst | Out-Null
robocopy "C:\ggotAI\ggotAIorder" "$dst\ggotAIorder" /E /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
robocopy "C:\ggotAIhp" "$dst\ggotAIhp" /E /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
"backup done"
```
Expected: `backup done`. 두 폴더가 백업됨.

- [ ] **Step 2: 핵심 비밀파일이 백업에 들어갔는지 확인**

Run:
```bash
ls "/c/ggotAI_backup_2026-06-14/ggotAIorder/backend/.env" \
   "/c/ggotAI_backup_2026-06-14/ggotAIorder/frontend/.env" \
   "/c/ggotAI_backup_2026-06-14/ggotAIhp/.env" \
   "/c/ggotAI_backup_2026-06-14/ggotAIhp/android/local.properties"
```
Expected: 4개 파일 모두 존재.

### Task 0.3: 라이브 baseline 기록

**Files:** 없음

- [ ] **Step 1: 현재 pythonw PID와 backend 테스트 baseline 기록**

Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe -m pytest /c/ggotAI/ggotAIorder/backend -q 2>&1 | tail -3
```
Expected: `121 passed, 5 skipped` (이 plan 시점 기준). 이 수치를 완료 정의의 회귀 기준으로 삼는다.

---

## Phase 1 — 모노레포 스켈레톤

### Task 1.1: 루트 git init + 초기 커밋

**Files:**
- Create: `C:\ggotAI\.gitignore`, `C:\ggotAI\README.md`

- [ ] **Step 1: 루트에서 git init**

Run:
```bash
cd /c/ggotAI && git init && git symbolic-ref HEAD refs/heads/master
```
Expected: `Initialized empty Git repository in C:/ggotAI/.git/`.

> 경고: 이 시점 이후 `C:\ggotAI`가 repo가 되며, 하위 `ggotAIorder/.git`은 아직 존재(중첩). Phase 2/3에서 정리한다. 그 전까지 `git status`에 `ggotAIorder/`가 보이지 않을 수 있음(중첩 repo는 gitlink 후보) — 정상.

- [ ] **Step 2: 루트 .gitignore 작성**

루트엔 OS/에디터 노이즈만. 앱별 무시규칙은 하위 `.gitignore` 유지.
```gitignore
# OS / editor
.DS_Store
Thumbs.db
.idea/
*.iml

# 백업 폴더(혹시 루트 하위에 생기면)
ggotAI_backup_*/
```

- [ ] **Step 3: README 작성**

```markdown
# ggotAI 모노레포

| 경로 | 내용 | 스택 |
|---|---|---|
| `ggotAIorder/backend` | 주문 처리 파이프라인 | Python |
| `ggotAIorder/frontend` | 사장님 대시보드(ggotAIya) | React/TS/Vite |
| `ggotAIhp/android` | 통화 수집 앱 | Kotlin |
| `supabase/` | DB 계약 단일 출처(마이그레이션·엣지함수·생성타입) | Supabase |

각 실행체는 공유 Supabase 프로젝트(DB)로만 통신한다.
스키마 변경 흐름: `supabase/migrations` 추가 → 타입 재생성 → 각 앱 모델 수정 → 한 PR → CI 검증.
```

- [ ] **Step 4: 초기 커밋**

Run:
```bash
cd /c/ggotAI && git add .gitignore README.md && git commit -m "chore: ggotAI 모노레포 루트 초기화"
```
Expected: 1 commit, 2 files.

---

## Phase 2 — ggotAIorder 이력보존 편입 (라이브 무중단)

> 기법: order 로컬 repo를 remote로 추가→fetch→`merge -s ours`(이력 연결만)→`read-tree --prefix … (-u 없음)`(인덱스만, 워킹파일 불변)→commit→중첩 `.git` 제거. 워킹트리의 backend 파일이 한 번도 안 바뀌므로 pythonw 가동 유지.

### Task 2.1: order 이력을 ggotAIorder/ 프리픽스로 병합

**Files:** 인덱스 전반(워킹파일 불변)

- [ ] **Step 1: order를 원격으로 추가하고 fetch**

Run:
```bash
cd /c/ggotAI && git remote add order_src /c/ggotAI/ggotAIorder && git fetch order_src
```
Expected: order의 모든 ref/이력이 fetch됨(`* [new branch] master -> order_src/master` 등).

- [ ] **Step 2: 편입 대상 커밋 확정(이 plan/spec 포함 브랜치)**

spec/plan 커밋이 있는 `docs/monorepo-integration-design`를 편입한다(master + 문서 포함).

Run:
```bash
cd /c/ggotAI && git rev-parse order_src/docs/monorepo-integration-design
```
Expected: 커밋 해시 출력(존재 확인).

- [ ] **Step 3: 이력 연결(ours) — 워킹/인덱스 변경 없음**

Run:
```bash
cd /c/ggotAI && git merge -s ours --no-commit --allow-unrelated-histories order_src/docs/monorepo-integration-design
```
Expected: `Automatic merge went well; stopped before committing as requested`.

- [ ] **Step 4: 인덱스에만 프리픽스로 트리 적재(-u 없음 = 워킹파일 불변)**

Run:
```bash
cd /c/ggotAI && git read-tree --prefix=ggotAIorder/ order_src/docs/monorepo-integration-design
```
Expected: 출력 없음(성공). **`--prefix`를 `-u` 없이** 쓰면 인덱스만 갱신하고 워킹트리는 손대지 않는다. 디스크의 `ggotAIorder/` 파일은 그대로(라이브 backend 무중단의 핵심). 디스크 파일이 이 ref의 트리와 bit-identical이어야 커밋 후 clean(= order 워킹카피가 해당 브랜치에서 clean 상태여야 함, Phase 0.1에서 보장).

- [ ] **Step 5: 커밋(이력 보존된 편입)**

Run:
```bash
cd /c/ggotAI && git commit -m "merge: ggotAIorder 편입(이력보존, 경로 불변)"
```
Expected: order 전체 이력이 모노레포 그래프에 연결된 머지 커밋 생성.

- [ ] **Step 6: 중첩 .git 제거 → 일반 추적 파일화**

Run:
```bash
rm -rf /c/ggotAI/ggotAIorder/.git && cd /c/ggotAI && git status -sb | head -20
```
Expected: `ggotAIorder/`가 더 이상 gitlink/중첩이 아니고, 워킹트리가 인덱스와 일치(추적 파일은 clean). `.env`/`.venv` 등 gitignore 항목만 무시됨.

- [ ] **Step 7: 라이브 backend 무중단 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe -c "print('venv ok')"
tasklist 2>/dev/null | grep -i pythonw || echo "pythonw 확인 필요"
```
Expected: `venv ok` 출력, pythonw 프로세스 여전히 살아있음(PID 변화 없음). backend 파일이 안 바뀌었으므로 정상 가동.

- [ ] **Step 8: backend 회귀 테스트**

Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe -m pytest /c/ggotAI/ggotAIorder/backend -q 2>&1 | tail -3
```
Expected: `121 passed, 5 skipped`(Phase 0 baseline과 동일, 회귀0).

---

## Phase 3 — ggotAIhp 이력보존 편입

> hp는 `C:\ggotAIhp`(루트 밖)에 있으므로, **이력은 fetch로 가져오고** 워킹파일은 물리 이동한다. 동일 `read-tree -i` 기법으로 디스크와 인덱스를 맞춘다.

### Task 3.1: hp 워킹카피를 모노레포 안으로 이동

**Files:** `C:\ggotAIhp\*` → `C:\ggotAI\ggotAIhp\*`

- [ ] **Step 1: hp 원격 추가 + fetch (이동 전, 이력 확보)**

Run:
```bash
cd /c/ggotAI && git remote add hp_src /c/ggotAIhp && git fetch hp_src
```
Expected: hp 이력 fetch됨.

- [ ] **Step 2: hp 워킹카피를 ggotAIhp/로 이동(.env/local.properties/build 포함)**

Run (PowerShell):
```powershell
Move-Item "C:\ggotAIhp" "C:\ggotAI\ggotAIhp"
Test-Path "C:\ggotAI\ggotAIhp\android\local.properties"
Test-Path "C:\ggotAI\ggotAIhp\.env"
```
Expected: 두 `Test-Path` 모두 `True`. (Move 실패 시 robocopy /MOVE 사용 후 빈 원본 제거.)

- [ ] **Step 3: 이동된 hp의 중첩 .git 제거**

Run:
```bash
rm -rf /c/ggotAI/ggotAIhp/.git
```
Expected: 출력 없음. (이력은 이미 hp_src로 fetch돼 있음.)

### Task 3.2: hp 이력을 ggotAIhp/ 프리픽스로 병합

**Files:** 인덱스(이동된 워킹파일과 일치시킴)

- [ ] **Step 1: 이력 연결(ours)**

Run:
```bash
cd /c/ggotAI && git merge -s ours --no-commit --allow-unrelated-histories hp_src/master
```
Expected: `stopped before committing as requested`.

- [ ] **Step 2: 인덱스에 프리픽스 트리 적재(-u 없음, 워킹 불변)**

Run:
```bash
cd /c/ggotAI && git read-tree --prefix=ggotAIhp/ hp_src/master
```
Expected: 출력 없음. `-u` 없이 인덱스만 갱신. 디스크의 이동된 `ggotAIhp/` 추적파일이 `hp_src/master` 트리와 일치하므로 커밋 후 clean(gitignore 항목은 무시). hp 워킹카피가 master에서 clean이어야 함(Phase 0.1 Step 3에서 보장).

- [ ] **Step 3: 커밋**

Run:
```bash
cd /c/ggotAI && git commit -m "merge: ggotAIhp 편입(이력보존)"
```
Expected: hp 전체 이력이 그래프에 연결됨.

- [ ] **Step 4: 상태 확인**

Run:
```bash
cd /c/ggotAI && git status -sb | head -20 && git log --oneline --graph -8
```
Expected: 워킹트리 clean(추적파일), 그래프에 order/hp 두 머지 흔적. `ggotAIhp/android/local.properties`·`.env`는 gitignore로 무시됨(추적 안 됨 확인).

- [ ] **Step 5: 원격 remote 정리(임시 소스 제거)**

Run:
```bash
cd /c/ggotAI && git remote remove order_src && git remote remove hp_src
```
Expected: 출력 없음.

---

## Phase 4 — DB 계약 단일화: 마이그레이션

> 라이브 DB엔 이미 전부 적용됨. 통합본은 "신규 환경 재현 + 단일 진실" 기록. order의 날짜-기능 파일을 타임스탬프 컨벤션으로 리네이밍해 hp 마이그레이션과 시간순 병합.

### Task 4.1: 루트 supabase/ 구성 + 마이그레이션 통합

**Files:**
- Create: `supabase/migrations/*.sql` (통합)
- Move-from: `ggotAIhp/supabase/migrations/*`, `ggotAIorder/docs/migrations/*`
- Move-from: `ggotAIorder/supabase/config.toml`

- [ ] **Step 1: 루트 supabase 골격 + config 이동**

Run:
```bash
cd /c/ggotAI && mkdir -p supabase/migrations supabase/functions
git mv ggotAIorder/supabase/config.toml supabase/config.toml
```
Expected: config.toml이 루트 supabase로 이동(스테이징됨).

- [ ] **Step 2: hp 마이그레이션 이동(타임스탬프 컨벤션 유지)**

Run:
```bash
cd /c/ggotAI
git mv ggotAIhp/supabase/migrations/20260518000000_init.sql                  supabase/migrations/20260518000000_init.sql
git mv ggotAIhp/supabase/migrations/20260611000000_server_call_unique_index.sql supabase/migrations/20260611000000_server_call_unique_index.sql
```
Expected: 2개 이동.

- [ ] **Step 3: order 마이그레이션을 타임스탬프 리네이밍하며 이동**

매핑(날짜→`YYYYMMDD000000`, 같은 날 충돌 회피용 분 단위 부여). hp와 시간순 정렬됨.
Run:
```bash
cd /c/ggotAI
git mv ggotAIorder/docs/migrations/2026-06-06-b1-auth.sql          supabase/migrations/20260606000100_b1_auth.sql
git mv ggotAIorder/docs/migrations/2026-06-06-b2a-otp.sql          supabase/migrations/20260606000200_b2a_otp.sql
git mv ggotAIorder/docs/migrations/2026-06-07-b2b-mypage.sql       supabase/migrations/20260607000100_b2b_mypage.sql
git mv ggotAIorder/docs/migrations/2026-06-07-c-dashboard.sql      supabase/migrations/20260607000200_c_dashboard.sql
git mv ggotAIorder/docs/migrations/2026-06-10-d-order-list.sql     supabase/migrations/20260610000100_d_order_list.sql
git mv ggotAIorder/docs/migrations/2026-06-10-e-settings.sql       supabase/migrations/20260610000200_e_settings.sql
git mv ggotAIorder/docs/migrations/2026-06-13-delivery-at-text.sql supabase/migrations/20260613000100_delivery_at_text.sql
git mv ggotAIorder/docs/migrations/2026-06-14-catchup-scan.sql     supabase/migrations/20260614000100_catchup_scan.sql
```
Expected: 8개 이동. (`ggotAIorder/docs/migrations/` 비게 됨.)

- [ ] **Step 4: 정렬·중복 점검**

Run:
```bash
ls /c/ggotAI/supabase/migrations/ | sort
```
Expected: 10개 파일이 타임스탬프 오름차순. init(0518)이 최상단, catchup(0614)이 최하단.

- [ ] **Step 5: 커밋**

Run:
```bash
cd /c/ggotAI && git add -A && git commit -m "refactor(db): 마이그레이션을 루트 supabase/migrations로 단일화(타임스탬프 정렬)"
```
Expected: rename 10 + config 이동.

### Task 4.2: 통합 마이그레이션이 라이브 스키마와 일치하는지 검증

**Files:** 없음(검증)

- [ ] **Step 1: supabase CLI로 db diff (라이브 대상)**

> 사장님 작업 가능성: `supabase login` + 프로젝트 link 필요. CLI 미설치 시 npx 사용.

Run:
```bash
cd /c/ggotAI && supabase db diff --linked 2>&1 | tail -20
```
Expected: **빈 diff**(통합 마이그레이션 = 라이브 스키마). 차이가 나오면 누락 마이그레이션 보정 후 재커밋.

---

## Phase 5 — DB 계약 단일화: 엣지함수

### Task 5.1: 엣지함수 5개를 루트 supabase/functions로 통합

**Files:**
- Move: order `supabase/functions/{send-otp,_shared}`, hp `supabase/functions/{delete-call,get-settings,upload-call,verify-device}`

- [ ] **Step 1: order 함수 이동**

Run:
```bash
cd /c/ggotAI
git mv ggotAIorder/supabase/functions/send-otp supabase/functions/send-otp
git mv ggotAIorder/supabase/functions/_shared  supabase/functions/_shared
```
Expected: 2개 이동.

- [ ] **Step 2: hp 함수 이동**

Run:
```bash
cd /c/ggotAI
git mv ggotAIhp/supabase/functions/delete-call    supabase/functions/delete-call
git mv ggotAIhp/supabase/functions/get-settings   supabase/functions/get-settings
git mv ggotAIhp/supabase/functions/upload-call    supabase/functions/upload-call
git mv ggotAIhp/supabase/functions/verify-device  supabase/functions/verify-device
```
Expected: 4개 이동.

- [ ] **Step 3: 빈 하위 supabase 잔재 제거**

Run:
```bash
cd /c/ggotAI && find ggotAIorder/supabase ggotAIhp/supabase -type d 2>/dev/null; rmdir -p ggotAIorder/supabase/functions ggotAIhp/supabase/migrations ggotAIhp/supabase/functions 2>/dev/null; echo done
```
Expected: `done`. 하위 supabase 디렉터리가 비어 사라짐(git은 빈 디렉터리 추적 안 함).

- [ ] **Step 4: 함수 import 경로 점검(_shared 상대경로)**

Run:
```bash
grep -rn "_shared" /c/ggotAI/supabase/functions/ 2>/dev/null
```
Expected: send-otp가 `../_shared/cors.ts`를 참조하면 경로 유지됨(같은 상대구조). 깨진 참조 없으면 통과.

- [ ] **Step 5: 커밋**

Run:
```bash
cd /c/ggotAI && git add -A && git commit -m "refactor(db): 엣지함수 5종을 루트 supabase/functions로 통합"
```
Expected: 함수 트리 이동 커밋.

---

## Phase 6 — 타입 생성 (ya 자동 감지)

### Task 6.1: DB 타입 생성을 frontend로 배선

**Files:**
- Modify: `ggotAIorder/frontend/package.json` (scripts에 `gen:types`)
- Create/Update: `ggotAIorder/frontend/src/types/database.ts`

- [ ] **Step 1: package.json에 타입생성 스크립트 추가**

`scripts`에 추가(프로젝트 ref는 실제 값으로):
```json
"gen:types": "supabase gen types typescript --linked > src/types/database.ts"
```

- [ ] **Step 2: 타입 생성 실행**

Run:
```bash
cd /c/ggotAI/ggotAIorder/frontend && npm run gen:types && head -5 src/types/database.ts
```
Expected: `src/types/database.ts`에 `export type Database = {...}` 형태 생성. `server_call_history`/`order_details`/`setting_info`/`member_info` 테이블 타입 포함.

- [ ] **Step 3: frontend 빌드로 타입 정합 확인**

Run:
```bash
cd /c/ggotAI/ggotAIorder/frontend && npm run build 2>&1 | tail -8
```
Expected: 빌드 성공(생성 타입과 기존 코드 충돌 없음). 충돌 시 해당 컴포넌트의 타입 import를 생성타입으로 정렬.

- [ ] **Step 4: vitest 회귀**

Run:
```bash
cd /c/ggotAI/ggotAIorder/frontend && npx vitest run 2>&1 | tail -5
```
Expected: 기존 vitest 스위트 전부 통과(회귀0).

- [ ] **Step 5: 커밋**

Run:
```bash
cd /c/ggotAI && git add ggotAIorder/frontend/package.json ggotAIorder/frontend/src/types/database.ts && git commit -m "feat(types): Supabase 생성 타입 배선(frontend gen:types)"
```

---

## Phase 7 — 계약 테스트 (드리프트 차단)

> backend는 이미 스키마 계약 테스트가 있다(`test_phase4_schema_contract.py`). "타입이 최신인지"를 강제하는 **types-in-sync 가드 테스트**를 frontend에 추가해, 스키마 변경 후 타입 재생성을 빠뜨리면 실패하게 한다.

### Task 7.1: frontend types-in-sync 가드 (TDD)

**Files:**
- Create: `ggotAIorder/frontend/src/types/__tests__/database-in-sync.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

생성 타입에 핵심 테이블이 존재함을 단언(스키마↔타입 최소 계약). 컬럼 변경 후 타입 미갱신 시 키 부재로 실패.
```ts
import { describe, it, expect } from "vitest";
import type { Database } from "../database";

describe("database types in sync", () => {
  it("핵심 테이블 타입이 생성되어 있다", () => {
    type Tables = Database["public"]["Tables"];
    const required: (keyof Tables)[] = [
      "server_call_history",
      "order_details",
      "member_info",
      "setting_info",
    ];
    // 타입 수준 단언: 누락 시 컴파일 에러. 런타임 가드도 둔다.
    expect(required.length).toBe(4);
  });

  it("server_call_history에 shop_key·processed_at 컬럼 타입이 있다", () => {
    type Row = Database["public"]["Tables"]["server_call_history"]["Row"];
    const probe: Pick<Row, "shop_key" | "processed_at"> = {
      shop_key: 19,
      processed_at: null,
    };
    expect(probe.shop_key).toBe(19);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인(타입 미생성/컬럼 부재 시)**

Run:
```bash
cd /c/ggotAI/ggotAIorder/frontend && npx vitest run src/types/__tests__/database-in-sync.test.ts 2>&1 | tail -15
```
Expected: 만약 Phase 6 타입이 정상 생성됐다면 PASS가 나올 수 있다. 그 경우 **일부러 database.ts에서 `shop_key` 줄을 임시 삭제** → 재실행 시 컴파일/런타임 FAIL 확인 → 되돌리기. (테스트가 실제로 드리프트를 잡는지 검증.)

- [ ] **Step 3: 타입 원복 후 통과 확인**

Run:
```bash
cd /c/ggotAI/ggotAIorder/frontend && npm run gen:types && npx vitest run src/types/__tests__/database-in-sync.test.ts 2>&1 | tail -5
```
Expected: PASS.

- [ ] **Step 4: 커밋**

Run:
```bash
cd /c/ggotAI && git add ggotAIorder/frontend/src/types/__tests__/database-in-sync.test.ts && git commit -m "test(types): DB 타입 in-sync 가드 추가(드리프트 차단)"
```

---

## Phase 8 — 통합 CI

### Task 8.1: GitHub Actions 통합 워크플로

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: CI 워크플로 작성**

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [master]

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ggotAIorder/backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -e .[dev] || pip install -r requirements.txt
      - run: python -m pytest -q

  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ggotAIorder/frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm", cache-dependency-path: ggotAIorder/frontend/package-lock.json }
      - run: npm ci
      - run: npx vitest run
      - run: npm run build

  android:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ggotAIhp/android } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: "temurin", java-version: "17" }
      - run: chmod +x ./gradlew && ./gradlew assembleDebug --no-daemon
```

> backend 설치 명령은 실제 매니페스트에 맞춰 1개로 확정(아래 Step 2에서 확인 후 수정).

- [ ] **Step 2: backend 설치 방식 확인 후 ci.yml 보정**

Run:
```bash
ls /c/ggotAI/ggotAIorder/backend/pyproject.toml /c/ggotAI/ggotAIorder/backend/requirements.txt 2>/dev/null
```
Expected: 존재하는 파일에 맞춰 backend job의 install 스텝을 단일 명령으로 확정(`pyproject.toml`이면 `pip install -e .` + dev extras 확인).

- [ ] **Step 3: 워크플로 YAML 문법 검증**

Run:
```bash
python -c "import yaml,sys; yaml.safe_load(open('/c/ggotAI/.github/workflows/ci.yml')); print('yaml ok')"
```
Expected: `yaml ok`.

- [ ] **Step 4: 커밋**

Run:
```bash
cd /c/ggotAI && git add .github/workflows/ci.yml && git commit -m "ci: backend·frontend·android 통합 워크플로"
```

---

## Phase 9 — 원격 게시 + 라이브 재검증

### Task 9.1: 모노레포 원격 연결 및 푸시

**Files:** 없음

- [ ] **Step 1: 모노레포 원격 결정·연결**

`ggotAI`(hp 기존 리모트) 재사용은 hp 단독 루트 이력과 충돌 → **신규 빈 repo 권장**(예: `KoreaVictor/ggotAI-mono`). 사장님이 GitHub에서 빈 repo 생성 후:
Run:
```bash
cd /c/ggotAI && git remote add origin https://github.com/KoreaVictor/ggotAI-mono.git
```

- [ ] **Step 2: 푸시**

Run:
```bash
cd /c/ggotAI && git push -u origin master 2>&1 | tail -5
```
Expected: 전체 이력(order+hp 보존) 업로드.

### Task 9.2: 라이브 무인기동 재검증

**Files:** 없음

- [ ] **Step 1: backend 최종 회귀**

Run:
```bash
PYTHONIOENCODING=utf-8 /c/ggotAI/ggotAIorder/backend/.venv/Scripts/python.exe -m pytest /c/ggotAI/ggotAIorder/backend -q 2>&1 | tail -3
```
Expected: `121 passed, 5 skipped`.

- [ ] **Step 2: 작업 스케줄러 경로 무변경 확인**

Run (PowerShell):
```powershell
(Get-ScheduledTask ggotAIorder).Actions | Select-Object Execute, Arguments
```
Expected: Arguments에 `C:\ggotAI\ggotAIorder\backend\run_dev.py`(경로 불변) → 재배선 불필요.

- [ ] **Step 3: 작업 1회 재기동 후 catch-up 로그 정상 확인**

Run (PowerShell, 관리자 필요 — 사장님 작업):
```powershell
Restart-ScheduledTask -TaskName ggotAIorder   # 또는 Stop/Start
```
그 후:
```bash
tail -20 /c/ggotAI/ggotAIorder/backend/logs/ggotaiorder.log
```
Expected: `오케스트레이터 시작` + `Realtime 구독 시작: server_call_history INSERT (shop_key=19)` + catch-up 정상. (shop_key 필터 로그까지 확인되면 직전 PR #22도 라이브 반영됨.)

- [ ] **Step 4: 합성 통화 E2E(선택, 기존 검증법 재사용)**

미처리 핸드폰 행 INSERT → `order_details` 자동 생성 폴링 → 흔적 정리. (메모리 `ggotaiya-phone-pipeline-bringup`의 검증 절차 재사용.)
Expected: 자동 주문 생성 확인 후 자식→부모 순 삭제로 흔적 0.

---

## 정리 / 사후

- [ ] 구 `C:\ggotAIhp`는 이동됨(없음). 백업 `C:\ggotAI_backup_2026-06-14`는 1주 보관 후 삭제.
- [ ] 기존 `ggotAIorder`·`ggotAI`(hp) 원격은 읽기전용/아카이브 표기. 신규 작업은 모노레포로.
- [ ] 메모리 갱신: 모노레포 전환 완료, 새 원격/경로, DB 단일출처 위치(`supabase/`), 타입생성·CI 흐름.
- [ ] Android Studio에서 `C:\ggotAI\ggotAIhp\android` 재오픈(`local.properties` 유지됨).

## 위험 / 주의

- **되돌리기 까다로움**: Phase 1~3은 git 그래프를 바꾼다. 문제 시 `C:\ggotAI\.git` 삭제 + 백업 복원 + 두 원격에서 워킹카피 재clone으로 원복.
- **gitignore 파일 보존**: `.env`·`.venv`·`node_modules`·`local.properties`는 이력에 없으므로 **이동/유지로만** 보존됨. Phase 0 백업이 최후 안전망.
- **admin 필요 단계**: 작업 스케줄러 재기동(Phase 9.2 Step 3)은 관리자 권한 → 사장님 실행.
- **Supabase CLI 로그인/link**: Phase 4.2·6은 `supabase login`+프로젝트 link 필요(MCP는 현재 Unauthorized). 미설정 시 사장님 1회 설정.
- **read-tree `--prefix`는 반드시 `-u` 없이**: Phase 2/3에서 `git read-tree --prefix=…`를 `-u` 없이 써야 인덱스만 갱신되고 워킹파일이 안 바뀌어 라이브 무중단이 성립. `-u`를 붙이면 이미 디스크에 존재하는 파일과 충돌("would be overwritten")하거나 backend 파일을 덮어써 흔들릴 수 있음. (`-i`는 `-m` 머지용 플래그라 여기선 쓰지 않음.) 전제: 해당 워킹카피가 그 ref에서 clean이어야 커밋 후 상태가 깨끗함.
