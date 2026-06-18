from pathlib import Path

import pytest

from ggotaiorder.config import Config, load_config, ConfigError

VALID = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
    "AES_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # 64 hex -> 32 bytes
    "GEMINI_API_KEY": "test-gemini-key",
    "SHOP_KEY": "19",
}


def test_load_config_returns_values():
    cfg = load_config(env=VALID)
    assert isinstance(cfg, Config)
    assert cfg.supabase_url == "https://example.supabase.co"
    assert cfg.supabase_service_role_key == "service-key"
    assert cfg.aes_encryption_key == VALID["AES_ENCRYPTION_KEY"]
    assert cfg.gemini_api_key == "test-gemini-key"


def test_missing_key_raises():
    broken = dict(VALID)
    del broken["SUPABASE_URL"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_missing_gemini_key_raises():
    broken = dict(VALID)
    del broken["GEMINI_API_KEY"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_empty_key_raises():
    broken = dict(VALID, SUPABASE_ANON_KEY="")
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_aes_key_must_be_32_bytes():
    broken = dict(VALID, AES_ENCRYPTION_KEY="0123456789abcdef")  # valid hex, 8 bytes
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_shop_key_parsed_as_int():
    cfg = load_config(env=VALID)
    assert cfg.shop_key == 19
    assert isinstance(cfg.shop_key, int)


def test_missing_shop_key_raises():
    broken = dict(VALID)
    del broken["SHOP_KEY"]
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_non_integer_shop_key_raises():
    broken = dict(VALID, SHOP_KEY="abc")
    with pytest.raises(ConfigError):
        load_config(env=broken)


def test_rpa_backup_dir_default():
    cfg = load_config(env=VALID)
    assert isinstance(cfg.rpa_backup_dir, Path)
    assert cfg.rpa_backup_dir.name == "backups"


def test_rpa_backup_dir_override():
    cfg = load_config(env=dict(VALID, RPA_BACKUP_DIR="/tmp/custom-backups"))
    assert str(cfg.rpa_backup_dir).endswith("custom-backups")


def test_rpa_profile_dir_and_debug_port_defaults():
    cfg = load_config(env=VALID)
    assert isinstance(cfg.rpa_profile_dir, Path)
    assert cfg.flowernt_debug_port == 9222


def test_rpa_profile_dir_and_port_from_env():
    cfg = load_config(env=dict(VALID, RPA_PROFILE_DIR=r"C:\tmp\prof", RPA_DEBUG_PORT="9333"))
    assert str(cfg.rpa_profile_dir).endswith("prof")
    assert cfg.flowernt_debug_port == 9333


def test_non_integer_debug_port_raises():
    with pytest.raises(ConfigError):
        load_config(env=dict(VALID, RPA_DEBUG_PORT="abc"))
