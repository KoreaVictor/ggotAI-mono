# ggotAIorder 백엔드

다중 채널 주문 수집·AI 정형화·자동입력(RPA) Windows 백그라운드 서비스.

## 개발 환경 설정

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
backend\.venv\Scripts\python.exe -m pip install -e backend
```

후속 세션에서 필요 시:
```powershell
backend\.venv\Scripts\python.exe -m playwright install chromium
backend\.venv\Scripts\python.exe backend\.venv\Scripts\pywin32_postinstall.py -install
```

## 로컬 디버그 실행 (서비스 미등록)

```powershell
backend\.venv\Scripts\python.exe backend\run_dev.py
```
FastAPI: http://127.0.0.1:8765/health

## Windows 서비스 등록 (관리자 권한)

```powershell
backend\.venv\Scripts\python.exe -m ggotaiorder.service install
net start ggotAIorder
net stop ggotAIorder
```

## 테스트

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

## 구조

- `config` / `logging_setup` / `core/crypto` / `core/supabase_client` — 핵심 코어(실로직)
- `orchestrator` — 단일 asyncio 루프, 서브시스템 배선, 수집 on/off
- `service` / `tray` — Windows 서비스·트레이
- `api` / `realtime` / `pipeline` / `scraper` / `rpa` / `notifier` — 도메인 모듈(스텁, 후속 구현)
