from ggotaiorder.notifier.repository import NotificationSettings
from ggotaiorder.notifier.sms_sender import render_template, send


class FakeRepo:
    def __init__(self, settings):
        self._settings = settings

    def get_settings(self, shop_key):
        self.last_shop_key = shop_key
        return self._settings


class FakeProvider:
    requires_template_code = False

    def __init__(self, raises=False, requires_template_code=False):
        self.sent = []
        self.calls = []
        self._raises = raises
        self.requires_template_code = requires_template_code

    def send_message(self, to, text, *, template_code=None, variables=None):
        if self._raises:
            raise RuntimeError("provider down")
        self.sent.append((to, text))
        self.calls.append(
            {"to": to, "text": text, "template_code": template_code, "variables": variables}
        )


def _settings(**kw):
    base = dict(
        use_notification="Y",
        notification_phone_number="010-1111-2222",
        rpa_success_message="{channel} 주문 {count}건 입력 완료",
        rpa_manual_message="{channel} 주문 {count}건 접수 - 수동입력 필요",
        rpa_fail_message="[경고] {channel} 주문 입력 실패",
        fallback_mobile="010-9999-0000",
    )
    base.update(kw)
    return NotificationSettings(**base)


def test_render_template_substitutes():
    assert render_template("{channel} {count}건", "인터라넷", 3) == "인터라넷 3건"


async def test_disabled_skips_and_returns_false():
    repo = FakeRepo(_settings(use_notification="N"))
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "success", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


async def test_success_sends_to_notification_number():
    repo = FakeRepo(_settings())
    provider = FakeProvider()
    result = await send(2, "가게전화", 4, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.sent == [("010-1111-2222", "가게전화 주문 4건 입력 완료")]


async def test_manual_uses_manual_template():
    repo = FakeRepo(_settings())
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "manual", repo=repo, provider=provider)
    assert result is True
    assert provider.sent == [("010-1111-2222", "핸드폰 주문 1건 접수 - 수동입력 필요")]


async def test_fallback_to_mobile_when_no_notification_number():
    repo = FakeRepo(_settings(notification_phone_number=None))
    provider = FakeProvider()
    result = await send(2, "쇼핑몰", 2, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.sent[0][0] == "010-9999-0000"


async def test_failure_uses_fail_template():
    repo = FakeRepo(_settings())
    provider = FakeProvider()
    result = await send(2, "인터라넷", 1, "fail", repo=repo, provider=provider)
    assert result is True
    assert provider.sent == [("010-1111-2222", "[경고] 인터라넷 주문 입력 실패")]


async def test_no_recipient_returns_false():
    repo = FakeRepo(_settings(notification_phone_number=None, fallback_mobile=None))
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "success", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


async def test_settings_none_returns_false():
    repo = FakeRepo(None)
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "success", repo=repo, provider=provider)
    assert result is False


async def test_provider_exception_returns_false():
    repo = FakeRepo(_settings())
    provider = FakeProvider(raises=True)
    result = await send(2, "핸드폰", 1, "success", repo=repo, provider=provider)
    assert result is False


async def test_empty_manual_template_skips_and_returns_false():
    repo = FakeRepo(_settings(rpa_manual_message=""))
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "manual", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


async def test_empty_template_skips_and_returns_false():
    repo = FakeRepo(_settings(rpa_success_message="", rpa_fail_message=""))
    provider = FakeProvider()
    result = await send(2, "핸드폰", 1, "success", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


def test_mask_exposes_last_4_digits_only():
    from ggotaiorder.notifier.sms_sender import _mask
    assert _mask("010-1234-5678") == "***5678"
    assert _mask("ab") == "***"


async def test_success_passes_template_code_and_variables(monkeypatch):
    monkeypatch.setenv("IWINV_TEMPLATE_CODE_SUCCESS", "TPL_SUCCESS")
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.calls[0]["template_code"] == "TPL_SUCCESS"
    assert provider.calls[0]["variables"] == {"건수": "1"}


async def test_template_provider_skips_when_code_missing(monkeypatch):
    monkeypatch.delenv("IWINV_TEMPLATE_CODE_FAIL", raising=False)
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "fail", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


async def test_freetext_provider_ignores_missing_template_code(monkeypatch):
    monkeypatch.delenv("IWINV_TEMPLATE_CODE_SUCCESS", raising=False)
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=False)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.sent == [("010-1111-2222", "가게전화 주문 1건 입력 완료")]
