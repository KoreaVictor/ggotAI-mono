from ggotaiorder.core.crypto import encrypt
from ggotaiorder.rpa.program_settings import RpaProgramSettings, parse_settings_row

KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_parse_full_row_decrypts_password():
    row = {
        "rpa_program_type": "flowernt",
        "rpa_program_url": "https://www.flowernt.com",
        "rpa_login_id": "shop01",
        "rpa_login_password": encrypt("pw123!", KEY),
        "rpa_enabled": "Y",
        "rpa_auto_submit": "Y",
    }
    s = parse_settings_row(row, KEY)
    assert s == RpaProgramSettings(
        program_type="flowernt", url="https://www.flowernt.com",
        login_id="shop01", login_password="pw123!",
        enabled=True, auto_submit=True,
    )


def test_parse_disabled_and_no_password():
    row = {
        "rpa_program_type": "", "rpa_program_url": None, "rpa_login_id": None,
        "rpa_login_password": None, "rpa_enabled": "N", "rpa_auto_submit": "N",
    }
    s = parse_settings_row(row, KEY)
    assert s.enabled is False
    assert s.auto_submit is False
    assert s.login_password is None


def test_parse_none_row():
    assert parse_settings_row(None, KEY) is None


def test_parse_bad_password_is_none_not_crash():
    row = {"rpa_program_type": "flowernt", "rpa_enabled": "Y",
           "rpa_login_password": "not-a-valid-blob"}
    s = parse_settings_row(row, KEY)
    assert s.login_password is None  # 복호 실패는 조용히 None
