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
