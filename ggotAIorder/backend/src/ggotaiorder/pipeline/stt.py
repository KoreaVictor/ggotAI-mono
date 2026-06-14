"""음성→텍스트(STT): Storage 음성 다운로드 후 provider로 한국어 전사.

provider 두 종류를 STT_PROVIDER 로 선택한다.
- `http`(기본): OpenAI 호환 `/v1/audio/transcriptions` HTTP 호출. 지금은 Groq,
  나중엔 자체 whisper 서버로 STT_API_BASE 만 교체(꽃집마다 설치 불필요).
- `local`: faster-whisper 로컬 모델. ctranslate2 네이티브 의존은 _get_model 내부에서
  지연 import 한다(모듈 import 시점 로드 회피 → 오프라인 테스트·타 모듈 import 안전).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import PurePosixPath
from typing import Protocol

import httpx

from ggotaiorder.api.storage import AUDIO_BUCKET
from ggotaiorder.core.supabase_client import get_client

logger = logging.getLogger(__name__)

_model = None


class WhisperProvider(Protocol):
    """오디오 바이트 → 한국어 텍스트 전사 계약."""

    def transcribe(self, audio: bytes, filename: str) -> str: ...


class HttpWhisperProvider:
    """OpenAI 호환 HTTP 전사 (Groq / OpenAI / 자체 whisper 서버 공용).

    env: STT_API_BASE(기본 https://api.openai.com/v1), STT_API_KEY, STT_MODEL(기본 whisper-1).
    키 미설정 시 호출 시점에 RuntimeError.
    """

    def transcribe(self, audio: bytes, filename: str) -> str:
        base = os.getenv("STT_API_BASE", "https://api.openai.com/v1").rstrip("/")
        api_key = os.getenv("STT_API_KEY")
        model = os.getenv("STT_MODEL", "whisper-1")
        if not api_key:
            raise RuntimeError("STT_API_KEY 미설정 — HTTP STT 불가")
        resp = httpx.post(
            f"{base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio)},
            data={"model": model, "language": "ko", "response_format": "json"},
            timeout=120.0,
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()


class LocalWhisperProvider:
    """faster-whisper 로컬 전사(자체 서버 GPU 등). 임시파일로 기록 후 변환."""

    def transcribe(self, audio: bytes, filename: str) -> str:
        suffix = PurePosixPath(filename).suffix or ".wav"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(audio)
            tmp.close()
            segments, _info = _get_model().transcribe(tmp.name, language="ko")
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def _provider() -> WhisperProvider:
    """STT_PROVIDER env 로 전사 provider 를 선택한다(기본 http)."""
    if os.getenv("STT_PROVIDER", "http") == "local":
        return LocalWhisperProvider()
    return HttpWhisperProvider()


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


def _resolve_key(audio_file_name: str) -> str:
    """DB의 audio_file_name 을 실제 Storage 객체 키로 변환한다.

    - 이미 `/` 를 포함하면 풀 키(가게전화 api 업로드 `{shop_key}/{uuid}.ext`) → 그대로.
    - flat 파일명(핸드폰=ggotAIhp)이면 `{매장번호}/{YYYYMM}/{파일명}` 으로 복원한다.
      규칙: `01058921670_0555828585_20260612_190438.wav`
            → `01058921670/202606/01058921670_0555828585_20260612_190438.wav`
    - 복원 규칙에 맞지 않으면(언더스코어 부족/날짜 비정형) 원본 그대로 반환(방어).
    """
    if "/" in audio_file_name:
        return audio_file_name
    stem = audio_file_name.rsplit(".", 1)[0]
    parts = stem.split("_")
    if len(parts) < 4:
        return audio_file_name
    phone, date = parts[0], parts[-2]
    if len(date) < 6 or not date[:6].isdigit():
        return audio_file_name
    return f"{phone}/{date[:6]}/{audio_file_name}"


def _download_audio(object_name: str) -> bytes:
    """audio-files 버킷에서 음성 파일 바이트를 내려받는다."""
    return get_client().storage.from_(AUDIO_BUCKET).download(object_name)


def transcribe(audio_file_name: str) -> str:
    """Storage의 음성 파일을 한국어 텍스트로 변환해 반환한다.

    audio_file_name: DB server_call_history.audio_file_name (핸드폰=flat 파일명,
    가게전화=풀 키). _resolve_key 로 실제 객체 키를 구해 다운로드 후 provider 로 전사.
    """
    data = _download_audio(_resolve_key(audio_file_name))
    return _provider().transcribe(data, audio_file_name)
