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
        rpa_hold_message="{channel} 주문 {count}건 확인 필요 - 내용을 채워주세요",
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


async def test_neutral_template_code_env_is_honored(monkeypatch):
    # provider 중립 env(NOTIFY_TEMPLATE_CODE_*)도 인식해야 한다(비즈엠 등).
    monkeypatch.delenv("IWINV_TEMPLATE_CODE_SUCCESS", raising=False)
    monkeypatch.setenv("NOTIFY_TEMPLATE_CODE_SUCCESS", "TPL_NEUTRAL")
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.calls[0]["template_code"] == "TPL_NEUTRAL"


async def test_legacy_iwinv_template_code_env_still_works(monkeypatch):
    # 기존 IWINV_TEMPLATE_CODE_* 도 폴백으로 계속 동작해야 한다.
    monkeypatch.delenv("NOTIFY_TEMPLATE_CODE_SUCCESS", raising=False)
    monkeypatch.setenv("IWINV_TEMPLATE_CODE_SUCCESS", "TPL_LEGACY")
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.calls[0]["template_code"] == "TPL_LEGACY"


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
    assert provider.calls[0]["template_code"] is None


async def test_hold_uses_hold_message_not_fail_warning():
    """보류(hold)는 오류가 아니라 '확인 필요' 안내다 — 실패 경고 문구가 가면 안 된다."""
    repo = FakeRepo(_settings())
    provider = FakeProvider()

    result = await send(2, "문자", 1, "hold", repo=repo, provider=provider)

    assert result is True
    to, text = provider.sent[0]
    assert text == "문자 주문 1건 확인 필요 - 내용을 채워주세요"


async def test_unknown_outcome_still_falls_back_to_fail_message():
    """알 수 없는 outcome 은 기존대로 실패 문구로 보수적 폴백."""
    repo = FakeRepo(_settings())
    provider = FakeProvider()

    await send(2, "핸드폰", 1, "weird", repo=repo, provider=provider)

    _, text = provider.sent[0]
    assert text == "[경고] 핸드폰 주문 입력 실패"
