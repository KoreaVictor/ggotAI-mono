# ggotAIorder 백엔드 골격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ggotAIorder 백엔드(Windows Service)의 전체 골격을 구성한다 — 핵심 코어(config/logging/crypto/supabase)는 실로직으로, 6개 도메인 모듈(api/realtime/pipeline/scraper/rpa/notifier)은 계약이 고정된 스텁으로, 오케스트레이터·service·tray로 배선한다.

**Architecture:** 단일 asyncio 이벤트 루프 오케스트레이터. pywin32 Windows Service가 워커 스레드에서 오케스트레이터 루프를 start/stop 한다. FastAPI(uvicorn)·Supabase Realtime·APScheduler·싱글턴 RPA(`asyncio.Lock`)가 한 이벤트 루프를 공유한다. 6개 도메인 모듈은 타입힌트·docstring으로 계약을 고정하고 본문은 안전한 no-op + 로그.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, supabase-py, python-dotenv, cryptography, APScheduler, faster-whisper, google-generativeai, Playwright, pywin32, pystray, Pillow, openpyxl, pyperclip/pygetwindow, pytest.

설계서: `docs/superpowers/specs/2026-06-02-backend-skeleton-design.md`

---

## File Structure

| 파일 | 책임 | 유형 |
| --- | --- | --- |
| `backend/pyproject.toml` | 패키지 메타·editable 설치 설정 | 신규 |
| `backend/requirements.txt` | 의존성 목록 | 신규 |
| `backend/README.md` | 서비스 등록/실행 가이드 | 신규 |
| `backend/run_dev.py` | 서비스 없이 로컬 디버그 실행 진입점 | 신규 |
| `backend/src/ggotaiorder/__init__.py` | 패키지 루트, 버전 | 신규 |
| `backend/src/ggotaiorder/config.py` | .env 로딩·필수 키 검증 | 실로직 |
| `backend/src/ggotaiorder/logging_setup.py` | 콘솔+회전파일 로깅 | 실로직 |
| `backend/src/ggotaiorder/core/crypto.py` | AES-256-CBC 복호화(crypto-js 호환) | 실로직 |
| `backend/src/ggotaiorder/core/supabase_client.py` | supabase-py 싱글턴 클라이언트 | 실로직 |
| `backend/src/ggotaiorder/orchestrator.py` | asyncio 루프·서브시스템 배선·수집 on/off | 실로직 |
| `backend/src/ggotaiorder/service.py` | pywin32 Windows Service 래퍼 | 실로직 |
| `backend/src/ggotaiorder/tray.py` | pystray 트레이 아이콘/메뉴 | 실로직 |
| `backend/src/ggotaiorder/api/routes.py` | FastAPI 게이트폰 Webhook | 스텁 |
| `backend/src/ggotaiorder/realtime/listener.py` | Realtime INSERT 구독 | 스텁 |
| `backend/src/ggotaiorder/pipeline/engine.py` | STT+Gemini 정형화 | 스텁 |
| `backend/src/ggotaiorder/scraper/crawler.py` | Playwright 인트라넷 크롤러 | 스텁 |
| `backend/src/ggotaiorder/rpa/singleton_macro.py` | 싱글턴 RPA + 백업 | 스텁 |
| `backend/src/ggotaiorder/notifier/sms_sender.py` | 알림톡/문자 발송 | 스텁 |
| `backend/tests/test_crypto.py` | AES 복호화 검증 | 테스트 |
| `backend/tests/test_config.py` | config 로딩 검증 | 테스트 |
| `backend/tests/test_smoke.py` | 전체 모듈 import·계약 스모크 | 테스트 |

모든 명령은 `C:\ggotAI\ggotAIorder` (저장소 루트)에서 실행한다. venv는 `backend/.venv`.

---

### Task 1: 가상환경·의존성·패키지 골격

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `backend/src/ggotaiorder/__init__.py`
- Create: `backend/src/ggotaiorder/core/__init__.py`
- Create: `backend/src/ggotaiorder/api/__init__.py`
- Create: `backend/src/ggotaiorder/realtime/__init__.py`
- Create: `backend/src/ggotaiorder/pipeline/__init__.py`
- Create: `backend/src/ggotaiorder/scraper/__init__.py`
- Create: `backend/src/ggotaiorder/rpa/__init__.py`
- Create: `backend/src/ggotaiorder/notifier/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: requirements.txt 작성**

`backend/requirements.txt`:
```text
# --- Web / API ---
fastapi
uvicorn[standard]
python-multipart

# --- Supabase / DB ---
supabase

# --- 환경설정 / 보안 ---
python-dotenv
cryptography

# --- 스케줄러 ---
APScheduler

# --- AI 파이프라인 ---
faster-whisper
google-generativeai

# --- 웹 자동화 ---
playwright

# --- Windows 서비스 / 트레이 ---
pywin32; sys_platform == "win32"
pystray
Pillow

# --- RPA / 백업 ---
pyperclip
pygetwindow
openpyxl

# --- HTTP (알림 API) ---
httpx

# --- 개발/테스트 ---
pytest
```

- [ ] **Step 2: pyproject.toml 작성 (src-layout editable 설치용)**

`backend/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ggotaiorder"
version = "0.1.0"
description = "ggotAIorder 백엔드 Windows Service 엔진"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 패키지 `__init__.py` 파일 생성**

`backend/src/ggotaiorder/__init__.py`:
```python
"""ggotAIorder 백엔드 Windows Service 엔진."""

__version__ = "0.1.0"
```

나머지 `__init__.py` 7개(`core`, `api`, `realtime`, `pipeline`, `scraper`, `rpa`, `notifier`)와 `tests/__init__.py`는 빈 파일로 생성:
```python
```

- [ ] **Step 4: venv 생성 및 의존성 설치**

Run:
```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
backend\.venv\Scripts\python.exe -m pip install -e backend
```
Expected: 모든 패키지 설치 성공. faster-whisper(ctranslate2)·playwright 설치에 수 분 소요될 수 있음. `pip install -e backend`로 `ggotaiorder` 패키지가 editable 설치됨.

참고: Playwright 브라우저 바이너리(`playwright install chromium`)와 pywin32 post-install은 이번 골격에서 실행하지 않는다(후속 세션). 설치 중 일부 패키지가 빌드 도구를 요구하면 로그를 확인하고 보고한다.

- [ ] **Step 5: 설치 검증**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "import ggotaiorder; print(ggotaiorder.__version__)"
```
Expected: `0.1.0` 출력.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/pyproject.toml backend/src/ggotaiorder/__init__.py backend/src/ggotaiorder/core/__init__.py backend/src/ggotaiorder/api/__init__.py backend/src/ggotaiorder/realtime/__init__.py backend/src/ggotaiorder/pipeline/__init__.py backend/src/ggotaiorder/scraper/__init__.py backend/src/ggotaiorder/rpa/__init__.py backend/src/ggotaiorder/notifier/__init__.py backend/tests/__init__.py
git commit -m "chore: 백엔드 패키지 골격 및 의존성 구성"
```

---

### Task 2: config.py — .env 로딩·검증 (TDD)

**Files:**
- Create: `backend/src/ggotaiorder/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_config.py`:
```python
import pytest

from ggotaiorder.config import Config, load_config, ConfigError

VALID = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
    "AES_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef",  # 32 bytes
}


def test_load_config_returns_values():
    cfg = load_config(env=VALID)
    assert isinstance(cfg, Config)
    assert cfg.supabase_url == "https://example.supabase.co"
    assert cfg.supabase_service_role_key == "service-key"
    assert cfg.aes_encryption_key == VALID["AES_ENCRYPTION_KEY"]


def test_missing_key_raises():
    broken = dict(VALID)
    del broken["SUPABASE_URL"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_empty_key_raises():
    broken = dict(VALID, SUPABASE_ANON_KEY="")
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_aes_key_must_be_32_bytes():
    broken = dict(VALID, AES_ENCRYPTION_KEY="too-short")
    with pytest.raises(ConfigError):
        load_config(env=broken)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError` 또는 `ImportError: cannot import name 'Config'`.

- [ ] **Step 3: 최소 구현 작성**

`backend/src/ggotaiorder/config.py`:
```python
"""환경설정(.env) 로딩 및 검증."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

_REQUIRED_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AES_ENCRYPTION_KEY",
)


class ConfigError(RuntimeError):
    """필수 환경설정 누락/오류."""


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    aes_encryption_key: str


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """환경설정을 로딩해 검증된 Config를 반환한다.

    env가 None이면 backend/.env를 os.environ에 로딩한 뒤 os.environ을 사용한다.
    필수 키 누락/공백 또는 AES 키가 32바이트가 아니면 ConfigError.
    """
    if env is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(env_path)
        env = os.environ

    missing = [k for k in _REQUIRED_KEYS if not env.get(k)]
    if missing:
        raise ConfigError(f"필수 환경변수 누락/공백: {', '.join(missing)}")

    aes_key = env["AES_ENCRYPTION_KEY"]
    if len(aes_key.encode("utf-8")) != 32:
        raise ConfigError("AES_ENCRYPTION_KEY 는 UTF-8 기준 정확히 32바이트여야 합니다.")

    return Config(
        supabase_url=env["SUPABASE_URL"],
        supabase_anon_key=env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=env["SUPABASE_SERVICE_ROLE_KEY"],
        aes_encryption_key=aes_key,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_config.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/config.py backend/tests/test_config.py
git commit -m "feat: config 로딩·검증 모듈 추가"
```

