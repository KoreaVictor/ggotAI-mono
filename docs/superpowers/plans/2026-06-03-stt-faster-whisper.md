# STT (faster-whisper) 실구현 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pipeline.stt.transcribe` 스텁을 faster-whisper 실구현으로 — Storage(`call-audio`) 음성 다운로드 → 한국어 STT → 텍스트 반환. engine의 STT 호출을 비블로킹·예외안전하게 보정.

**Architecture:** 자기완결형 `pipeline/stt.py`(내부 `_download_audio` + lazy `_get_model`). faster_whisper는 `_get_model` 내부에서 **지연 import**(ctranslate2 네이티브 의존이 모듈 import·오프라인 테스트를 깨지 않도록). 오프라인 테스트는 두 seam을 monkeypatch해 결정적. 실제 모델 구동은 opt-in/라이브 체크리스트.

**Tech Stack:** Python 3.13, faster-whisper 1.2.1, supabase-py 2.30.1, pytest, pytest-asyncio.

설계서: `docs/superpowers/specs/2026-06-03-stt-faster-whisper-design.md`
브랜치: `feature/stt-faster-whisper` (이미 생성됨)

**중요(환경):** 이 개발 머신은 ctranslate2 DLL 로드에 MS Visual C++ Redistributable이 필요해 **실제 faster-whisper 구동이 현재 불가**. 따라서 (1) faster_whisper는 반드시 `_get_model` 내부에서 import, (2) **라이브 STT 테스트를 이 머신에서 실행하지 말 것**(기본 skip 유지). 검증은 오프라인 결정적 테스트로 한다.

**검증 명령 전제:** 모든 pytest/python은 `backend\.venv\Scripts\python.exe`로, 저장소 루트 `C:\ggotAI\ggotAIorder`에서 실행.

---

## File Structure

| 파일 | 책임 | 유형 |
| --- | --- | --- |
| `backend/src/ggotaiorder/pipeline/stt.py` | Storage 다운로드 + faster-whisper 한국어 변환 (스텁 대체) | 수정 |
| `backend/src/ggotaiorder/pipeline/engine.py` | STT 호출 to_thread + except Exception 보정 | 수정 |
| `backend/tests/test_pipeline_stt.py` | STT 오프라인 결정적 테스트 (재작성) | 수정 |
| `backend/tests/test_pipeline_stt_live.py` | 실제 모델 변환 (opt-in, 기본 skip) | 신규 |
| `backend/tests/test_pipeline_engine.py` | STT 경로 테스트 갱신 | 수정 |
| `backend/README.md` | STT 라이브 체크리스트(VC++ Redist 등) | 수정 |

---

### Task 1: pipeline/stt.py — faster-whisper 실구현 (TDD)

**Files:** Modify `backend/src/ggotaiorder/pipeline/stt.py`; rewrite `backend/tests/test_pipeline_stt.py`; create `backend/tests/test_pipeline_stt_live.py`.

기존 `test_pipeline_stt.py`는 `transcribe`가 NotImplementedError를 던지는지 확인하는 스텁 테스트다 — 전체 재작성한다.

- [ ] **Step 1: 오프라인 테스트 재작성** — `backend/tests/test_pipeline_stt.py` 전체 교체:
```python
import os

import ggotaiorder.pipeline.stt as stt_mod
from ggotaiorder.pipeline.stt import transcribe


class _Seg:
    def __init__(self, text: str):
        self.text = text


class _FakeModel:
    def __init__(self, segments):
        self._segments = segments
        self.calls: list[tuple] = []

    def transcribe(self, path, language=None, **kwargs):
        self.calls.append((path, language))
        return (self._segments, None)


def test_transcribe_downloads_runs_and_joins(monkeypatch):
    monkeypatch.setattr(stt_mod, "_download_audio", lambda name: b"FAKEAUDIO")
    fake = _FakeModel([_Seg("  안녕하세요 "), _Seg("꽃 주문이요 ")])
    monkeypatch.setattr(stt_mod, "_get_model", lambda: fake)

    text = transcribe("7/abc.wav")

    assert text == "안녕하세요 꽃 주문이요"
    # 모델은 임시파일 경로 + language='ko' 로 호출됨
    temp_path, language = fake.calls[0]
    assert language == "ko"
    assert temp_path.endswith(".wav")
    # 임시파일은 finally 에서 정리되어 남지 않음
    assert not os.path.exists(temp_path)


def test_transcribe_empty_segments_returns_empty(monkeypatch):
    monkeypatch.setattr(stt_mod, "_download_audio", lambda name: b"X")
    monkeypatch.setattr(stt_mod, "_get_model", lambda: _FakeModel([]))
    assert transcribe("1/a.mp3") == ""


def test_module_import_does_not_require_faster_whisper():
    # _get_model 내부 지연 import 이므로 모듈 import 시 faster_whisper 미로딩
    import sys
    assert "faster_whisper" not in sys.modules or stt_mod._model is None
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt.py -v`
Expected: FAIL — `_download_audio`/`_get_model` 속성 없음(현재 스텁엔 미존재) → AttributeError.

