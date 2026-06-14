# Phase 4 수동 검증 체크리스트 (T2: IPC→서비스정지→트레이)

서비스명: `ggotAIorder` (백엔드 `service.py` `_svc_name_` ↔ 프론트 `net start/stop ggotAIorder` 일치 필수)

## 0. 사전 정합 확인
- [ ] `backend/src/ggotaiorder/service.py` 의 `_svc_name_ == "ggotAIorder"`
- [ ] 프론트 `frontend/src/main/index.ts` 의 `net start/stop` 대상명이 `ggotAIorder`

## 1. 사전 준비(비-GUI, 보조 가능)
- [ ] 백엔드 의존성: `cd backend && ./.venv/Scripts/python.exe -m pip install -e .[test]`
- [ ] 서비스 설치(관리자 PowerShell): `./.venv/Scripts/python.exe -m ggotaiorder.service install`
- [ ] 등록 확인: `sc query ggotAIorder` → 서비스 존재
- [ ] 프론트 빌드/실행: `cd frontend && npm install && npm run dev` (또는 `npm run build` 후 패키지 실행)

## 2. 검증 절차
| # | 동작 | 명령/조작 | 기대 관측 | 실패 시 진단 |
|---|---|---|---|---|
| 1 | 서비스 시작 | `net start ggotAIorder` (관리자) | `sc query` = RUNNING, 트레이 🟢 | 이벤트뷰어/로그, .env 검증 |
| 2 | 앱 표시 | Electron 앱 실행 | 대시보드 렌더, 채널 상태 위젯 | 콘솔 에러, VITE_ env |
| 3 | 수집 중지 | UI [수집 중지] 클릭 | IPC→`net stop ggotAIorder` 실행 | preload IPC 채널/권한 |
| 4 | 정지 확인 | `sc query ggotAIorder` | STATE = STOPPED | 서비스 stop 핸들러 로그 |
| 5 | 트레이 색 | 트레이 아이콘 육안 | 🔴 (정지색) | tray 상태 연동 로직 |
| 6 | 역검증 | UI [시작] 클릭 | RUNNING + 🟢 | net start 권한(UAC) |

## 3. 결과 기록
- 검증일/검증자:
- 단계별 결과(통과/실패/비고):
- 캡처(트레이 🔴/🟢):
