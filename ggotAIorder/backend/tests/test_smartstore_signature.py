import base64

import pytest

from ggotaiorder.mall.models import MallCredential
from ggotaiorder.mall.smartstore_client import HttpSmartStoreClient

# 유효한 bcrypt salt(네이버 client_secret 은 이 형식). 결정성 검증용 고정값.
_SALT = "$2b$12$R9h/cIPz0gi.URNNX3kh2O"


def test_signature_is_deterministic_for_fixed_inputs():
    c = HttpSmartStoreClient()
    s1 = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    s2 = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    assert s1 == s2


def test_signature_is_base64():
    c = HttpSmartStoreClient()
    sig = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    # base64 디코딩이 예외 없이 되어야 한다(bcrypt 해시의 base64 인코딩).
    assert base64.b64decode(sig)
    assert isinstance(sig, str)


def test_signature_changes_with_timestamp():
    c = HttpSmartStoreClient()
    a = c._make_signature("client-abc", _SALT, 1_700_000_000_000)
    b = c._make_signature("client-abc", _SALT, 1_700_000_000_001)
    assert a != b


def test_fetch_and_confirm_are_stubbed():
    c = HttpSmartStoreClient()
    cred = MallCredential(
        shop_key=1, shop_name="꽃집", provider="smartstore",
        client_id="cid", enc_client_secret="enc", extra={},
    )
    with pytest.raises(NotImplementedError):
        c.fetch_new_orders(cred)
    with pytest.raises(NotImplementedError):
        c.confirm_order(cred, "PO1")
