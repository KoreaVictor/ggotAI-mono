"""HTTP(Whisper) STT provider + 스토리지 객체 키 복원 테스트."""

from __future__ import annotations

import ggotaiorder.pipeline.stt as stt_mod


# ---- _resolve_key: DB의 audio_file_name → 실제 Storage 객체 키 ----

def test_resolve_key_flat_phone_filename_reconstructs_folders():
    # ggotAIhp 핸드폰 업로드: flat 파일명 → {매장번호}/{YYYYMM}/{파일명}
    name = "01058921670_0555828585_20260612_190438.wav"
    assert stt_mod._resolve_key(name) == (
        "01058921670/202606/01058921670_0555828585_20260612_190438.wav"
    )


def test_resolve_key_unknown_caller_still_reconstructs():
    name = "01058921670_Unknown_20260610_205705.wav"
    assert stt_mod._resolve_key(name) == (
        "01058921670/202606/01058921670_Unknown_20260610_205705.wav"
    )


def test_resolve_key_passthrough_when_already_full_key():
    # 가게전화(api 업로드)은 이미 {shop_key}/{uuid}.ext 풀 키 — 그대로 사용
    assert stt_mod._resolve_key("19/abcdef.wav") == "19/abcdef.wav"


def test_resolve_key_defensive_on_malformed_name():
    # 비정형(언더스코어 부족) — 복원 불가 시 원본 그대로(방어)
    assert stt_mod._resolve_key("weird.wav") == "weird.wav"


# ---- HttpWhisperProvider: OpenAI 호환 멀티파트 전사 ----

class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_http_provider_posts_multipart_and_parses_text(monkeypatch):
    monkeypatch.setenv("STT_API_BASE", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("STT_API_KEY", "gsk_test")
    monkeypatch.setenv("STT_MODEL", "whisper-large-v3")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["files"] = kwargs.get("files")
        captured["data"] = kwargs.get("data")
        return _FakeResp({"text": "  꽃 주문이요  "})

    monkeypatch.setattr(stt_mod.httpx, "post", fake_post)

    text = stt_mod.HttpWhisperProvider().transcribe(b"AUDIOBYTES", "1/a.wav")

    assert text == "꽃 주문이요"
    assert captured["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert captured["headers"]["Authorization"] == "Bearer gsk_test"
    assert captured["data"]["model"] == "whisper-large-v3"
    assert captured["data"]["language"] == "ko"
    # 멀티파트 file 필드에 오디오 바이트가 실림
    assert captured["files"]["file"][1] == b"AUDIOBYTES"


def test_http_provider_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("STT_API_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError):
        stt_mod.HttpWhisperProvider().transcribe(b"X", "1/a.wav")


def test_http_provider_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("STT_API_KEY", "gsk_test")
    monkeypatch.setattr(
        stt_mod.httpx, "post", lambda url, **kw: _FakeResp({}, status=500)
    )
    import pytest

    with pytest.raises(RuntimeError):
        stt_mod.HttpWhisperProvider().transcribe(b"X", "1/a.wav")


# ---- provider 선택: STT_PROVIDER ----

def test_transcribe_uses_http_provider_by_default(monkeypatch):
    monkeypatch.delenv("STT_PROVIDER", raising=False)
    monkeypatch.setattr(stt_mod, "_download_audio", lambda key: b"BYTES")
    seen = {}

    class _Spy:
        def transcribe(self, audio, filename):
            seen["audio"] = audio
            seen["filename"] = filename
            return "전사결과"

    monkeypatch.setattr(stt_mod, "HttpWhisperProvider", lambda: _Spy())

    out = stt_mod.transcribe("01058921670_0555828585_20260612_190438.wav")

    assert out == "전사결과"
    assert seen["audio"] == b"BYTES"
