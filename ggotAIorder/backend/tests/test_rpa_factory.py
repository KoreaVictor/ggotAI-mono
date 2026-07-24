from ggotaiorder.rpa.adapters import ManualOnlyAutomator
from ggotaiorder.rpa.factory import build_automator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings
from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator


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


def test_roseweb_builds_roseweb_automator():
    a = build_automator(_s(program_type="roseweb", auto_submit=True), debug_port=9222)
    assert isinstance(a, RoseWebAutomator)
    assert a._auto_submit is True


def test_roseweb_auto_submit_defaults_to_fill_only():
    """검증 전에는 채우기만 — FlowerNT 도입 때와 같은 관례."""
    a = build_automator(_s(program_type="roseweb", auto_submit=False), debug_port=9222)
    assert a._auto_submit is False


def test_factory_does_not_import_uiautomation_at_module_level():
    """factory 는 모든 가게가 기동 때 import 한다.

    여기서 uiautomation(Windows 전용 · [roseweb] extra)이 딸려 오면 FlowerNT 전용
    설치본과 리눅스 CI 에서 수집엔진이 아예 못 뜬다. 어댑터가 호출 시점에 import 하는지는
    test_rpa_roseweb_automator 가 따로 지킨다.
    """
    import ast
    from pathlib import Path

    from ggotaiorder.rpa import factory

    tree = ast.parse(Path(factory.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(m.split(".")[0] == "uiautomation" for m in imported), imported


def test_unknown_type_is_manual_only():
    a = build_automator(_s(program_type="etc"), debug_port=9222)
    assert isinstance(a, ManualOnlyAutomator)
