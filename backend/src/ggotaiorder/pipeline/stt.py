"""음성→텍스트(STT) 인터페이스 (faster-whisper 실연동은 다음 증분).

이번 증분에서는 인터페이스만 고정하고, 호출 시 NotImplementedError 를 던진다.
engine.process 는 이 예외를 잡아 해당 건을 건너뛴다(파이프라인 비중단).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def transcribe(audio_file_name: str) -> str:
    """[스텁] 음성 파일을 텍스트로 변환한다.

    TODO(다음 증분): Supabase Storage에서 audio_file_name 다운로드 →
    faster-whisper(한국어)로 STT → 텍스트 반환.
    """
    logger.warning("[STUB] stt.transcribe 미구현: %s", audio_file_name)
    raise NotImplementedError("STT(faster-whisper)는 다음 증분에서 구현됩니다.")