---

### Task 3: logging_setup.py — 로깅 구성

**Files:**
- Create: `backend/src/ggotaiorder/logging_setup.py`

- [ ] **Step 1: 구현 작성**

`backend/src/ggotaiorder/logging_setup.py`:
```python
"""콘솔 + 회전 파일 로깅 구성."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """루트 로거에 콘솔 + 회전 파일 핸들러를 1회 구성한다."""
    root = logging.getLogger()
    if root.handlers:  # 중복 구성 방지
        return
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_DIR / "ggotaiorder.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
```

- [ ] **Step 2: 동작 확인**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.logging_setup import setup_logging; import logging; setup_logging(); logging.getLogger('check').info('logging ok')"
```
Expected: 콘솔에 `... | INFO    | check | logging ok` 출력, `backend/logs/ggotaiorder.log` 생성.

- [ ] **Step 3: Commit**

```bash
git add backend/src/ggotaiorder/logging_setup.py
git commit -m "feat: 로깅 구성 모듈 추가"
```

---

### Task 4: core/crypto.py — AES-256-CBC 복호화 (TDD, crypto-js 호환)

**Files:**
- Create: `backend/src/ggotaiorder/core/crypto.py`
- Test: `backend/tests/test_crypto.py`

DB 저장 포맷: `iv_hex(32 hex chars) + ":" + ciphertext_base64`. 알고리즘 `AES-256-CBC`, 패딩 `PKCS7(128)`, 키는 UTF-8 32바이트. 아래 고정 벡터는 cryptography 라이브러리(= crypto-js와 동일 알고리즘)로 실제 생성·검증한 값이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_crypto.py`:
```python
from ggotaiorder.core.crypto import decrypt, encrypt

# cryptography(AES-256-CBC/PKCS7)로 실제 생성·검증한 고정 벡터.
# crypto-js가 동일 key/iv/plaintext로 만드는 결과와 바이트 단위로 동일하다.
KEY = "0123456789abcdef0123456789abcdef"      # 32 bytes -> AES-256
IV_HEX = "00112233445566778899aabbccddeeff"
PLAIN = "flower_pw_123!"
DB_VALUE = "00112233445566778899aabbccddeeff:trOEJkzSStKQyv6HIunOxw=="


def test_decrypt_known_vector():
    assert decrypt(DB_VALUE, KEY) == PLAIN


def test_encrypt_with_fixed_iv_matches_vector():
    iv = bytes.fromhex(IV_HEX)
    assert encrypt(PLAIN, KEY, iv=iv) == DB_VALUE


def test_round_trip_random_iv():
    blob = encrypt("배달장소 서울시 강남구", KEY)
    assert decrypt(blob, KEY) == "배달장소 서울시 강남구"
    # 랜덤 IV 이므로 매 호출 결과가 달라야 한다
    assert encrypt("x", KEY) != encrypt("x", KEY)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_crypto.py -v`
Expected: FAIL — `ImportError: cannot import name 'decrypt'`.

- [ ] **Step 3: 최소 구현 작성**

`backend/src/ggotaiorder/core/crypto.py`:
```python
"""AES-256-CBC 대칭키 복호화 (프론트엔드 crypto-js 호환).

DB 저장 포맷: ``iv_hex:ciphertext_base64``
- 알고리즘: AES-256-CBC
- 패딩: PKCS7(128)
- 키: UTF-8 32바이트 문자열 (AES_ENCRYPTION_KEY)
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _key_bytes(key: str) -> bytes:
    raw = key.encode("utf-8")
    if len(raw) != 32:
        raise ValueError("AES 키는 UTF-8 기준 정확히 32바이트여야 합니다.")
    return raw


def decrypt(db_value: str, key: str) -> str:
    """``iv_hex:ciphertext_base64`` 형식을 복호화해 평문을 반환한다."""
    iv_hex, ct_b64 = db_value.split(":", 1)
    iv = bytes.fromhex(iv_hex)
    ciphertext = base64.b64decode(ct_b64)

    decryptor = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return plain.decode("utf-8")


def encrypt(plaintext: str, key: str, iv: bytes | None = None) -> str:
    """평문을 ``iv_hex:ciphertext_base64`` 형식으로 암호화한다.

    iv 미지정 시 16바이트 랜덤 IV를 생성한다. (검증/테스트 및 백엔드 측
    설정 저장에 사용; 프론트엔드는 crypto-js로 동일 포맷을 생성한다.)
    """
    if iv is None:
        iv = os.urandom(16)
    if len(iv) != 16:
        raise ValueError("IV 는 정확히 16바이트여야 합니다.")

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    encryptor = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return iv.hex() + ":" + base64.b64encode(ciphertext).decode("ascii")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_crypto.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/core/crypto.py backend/tests/test_crypto.py
git commit -m "feat: AES-256-CBC 복호화 모듈 추가 (crypto-js 호환)"
```

---

### Task 5: core/supabase_client.py — 싱글턴 클라이언트

**Files:**
- Create: `backend/src/ggotaiorder/core/supabase_client.py`

- [ ] **Step 1: 구현 작성**

`backend/src/ggotaiorder/core/supabase_client.py`:
```python
"""supabase-py 클라이언트 (프로세스 내 싱글턴).

서비스 롤 키를 사용한다(백엔드 전용). create_client 자체는 네트워크를
발생시키지 않으며, 실제 쿼리 시점에 연결된다.
"""

from __future__ import annotations

from supabase import Client, create_client

from ggotaiorder.config import Config, load_config

_client: Client | None = None


def get_client(cfg: Config | None = None) -> Client:
    """싱글턴 Supabase 클라이언트를 반환한다."""
    global _client
    if _client is None:
        cfg = cfg or load_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    return _client


def reset_client() -> None:
    """테스트 격리를 위해 싱글턴을 초기화한다."""
    global _client
    _client = None
```

- [ ] **Step 2: 동작 확인 (.env 로딩 + 싱글턴)**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.core.supabase_client import get_client; c1=get_client(); c2=get_client(); print('singleton', c1 is c2)"
```
Expected: `singleton True` 출력 (네트워크 호출 없음). `.env`의 키 형식이 잘못되면 에러가 나며, 그 경우 보고한다.

- [ ] **Step 3: Commit**

```bash
git add backend/src/ggotaiorder/core/supabase_client.py
git commit -m "feat: Supabase 싱글턴 클라이언트 추가"
```

---

### Task 6: 6개 도메인 모듈 스텁 (계약 고정)

각 모듈은 타입힌트·docstring으로 계약을 고정하고, 본문은 경고 로그 + 안전한 no-op으로 둔다. 오케스트레이터(Task 7)가 이 진입점들을 실제로 호출한다.

**Files:**
- Create: `backend/src/ggotaiorder/api/routes.py`
- Create: `backend/src/ggotaiorder/realtime/listener.py`
- Create: `backend/src/ggotaiorder/pipeline/engine.py`
- Create: `backend/src/ggotaiorder/scraper/crawler.py`
- Create: `backend/src/ggotaiorder/rpa/singleton_macro.py`
- Create: `backend/src/ggotaiorder/notifier/sms_sender.py`

- [ ] **Step 1: api/routes.py (FastAPI 게이트폰 Webhook 스텁)**

`backend/src/ggotaiorder/api/routes.py`:
```python
"""가게전화 VoIP Webhook 수신 API (스텁).

PRD 6-1: POST /api/v1/gate-phone/upload 로 통화 종료 웹훅(Multipart)을 수신.
수신 → 음성파일 Storage 임시적재 → server_call_history INSERT(channel_order='가게전화')
→ pipeline.process(call_history_id) 비동기 호출.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Form, UploadFile

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록해 반환한다."""
    app = FastAPI(title="ggotAIorder", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/gate-phone/upload")
    async def gate_phone_upload(
        file: UploadFile,
        caller_number: str = Form(...),
        call_duration: int = Form(...),
        user_phone_number: str = Form(...),
    ) -> dict[str, str]:
        """[스텁] 통화 종료 웹훅 수신 진입점.

        TODO(후속): Storage 적재 → server_call_history INSERT
        → pipeline.process(call_history_id) 호출.
        """
        logger.warning(
            "[STUB] gate-phone upload 수신: caller=%s duration=%s file=%s",
            caller_number, call_duration, file.filename,
        )
        return {"status": "accepted"}

    return app
```

- [ ] **Step 2: realtime/listener.py (Realtime 구독 스텁)**

`backend/src/ggotaiorder/realtime/listener.py`:
```python
"""Supabase Realtime 감시 (스텁).

PRD 6-2: public.server_call_history 의 INSERT 이벤트를 24시간 구독하여
신규 행 발생 시 pipeline.process(call_history_id) 를 호출한다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RealtimeListener:
    """server_call_history INSERT 구독 리스너."""

    async def start(self) -> None:
        """[스텁] Realtime 채널 구독을 시작한다.

        TODO(후속): supabase.channel(...).on_postgres_changes(INSERT,
        table='server_call_history', callback=self._on_new_call) 구독.
        """
        logger.warning("[STUB] RealtimeListener.start() — 구독 미구현")

    async def stop(self) -> None:
        """[스텁] 구독을 해제한다."""
        logger.warning("[STUB] RealtimeListener.stop()")

    async def _on_new_call(self, payload: dict) -> None:
        """[스텁] 신규 행 콜백. payload에서 id를 추출해 파이프라인 호출.

        TODO(후속): call_history_id = payload['new']['id'];
        await pipeline.process(call_history_id)
        """
        logger.warning("[STUB] on_new_call_received: %s", payload)
```

- [ ] **Step 3: pipeline/engine.py (STT+Gemini 스텁)**

`backend/src/ggotaiorder/pipeline/engine.py`:
```python
"""AI 데이터 정형화 파이프라인 (스텁).

PRD 6-4: STT(faster-whisper)로 stt_text 생성 → Gemini로 11필드 JSON 추출
→ 공백 항목 3개 이상이면 is_order='N' + 음성파일 강제삭제
→ is_order='Y' 이면 order_details INSERT(rpa_status='ready') 후 rpa.enqueue 호출.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Gemini가 추출할 11개 표준 주문서 필드
ORDER_FIELDS = (
    "customer_name",
    "customer_phone_number",
    "product_name",
    "quantity",
    "price",
    "delivery_at",
    "delivery_place",
    "receiver_name",
    "receiver_phone_number",
    "ribbon_congratulations",
    "card_message",
)


async def process(call_history_id: int) -> None:
    """[스텁] 단일 수집 건을 STT→Gemini 정형화 처리한다.

    TODO(후속):
      1. server_call_history 조회 → audio_file_name 확보
      2. faster-whisper STT → stt_text UPDATE
      3. Gemini 11필드 JSON 추출
      4. 공백 >= 3 → is_order='N', 음성파일 삭제, 종료
      5. is_order='Y' → order_details INSERT(rpa_status='ready')
      6. await rpa.enqueue(order_detail_id)
    """
    logger.warning("[STUB] pipeline.process(call_history_id=%s)", call_history_id)
```

- [ ] **Step 4: scraper/crawler.py (Playwright 크롤러 스텁)**

`backend/src/ggotaiorder/scraper/crawler.py`:
```python
"""인트라넷 정기 폴링 크롤러 (스텁).

PRD 6-3: APScheduler 주기로 Playwright Headless 로그인 → 신규 주문 목록 폴링
→ 중복 검증 → server_call_history INSERT(stt_text=원문,
audio_file_name='INTRANET_CRAWLED') → AI 패스 → order_details INSERT(ready)
→ rpa.enqueue. 연속 3회 실패 시 비상 알림.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

INTRANET_AUDIO_MARKER = "INTRANET_CRAWLED"


async def poll_once() -> None:
    """[스텁] 인트라넷을 1회 폴링한다 (APScheduler가 주기 호출).

    TODO(후속):
      1. setting_info 에서 intranet_url/id/password(복호화) 로딩
      2. Playwright 로그인 세션 획득
      3. 신규 주문번호 추출 → DB 교차검증(중복 제거)
      4. 신규 건 상세 스크래핑(11필드)
      5. server_call_history + order_details(ready) INSERT
      6. await rpa.enqueue(order_detail_id)
      7. 연속 3회 실패 시 notifier 비상 알림
    """
    logger.warning("[STUB] scraper.poll_once() — 크롤링 미구현")
```

- [ ] **Step 5: rpa/singleton_macro.py (싱글턴 RPA 스텁)**

`backend/src/ggotaiorder/rpa/singleton_macro.py`:
```python
"""싱글턴 순차 RPA 제어 (스텁).

PRD 6-5: asyncio.Lock()으로 단 하나의 RPA만 순차 실행. 관리 프로그램 창을
찾지 못하면 엑셀(.xlsx)+텍스트 영수증 백업 생성. 완료 후 rpa_status를
'success'/'fail'로 마킹하고 notifier.send 호출.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 다중 채널 충돌 방지용 싱글턴 락 (PRD 8-4)
_rpa_lock = asyncio.Lock()


async def enqueue(order_detail_id: int) -> None:
    """[스텁] order_details 1건을 전산 프로그램에 입력한다 (락 순차).

    TODO(후속):
      - 관리 프로그램 창 탐색(pygetwindow)
      - 있으면 클립보드(pyperclip)+Tab 매크로 입력 → rpa_status='success'/'fail'
      - 없으면 엑셀(openpyxl)+텍스트 영수증 백업 생성
      - 완료 후 await notifier.send(channel, count, success)
    """
    async with _rpa_lock:
        logger.warning("[STUB] rpa.enqueue(order_detail_id=%s)", order_detail_id)
```

- [ ] **Step 6: notifier/sms_sender.py (알림 발송 스텁)**

`backend/src/ggotaiorder/notifier/sms_sender.py`:
```python
"""개인화 알림 발송 (스텁).

PRD 6-6: setting_info.use_notification 확인 → 수신번호 결정
(notification_phone_number ?? member_info.mobile_number) → 템플릿
({channel}/{count} 치환) → 카카오 알림톡/문자 발송 + 이력 기록.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def render_template(template: str, channel: str, count: int) -> str:
    """템플릿의 {channel}/{count} 변수를 실제 값으로 치환한다."""
    return template.replace("{channel}", channel).replace("{count}", str(count))


async def send(channel: str, count: int, success: bool) -> None:
    """[스텁] RPA 결과 알림을 발송한다.

    TODO(후속):
      1. setting_info 조회 (use_notification 'N'이면 종료)
      2. 수신번호 결정(notification_phone_number ?? member_info.mobile_number)
      3. rpa_success_message / rpa_fail_message 선택 후 render_template
      4. 카카오 알림톡/문자 API(httpx) 발송 + 이력 기록
    """
    logger.warning(
        "[STUB] notifier.send(channel=%s, count=%s, success=%s)",
        channel, count, success,
    )
```

- [ ] **Step 7: 스텁 import 확인**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.api.routes import create_app; from ggotaiorder.realtime.listener import RealtimeListener; from ggotaiorder.pipeline.engine import process, ORDER_FIELDS; from ggotaiorder.scraper.crawler import poll_once; from ggotaiorder.rpa.singleton_macro import enqueue; from ggotaiorder.notifier.sms_sender import send, render_template; print('stubs ok', len(ORDER_FIELDS))"
```
Expected: `stubs ok 11` 출력.

- [ ] **Step 8: Commit**

```bash
git add backend/src/ggotaiorder/api/routes.py backend/src/ggotaiorder/realtime/listener.py backend/src/ggotaiorder/pipeline/engine.py backend/src/ggotaiorder/scraper/crawler.py backend/src/ggotaiorder/rpa/singleton_macro.py backend/src/ggotaiorder/notifier/sms_sender.py
git commit -m "feat: 6개 도메인 모듈 스텁 추가 (계약 고정)"
```

---

### Task 7: orchestrator.py — asyncio 루프·배선·수집 on/off (TDD)

**Files:**
- Create: `backend/src/ggotaiorder/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: 실패하는 테스트 작성 (pause/resume 상태)**

`backend/tests/test_orchestrator.py`:
```python
from ggotaiorder.orchestrator import Orchestrator


def test_starts_unpaused():
    orch = Orchestrator()
    assert orch.paused is False


def test_pause_resume_toggles_state():
    orch = Orchestrator()
    orch.pause()
    assert orch.paused is True
    orch.resume()
    assert orch.paused is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_orchestrator.py -v`
Expected: FAIL — `ImportError: cannot import name 'Orchestrator'`.

- [ ] **Step 3: 구현 작성**

`backend/src/ggotaiorder/orchestrator.py`:
```python
"""백엔드 서브시스템 오케스트레이터 (단일 asyncio 이벤트 루프).

FastAPI(uvicorn)·Realtime 리스너·APScheduler(크롤러)를 한 이벤트 루프에서
구동한다. 수집 on/off는 paused 플래그로 제어한다(서비스 stop/start 대응).
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ggotaiorder.api.routes import create_app
from ggotaiorder.realtime.listener import RealtimeListener
from ggotaiorder.scraper.crawler import poll_once

logger = logging.getLogger(__name__)

# 크롤러 폴링 기본 주기(분). 후속: setting_info 값으로 동적 재설정.
_DEFAULT_INTRANET_INTERVAL_MIN = 30


class Orchestrator:
    """모든 백엔드 서브시스템의 수명주기를 관리한다."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._host = host
        self._port = port
        self._paused = False
        self._listener = RealtimeListener()
        self._scheduler = AsyncIOScheduler()
        self._server: uvicorn.Server | None = None
        self._tasks: list[asyncio.Task] = []

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """수집을 일시정지한다 (net stop 대응). 프로세스는 유지."""
        self._paused = True
        logger.info("수집 일시정지 (paused=True)")

    def resume(self) -> None:
        """수집을 재개한다 (net start 대응)."""
        self._paused = False
        logger.info("수집 재개 (paused=False)")

    async def _scheduled_poll(self) -> None:
        """일시정지 상태가 아니면 크롤러를 1회 폴링한다."""
        if self._paused:
            logger.debug("paused 상태 — 크롤링 스킵")
            return
        await poll_once()

    async def start(self) -> None:
        """모든 서브시스템을 기동하고 종료될 때까지 대기한다."""
        logger.info("오케스트레이터 시작")

        await self._listener.start()

        self._scheduler.add_job(
            self._scheduled_poll,
            "interval",
            minutes=_DEFAULT_INTRANET_INTERVAL_MIN,
            id="intranet_poll",
        )
        self._scheduler.start()

        config = uvicorn.Config(
            create_app(), host=self._host, port=self._port, log_level="info"
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()  # 종료 신호 전까지 블로킹

    async def stop(self) -> None:
        """모든 서브시스템을 정상 종료한다."""
        logger.info("오케스트레이터 종료")
        if self._server is not None:
            self._server.should_exit = True
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        await self._listener.stop()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_orchestrator.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: asyncio 오케스트레이터 추가 (서브시스템 배선·수집 on/off)"
```

---

### Task 8: service.py — pywin32 Windows Service 래퍼

**Files:**
- Create: `backend/src/ggotaiorder/service.py`

pywin32가 설치된 Windows에서만 import 가능하다. 워커 스레드에서 asyncio 루프를 돌리고, SvcStop 시 루프에 종료를 요청한다.

- [ ] **Step 1: 구현 작성**

`backend/src/ggotaiorder/service.py`:
```python
"""pywin32 기반 Windows Service 래퍼.

서비스명 'ggotAIorder'. SvcDoRun에서 워커 스레드로 asyncio 이벤트 루프를
돌리며 Orchestrator를 구동하고, SvcStop에서 정상 종료를 요청한다.

설치(관리자 PowerShell):
    backend\\.venv\\Scripts\\python.exe -m ggotaiorder.service install
    backend\\.venv\\Scripts\\python.exe -m ggotaiorder.service start
"""

from __future__ import annotations

import asyncio
import logging

import servicemanager
import win32event
import win32service
import win32serviceutil

from ggotaiorder.logging_setup import setup_logging
from ggotaiorder.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class GgotAIOrderService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ggotAIorder"
    _svc_display_name_ = "ggotAIorder 주문 수집 서비스"
    _svc_description_ = "다중 채널 주문 수집·정형화·자동입력 백그라운드 서비스."

    def __init__(self, args) -> None:
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orchestrator: Orchestrator | None = None

    def SvcStop(self) -> None:
        """SCM 정지 요청 처리 (net stop)."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._loop is not None and self._orchestrator is not None:
            asyncio.run_coroutine_threadsafe(self._orchestrator.stop(), self._loop)
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self) -> None:
        """SCM 시작 요청 처리 (net start)."""
        setup_logging()
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._orchestrator = Orchestrator()
        try:
            self._loop.run_until_complete(self._orchestrator.start())
        finally:
            self._loop.close()