- [ ] **Step 3: stt.py 전체 교체** — `backend/src/ggotaiorder/pipeline/stt.py`:
```python
"""음성→텍스트(STT): Supabase Storage 음성 다운로드 후 faster-whisper 한국어 변환.

faster_whisper 는 _get_model 내부에서 지연 import 한다. ctranslate2 네이티브 의존이
모듈 import 시점에 로드되지 않게 하여, 오프라인 테스트와 타 모듈의 import 안전성을 보장한다.
설정은 환경변수로 조정한다(기본 small/int8/cpu).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import PurePosixPath

from ggotaiorder.api.storage import AUDIO_BUCKET
from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    """faster-whisper WhisperModel 싱글턴(지연 생성·지연 import)."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        model_name = os.getenv("STT_MODEL", "small")
        compute_type = os.getenv("STT_COMPUTE_TYPE", "int8")
        device = os.getenv("STT_DEVICE", "cpu")
        logger.info(
            "faster-whisper 모델 로드: %s (device=%s, compute=%s)",
            model_name, device, compute_type,
        )
        _model = WhisperModel(model_name, device=device, compute_type=compute_type)
    return _model


def _download_audio(object_name: str) -> bytes:
    """call-audio 버킷에서 음성 파일 바이트를 내려받는다."""
    return get_client().storage.from_(AUDIO_BUCKET).download(object_name)


def transcribe(audio_file_name: str) -> str:
    """Storage의 음성 파일을 한국어 텍스트로 변환해 반환한다.

    audio_file_name: Storage 객체명(예: '{shop_key}/{uuid}.wav').
    """
    data = _download_audio(audio_file_name)
    suffix = PurePosixPath(audio_file_name).suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        segments, _info = _get_model().transcribe(tmp.name, language="ko")
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
```

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt.py -v`
Expected: 3 passed.

- [ ] **Step 5: 라이브 opt-in 테스트 작성** — `backend/tests/test_pipeline_stt_live.py`:
```python
import os

import pytest

# 기본 skip. 실제 faster-whisper 구동은 RUN_LIVE_STT=1 + STT_SAMPLE_PATH 설정 시에만.
# (이 개발 머신은 ctranslate2 가 MS VC++ Redistributable 미설치로 구동 불가 — 라이브 검증은 별도 환경)
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_STT") != "1" or not os.getenv("STT_SAMPLE_PATH"),
    reason="RUN_LIVE_STT=1 와 STT_SAMPLE_PATH 설정 시에만 실행",
)


def test_live_transcribe_sample():
    from ggotaiorder.pipeline.stt import _get_model

    sample = os.environ["STT_SAMPLE_PATH"]
    segments, _info = _get_model().transcribe(sample, language="ko")
    text = " ".join(s.text.strip() for s in segments).strip()
    assert text != ""
```

- [ ] **Step 6: 라이브 테스트가 기본 skip 되는지 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt_live.py -v`
Expected: 1 skipped. (이 머신에서 RUN_LIVE_STT 설정 금지 — ctranslate2 구동 불가.)

