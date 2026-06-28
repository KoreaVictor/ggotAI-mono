import httpx
import pytest

from ggotaiorder.notifier import provider as provider_mod
from ggotaiorder.notifier.provider import (
    HttpNotificationProvider,
    KakaoBizmProvider,
    make_provider,
)


def _bizm_response(url, code="success"):
    return httpx.Response(
        200,
        json=[
            {
                "code": code,
                "data": {"phn": "01011112222", "type": "at", "msgid": "WEB123"},
                "message": "K000",
                "originMessage": None,
            }
        ],
        request=httpx.Request("POST", url),
    )


def test_bizm_builds_request_and_userid_header(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _bizm_response(url)

    monkeypatch.setenv("BIZM_USER_ID", "myaccount")
    monkeypatch.setenv("BIZM_PROFILE_KEY", "profile-key-40-chars")
    monkeypatch.setattr(provider_mod.httpx, "post", fake_post)

    KakaoBizmProvider().send_message(
        "010-1111-2222", "주문접수 1건", template_code="TPL_OK", variables={"건수": "1"}
    )

    assert captured["url"] == "https://alimtalk-api.bizmsg.kr/v2/sender/send"
    assert captured["headers"]["userid"] == "myaccount"
    assert captured["headers"]["Content-Type"] == "application/json"
    # body 는 JSON Array (최대 100건), 단건 발송
    assert captured["json"] == [
        {
            "message_type": "AT",
            "phn": "01011112222",
            "profile": "profile-key-40-chars",
            "tmplId": "TPL_OK",
            "msg": "주문접수 1건",
            "reserveDt": "00000000000000",
        }
    ]


def test_bizm_raises_when_user_id_missing(monkeypatch):
    monkeypatch.delenv("BIZM_USER_ID", raising=False)
    monkeypatch.setenv("BIZM_PROFILE_KEY", "profile-key")
    with pytest.raises(RuntimeError, match="BIZM_USER_ID"):
        KakaoBizmProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables=None
        )


def test_bizm_raises_when_profile_key_missing(monkeypatch):
    monkeypatch.setenv("BIZM_USER_ID", "myaccount")
    monkeypatch.delenv("BIZM_PROFILE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BIZM_PROFILE_KEY"):
        KakaoBizmProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables=None
        )


def test_bizm_raises_when_template_code_missing(monkeypatch):
    monkeypatch.setenv("BIZM_USER_ID", "myaccount")
    monkeypatch.setenv("BIZM_PROFILE_KEY", "profile-key")
    with pytest.raises(RuntimeError, match="template_code"):
        KakaoBizmProvider().send_message(
            "010-1111-2222", "x", template_code=None, variables=None
        )


def test_bizm_raises_when_any_element_failed(monkeypatch):
    monkeypatch.setenv("BIZM_USER_ID", "myaccount")
    monkeypatch.setenv("BIZM_PROFILE_KEY", "profile-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: _bizm_response(
            url, code="fail"
        ),
    )
    with pytest.raises(RuntimeError, match="bizm"):
        KakaoBizmProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables=None
        )


def test_bizm_raises_on_http_error_status(monkeypatch):
    monkeypatch.setenv("BIZM_USER_ID", "myaccount")
    monkeypatch.setenv("BIZM_PROFILE_KEY", "profile-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: httpx.Response(
            500, request=httpx.Request("POST", url)
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        KakaoBizmProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables=None
        )


def test_bizm_requires_template_code_flag():
    assert KakaoBizmProvider.requires_template_code is True


def test_make_provider_returns_bizm_when_configured(monkeypatch):
    monkeypatch.setenv("NOTIFY_PROVIDER", "bizm")
    assert isinstance(make_provider(), KakaoBizmProvider)


def test_make_provider_bizm_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("NOTIFY_PROVIDER", "BIZM")
    assert isinstance(make_provider(), KakaoBizmProvider)


def test_make_provider_defaults_to_http_without_bizm(monkeypatch):
    monkeypatch.delenv("NOTIFY_PROVIDER", raising=False)
    assert isinstance(make_provider(), HttpNotificationProvider)