def main() -> None:
    win32serviceutil.HandleCommandLine(GgotAIOrderService)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: import 확인 (Windows + pywin32 설치 전제)**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "import ggotaiorder.service as s; print('service import ok', s.GgotAIOrderService._svc_name_)"
```
Expected: `service import ok ggotAIorder` 출력. (pywin32 import 실패 시 post-install 필요 — README 참고하여 보고.)

- [ ] **Step 3: Commit**

```bash
git add backend/src/ggotaiorder/service.py
git commit -m "feat: pywin32 Windows Service 래퍼 추가"
```

---

### Task 9: tray.py — pystray 트레이 아이콘

**Files:**
- Create: `backend/src/ggotaiorder/tray.py`

- [ ] **Step 1: 구현 작성**

`backend/src/ggotaiorder/tray.py`:
```python
"""pystray 기반 시스템 트레이 아이콘.

상태: 🟢 수집 중 / 🔴 수집 중지. 우클릭 메뉴: 상황판 열기 / 주문수집 상태 /
ggotAIorder 정보. 더블클릭 시 ggotAIya UI 호출(후속).
"""

from __future__ import annotations

import logging

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _make_status_image(running: bool) -> Image.Image:
    """상태 색상 원(🟢/🔴)을 그린 32x32 아이콘 이미지를 생성한다."""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (40, 200, 80) if running else (220, 50, 50)
    draw.ellipse((4, 4, 28, 28), fill=color)
    return img