- [ ] **Step 7: import 안전성 확인** — Run:
```powershell
backend\.venv\Scripts\python.exe -c "import ggotaiorder.pipeline.stt, ggotaiorder.pipeline.engine; print('import ok')"
```
Expected: `import ok` (faster_whisper/ctranslate2 미로딩 — 지연 import).

- [ ] **Step 8: Commit**
```bash
git add backend/src/ggotaiorder/pipeline/stt.py backend/tests/test_pipeline_stt.py backend/tests/test_pipeline_stt_live.py
git commit -m "feat: STT(faster-whisper) 실구현 — Storage 다운로드+한국어 변환(지연 import)"
```

---

### Task 2: engine.process — STT 호출 비블로킹·예외안전 보정 (TDD)

**Files:** Modify `backend/src/ggotaiorder/pipeline/engine.py`; modify `backend/tests/test_pipeline_engine.py`.

현재 engine의 STT 블록은 `stt_text = transcribe(...)`를 동기 호출하고 `except NotImplementedError`만 처리한다. 실 STT는 느리고(CPU 바운드) 다양한 예외가 가능하므로 보정한다.

- [ ] **Step 1: engine 테스트 갱신(실패 유도)** — `backend/tests/test_pipeline_engine.py`에서 기존 `test_stt_needed_but_stub_skips` 함수를 찾아 **삭제**하고, 그 자리에 아래 두 테스트를 추가한다(파일의 나머지 — imports, FakeRepo, `_row`, `_full_extraction`, 다른 테스트 — 는 그대로 둔다):
```python
async def test_stt_path_transcribes_then_processes(monkeypatch):
    repo = FakeRepo(_row(stt_text=None, audio_file_name="call_002.wav"))
    monkeypatch.setattr(engine, "transcribe", lambda name: "변환된 주문 텍스트")
    monkeypatch.setattr(engine, "extract_order", lambda text: _full_extraction())
    enqueued: list[int] = []

    async def fake_enqueue(order_id: int) -> None:
        enqueued.append(order_id)

    monkeypatch.setattr(engine, "enqueue", fake_enqueue)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert ("update_stt", 1, "변환된 주문 텍스트") in repo.calls
    assert "insert" in kinds
    assert enqueued == [999]


async def test_stt_failure_skips(monkeypatch):
    repo = FakeRepo(_row(stt_text=None, audio_file_name="call_003.wav"))

    def boom(name):
        raise RuntimeError("stt fail")

    called = {"extract": False}

    def spy_extract(text):
        called["extract"] = True
        return _full_extraction()

    monkeypatch.setattr(engine, "transcribe", boom)
    monkeypatch.setattr(engine, "extract_order", spy_extract)
    monkeypatch.setattr(engine, "enqueue", lambda order_id: None)

    await engine.process(1, repo=repo)

    kinds = [c[0] for c in repo.calls]
    assert "insert" not in kinds
    assert called["extract"] is False
```

- [ ] **Step 2: 실패 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_engine.py -v`
Expected: `test_stt_path_transcribes_then_processes` 실패 가능(현재 engine은 `transcribe`를 동기 호출하지만 `except NotImplementedError`만 잡음 — monkeypatch한 정상 lambda면 통과할 수도 있으나, `test_stt_failure_skips`는 RuntimeError가 `except NotImplementedError`에 안 걸려 **process 밖으로 전파→테스트 에러**가 되어야 한다). 최소한 `test_stt_failure_skips`가 FAIL(에러)임을 확인.

- [ ] **Step 3: engine.py STT 블록 수정** — `backend/src/ggotaiorder/pipeline/engine.py`:

(a) 상단 import 영역에 `import asyncio` 추가(`from __future__ import annotations` 아래, 다른 import와 함께):
```python
import asyncio
import logging
```

(b) STT 블록을 아래로 교체(기존 `try/except NotImplementedError` 부분):
```python
    stt_text = row.stt_text
    if not stt_text:
        if row.audio_file_name and row.audio_file_name != INTRANET_AUDIO_MARKER:
            try:
                stt_text = await asyncio.to_thread(transcribe, row.audio_file_name)
                repo.update_stt_text(call_history_id, stt_text)
            except Exception:
                logger.exception("STT 처리 실패 — 건너뜀 id=%s", call_history_id)
                return
        else:
            logger.warning("stt_text 없음 — 건너뜀 id=%s", call_history_id)
            return
