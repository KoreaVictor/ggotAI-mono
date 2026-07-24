"""관리 프로그램 종류 해석(캐시 폴백) — 로그온 시 부수 프로세스 기동 판단용."""

import pytest

from ggotaiorder.rpa.program_type import UNKNOWN, resolve_program_type
from ggotaiorder.rpa.program_settings import RpaProgramSettings


def _settings(**kw):
    base = dict(program_type="flowernt", url=None, login_id=None,
                login_password=None, enabled=True, auto_submit=False)
    base.update(kw)
    return RpaProgramSettings(**base)


def test_lookup_success_returns_type_and_writes_cache(tmp_path):
    cache = tmp_path / "program_type"

    got = resolve_program_type(lookup=lambda: _settings(), cache_path=cache)

    assert got == "flowernt"
    assert cache.read_text(encoding="utf-8").strip() == "flowernt"


def test_disabled_rpa_resolves_to_none(tmp_path):
    """RPA를 꺼둔 가게는 관리 프로그램 부수 프로세스도 필요 없다."""
    cache = tmp_path / "program_type"

    got = resolve_program_type(lookup=lambda: _settings(enabled=False), cache_path=cache)

    assert got == "none"
    assert cache.read_text(encoding="utf-8").strip() == "none"


def test_no_settings_row_resolves_to_none(tmp_path):
    got = resolve_program_type(lookup=lambda: None, cache_path=tmp_path / "program_type")
    assert got == "none"


def test_lookup_failure_falls_back_to_cache(tmp_path):
    """로그온 직후엔 DNS·네트워크가 아직 안 올라와 조회가 실패한다 — 마지막 값을 쓴다."""
    cache = tmp_path / "program_type"
    cache.write_text("roseweb", encoding="utf-8")

    def boom():
        raise OSError("getaddrinfo failed")

    assert resolve_program_type(lookup=boom, cache_path=cache) == "roseweb"


def test_cache_with_bom_is_read_cleanly(tmp_path):
    """메모장·PowerShell 로 캐시를 저장하면 BOM이 붙는다.

    BOM이 남으면 호출자의 문자열 비교('flowernt')가 어긋나, FlowerNT 가게인데
    전용 Chrome을 안 띄우게 된다.
    """
    cache = tmp_path / "program_type"
    cache.write_bytes("﻿flowernt".encode("utf-8"))

    def boom():
        raise OSError("getaddrinfo failed")

    assert resolve_program_type(lookup=boom, cache_path=cache) == "flowernt"


def test_lookup_failure_without_cache_is_unknown(tmp_path):
    """캐시조차 없으면 모른다고 답한다 — 호출자가 안전한 쪽(기존 동작 유지)을 고르게."""

    def boom():
        raise OSError("getaddrinfo failed")

    assert resolve_program_type(lookup=boom, cache_path=tmp_path / "nope") == UNKNOWN


def test_cache_write_failure_does_not_break_resolution(tmp_path):
    """캐시는 부가기능 — 못 써도 조회 결과는 그대로 돌려준다."""
    unwritable = tmp_path / "missing_dir" / "program_type"

    assert resolve_program_type(lookup=lambda: _settings(), cache_path=unwritable) == "flowernt"


@pytest.mark.parametrize("raw,expected", [("  flowernt  ", "flowernt"), ("", "none")])
def test_program_type_is_normalized(tmp_path, raw, expected):
    got = resolve_program_type(
        lookup=lambda: _settings(program_type=raw), cache_path=tmp_path / "program_type"
    )
    assert got == expected
