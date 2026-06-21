from ggotaiorder.rpa.adapters import ManualOnlyAutomator, RoseWebAutomator
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings


def _s(**kw):
    base = dict(program_type="flowernt", url="https://www.flowernt.com",
                login_id="id", login_password="pw", enabled=True, auto_submit=True)
    base.update(kw)
    return RpaProgramSettings(**base)


def test_none_settings_is_manual_only():
    a = build_automator(None, debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)
    assert a.is_program_running() is False


def test_disabled_is_manual_only():
    a = build_automator(_s(enabled=False), debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)


def test_flowernt_builds_flowernt_automator():
    a = build_automator(_s(program_type="flowernt"), debug_port=9222)
    assert isinstance(a, FlowerNt3Automator)


def test_roseweb_is_stub_manual():
    a = build_automator(_s(program_type="roseweb"), debug_port=9222)
    assert isinstance(a, RoseWebAutomator)
    assert a.is_program_running() is False


def test_unknown_type_is_manual_only():
    a = build_automator(_s(program_type="etc"), debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)
