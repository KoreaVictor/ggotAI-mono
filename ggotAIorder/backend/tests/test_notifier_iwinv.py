import base64

import httpx
import pytest

from ggotaiorder.notifier import provider as provider_mod
from ggotaiorder.notifier.provider import (
    HttpNotificationProvider,
    KakaoIwinvProvider,
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


def _ok_response(url, code=200, fail=0):
    return httpx.Response(
        200,
        json={"code": code, "message": "ok", "success": 1, "fail": fail},
        request=httpx.Request("POST", url),
    )


def test_iwinv_builds_request_and_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _ok_response(url)

    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(provider_mod.httpx, "post", fake_post)

    KakaoIwinvProvider().send_message(
        "010-1111-2222", "본문무시", template_code="TPL_OK", variables={"건수": "1"}
    )

    assert captured["url"] == "https://biz.service.iwinv.kr/api/send/"
    assert captured["headers"]["AUTH"] == base64.b64encode(b"secret-key").decode("ascii")
    assert captured["json"]["templateCode"] == "TPL_OK"
    assert captured["json"]["reSend"] == "N"
    assert captured["json"]["list"] == [
        {"phone": "01011112222", "templateParam": {"건수": "1"}}
    ]


def test_iwinv_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("IWINV_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="IWINV_API_KEY"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )


def test_iwinv_raises_when_template_code_missing(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    with pytest.raises(RuntimeError, match="template_code"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code=None, variables={"건수": "1"}
        )


def test_iwinv_raises_on_non_200_code(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: _ok_response(url, code=400),
    )
    with pytest.raises(RuntimeError, match="iwinv"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )


def test_iwinv_raises_when_fail_count_nonzero(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: _ok_response(url, fail=1),
    )
    with pytest.raises(RuntimeError, match="iwinv"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )
