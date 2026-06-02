import pytest

from ggotaiorder.config import Config, load_config, ConfigError

VALID = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
    "AES_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # 64 hex -> 32 bytes
}


def test_load_config_returns_values():
    cfg = load_config(env=VALID)
    assert isinstance(cfg, Config)
    assert cfg.supabase_url == "https://example.supabase.co"
    assert cfg.supabase_service_role_key == "service-key"
    assert cfg.aes_encryption_key == VALID["AES_ENCRYPTION_KEY"]


def test_missing_key_raises():
    broken = dict(VALID)
    del broken["SUPABASE_URL"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_empty_key_raises():
    broken = dict(VALID, SUPABASE_ANON_KEY="")
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_aes_key_must_be_32_bytes():
    broken = dict(VALID, AES_ENCRYPTION_KEY="0123456789abcdef")
    with pytest.raises(ConfigError):
        load_config(env=broken)