def build_tray(running: bool = True) -> pystray.Icon:
    """트레이 아이콘 객체를 생성해 반환한다 (run()은 호출측에서)."""
    menu = pystray.Menu(
        pystray.MenuItem("상황판 열기", _on_open_dashboard, default=True),
        pystray.MenuItem(
            lambda item: "🟢 주문 수집 중" if running else "🔴 주문 수집 중지",
            None,
            enabled=False,
        ),
        pystray.MenuItem("ggotAIorder 정보", _on_about),
    )
    return pystray.Icon(
        "ggotAIorder",
        icon=_make_status_image(running),
        title="ggotAIorder",
        menu=menu,
    )


def _on_open_dashboard(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """[스텁] ggotAIya UI 호출. TODO(후속): Electron 앱 실행/포커스."""
    logger.warning("[STUB] 상황판 열기 클릭")


def _on_about(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    logger.info("ggotAIorder v0.1.0")
```

- [ ] **Step 2: import·아이콘 생성 확인**

Run:
```powershell
backend\.venv\Scripts\python.exe -c "from ggotaiorder.tray import build_tray, _make_status_image; _make_status_image(True); _make_status_image(False); print('tray ok', build_tray().name)"
```
Expected: `tray ok ggotAIorder` 출력 (아이콘 run()은 호출하지 않음).

- [ ] **Step 3: Commit**

```bash
git add backend/src/ggotaiorder/tray.py
git commit -m "feat: pystray 트레이 아이콘 추가"
```

---

### Task 10: run_dev.py·README·전체 스모크 테스트

**Files:**
- Create: `backend/run_dev.py`
- Create: `backend/README.md`
- Create: `backend/tests/test_smoke.py`

- [ ] **Step 1: run_dev.py 작성 (서비스 없이 로컬 디버그 실행)**

`backend/run_dev.py`:
```python
"""서비스 등록 없이 오케스트레이터를 로컬에서 직접 구동한다 (디버그용).

실행: backend\\.venv\\Scripts\\python.exe backend\\run_dev.py
Ctrl+C 로 종료.
"""

from __future__ import annotations

import asyncio

from ggotaiorder.logging_setup import setup_logging
from ggotaiorder.orchestrator import Orchestrator


async def _main() -> None:
    setup_logging()
    orch = Orchestrator()
    try:
        await orch.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        await orch.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
```

- [ ] **Step 2: 전체 스모크 테스트 작성**

`backend/tests/test_smoke.py`:
```python
"""전체 모듈 import 및 핵심 계약 스모크 테스트."""

import importlib

import pytest

MODULES = [
    "ggotaiorder.config",
    "ggotaiorder.logging_setup",
    "ggotaiorder.core.crypto",
    "ggotaiorder.core.supabase_client",
    "ggotaiorder.orchestrator",
    "ggotaiorder.tray",
    "ggotaiorder.api.routes",
    "ggotaiorder.realtime.listener",
    "ggotaiorder.pipeline.engine",
    "ggotaiorder.scraper.crawler",
    "ggotaiorder.rpa.singleton_macro",
    "ggotaiorder.notifier.sms_sender",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_pipeline_has_11_fields():
    from ggotaiorder.pipeline.engine import ORDER_FIELDS
    assert len(ORDER_FIELDS) == 11


def test_fastapi_app_has_health_route():
    from ggotaiorder.api.routes import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/v1/gate-phone/upload" in paths


def test_notifier_template_rendering():
    from ggotaiorder.notifier.sms_sender import render_template
    out = render_template("{channel} 주문 {count}건 완료", "인터라넷", 3)
    assert out == "인터라넷 주문 3건 완료"
```

참고: `ggotaiorder.service`는 pywin32(servicemanager) 의존으로 환경에 따라 import가 달라질 수 있어 스모크 파라미터에서 제외한다(Task 8에서 별도 확인).

- [ ] **Step 3: README.md 작성**

`backend/README.md`:
```markdown
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
```

- [ ] **Step 4: 전체 테스트 실행**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`
Expected: 모든 테스트 PASS (config 4 + crypto 3 + orchestrator 2 + smoke 15). 실패 시 원인 보고.

- [ ] **Step 5: Commit**

```bash
git add backend/run_dev.py backend/README.md backend/tests/test_smoke.py
git commit -m "feat: 로컬 실행 진입점·README·전체 스모크 테스트 추가"
```

---

## Self-Review 결과

- **Spec 커버리지**: 폴더구조(Task1·6) / config(2) / logging(3) / crypto-AES(4) / supabase(5) / 6개 스텁 계약(6) / 오케스트레이터·수집 on/off(7) / service(8) / tray(9) / run_dev·README·검증(10) — 설계서 9개 섹션 모두 매핑됨. 비범위 항목은 스텁 docstring의 TODO로 표시.
- **Placeholder**: 도메인 모듈 본문의 `TODO(후속)`는 의도된 스텁 표식이며, 모든 스텁은 실제 동작하는 시그니처·로그·반환을 갖춤(빈 placeholder 아님).
- **타입 일관성**: `Orchestrator.paused/pause/resume/start/stop`, `RealtimeListener.start/stop`, `process(call_history_id)`, `poll_once()`, `enqueue(order_detail_id)`, `send(channel,count,success)`, `render_template`, `create_app`, `ORDER_FIELDS(11)` — Task 간 시그니처 일치 확인.
- **검증 가능성**: crypto 고정 벡터는 실제 cryptography로 생성·검증됨. 전체 pytest로 회귀 검증.
