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