```
나머지(추출·필터·INSERT·enqueue, count_missing, _build_order_payload)는 불변.

- [ ] **Step 4: 통과 확인** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_engine.py -v`
Expected: 모든 engine 테스트 pass(주문 Y / 비주문 N / STT 변환 후 처리 / STT 실패 skip = 4 passed).

- [ ] **Step 5: Commit**
```bash
git add backend/src/ggotaiorder/pipeline/engine.py backend/tests/test_pipeline_engine.py
git commit -m "feat: engine STT 호출 비블로킹(to_thread)·예외안전(except Exception) 보정"
```

---

### Task 3: 전체 검증 + README STT 체크리스트

**Files:** Modify `backend/README.md`

- [ ] **Step 1: 전체 스위트 실행** — Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: 모두 pass + skipped. 신규/변경: stt 3 passed, stt_live 1 skipped, engine STT 테스트 2(기존 1 삭제→2 추가). 기존 라이브 Gemini 2 skipped 유지. 실제 합계를 보고(대략 52 passed, 3 skipped).

- [ ] **Step 2: README 에 STT 라이브 체크리스트 추가** — `backend/README.md`의 `## 구조` 섹션 바로 앞에 다음 섹션 삽입:
```markdown
## STT(faster-whisper) 라이브 구동 체크리스트

STT는 코드로 구현·오프라인 테스트되었으나, 실제 음성 변환에는 다음이 필요합니다:

1. **MS Visual C++ Redistributable** 설치 — ctranslate2 네이티브 DLL 의존(미설치 시 `faster_whisper` import가 DLL 로드 실패).
2. 최초 실행 시 STT 모델 자동 다운로드(기본 `small` ~460MB). 환경변수로 조정: `STT_MODEL`/`STT_COMPUTE_TYPE`/`STT_DEVICE`(기본 small/int8/cpu).
3. `call-audio` 버킷에 통화 음성이 적재되어 있어야 함(인입 경로 증분의 버킷 생성 선행).
4. 한국어 샘플 음성으로 opt-in 검증: `$env:RUN_LIVE_STT="1"; $env:STT_SAMPLE_PATH="<sample.wav>"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_pipeline_stt_live.py -v`

```

- [ ] **Step 3: Commit**
```bash
git add backend/README.md
git commit -m "docs: STT 라이브 구동 체크리스트 README 추가"
```

---

## Self-Review 결과

- **Spec 커버리지**: 자기완결형 stt.py·지연 import(Task1) / Storage 다운로드 `_download_audio`(Task1) / lazy `_get_model` env 설정(Task1) / 임시파일 정리(Task1) / engine to_thread+except Exception(Task2) / 오프라인 결정적 테스트(Task1) / engine STT 경로·실패 테스트(Task2) / 라이브 opt-in(Task1 Step5) / 체크리스트+VC++ Redist(Task3) — 설계서 절 모두 매핑.
- **Placeholder 스캔**: 라이브/모델 다운로드는 의도적 비범위(체크리스트). TODO 없음.
- **타입 일관성**: `transcribe(audio_file_name: str) -> str`(engine 호출 시그니처 유지), `_download_audio(object_name)->bytes`, `_get_model()->model`(`.transcribe(path, language=...) -> (segments, info)`), engine `transcribe`/`extract_order`/`enqueue` monkeypatch 대상 일치, FakeRepo의 `update_stt_text` 기록 형식(`("update_stt", id, text)`)과 테스트 assert 일치.
- **환경 주의**: 이 머신은 ctranslate2 구동 불가(VC++ Redist 미설치) → 지연 import로 오프라인 안전 확보, 라이브 테스트는 기본 skip(이 머신에서 RUN_LIVE_STT 설정 금지). 실 검증은 별도 환경 체크리스트.
- **회귀**: 기존 50 테스트 중 engine 1개(stub skip) 대체, 나머지 유지.
