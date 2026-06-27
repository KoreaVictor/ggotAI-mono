import base64

import httpx
import pytest

from ggotaiorder.notifier import provider as provider_mod
from ggotaiorder.notifier.provider import (
    HttpNotificationProvider,
    _only_digits,
)


def test_only_digits_strips_non_numeric():
    assert _only_digits("010-1111-2222") == "01011112222"
    assert _only_digits("+82 10 1234 5678") == "821012345678"


def test_http_provider_accepts_new_kwargs_and_uses_text(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("NOTIFY_API_URL", "https://example.test/send")
    monkeypatch.setenv("NOTIFY_API_KEY", "k")
    monkeypatch.setattr(provider_mod.httpx, "post", fake_post)

    HttpNotificationProvider().send_message(
        "010-1111-2222", "본문", template_code="T1", variables={"건수": "1"}
    )
    assert captured["json"] == {"to": "010-1111-2222", "text": "본문"}
