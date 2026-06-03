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
    temp_path, language = fake.calls[0]
    assert language == "ko"
    assert temp_path.endswith(".wav")
    assert not os.path.exists(temp_path)


def test_transcribe_empty_segments_returns_empty(monkeypatch):
    monkeypatch.setattr(stt_mod, "_download_audio", lambda name: b"X")
    monkeypatch.setattr(stt_mod, "_get_model", lambda: _FakeModel([]))
    assert transcribe("1/a.mp3") == ""


def test_module_import_does_not_require_faster_whisper():
    import sys
    assert "faster_whisper" not in sys.modules or stt_mod._model is None
