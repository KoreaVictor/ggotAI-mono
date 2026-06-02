import pytest

from ggotaiorder.pipeline.stt import transcribe


def test_transcribe_not_implemented():
    with pytest.raises(NotImplementedError):
        transcribe("some_audio.wav")
