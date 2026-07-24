"""RoseWebAutomator 실행·감지. uiautomation 없이 도는 단위테스트(리눅스 CI 포함).

실제 창 탐색(_main_window)만 가짜로 바꾸면 나머지 판단 로직은 그대로 검증된다.
"""

import subprocess

from ggotaiorder.rpa.roseweb import layout
from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator


class _Win:
    Name = "화원박사 ROSEWeb Network build(208.5.1) (관리자)"


def _automator(**kw):
    return RoseWebAutomator(**kw)


def _stub(a, *, windows, process_running=False, popen=None, monkeypatch=None):
    """windows = _main_window 가 호출될 때마다 돌려줄 값들(순서대로)."""
    seq = list(windows)

    def fake_main_window():
        return seq.pop(0) if seq else None

    monkeypatch.setattr(a, "_main_window", fake_main_window)
    monkeypatch.setattr(a, "_process_running", lambda: process_running)
    if popen is not None:
        monkeypatch.setattr(subprocess, "Popen", popen)


def test_importing_automator_does_not_need_uiautomation():
    """uiautomation 은 Windows 전용 + [roseweb] extra 다.

    모듈 최상단에서 import 하면 리눅스 CI 와 FlowerNT 전용 설치본에서 이 모듈을
    건드리는 순간 죽는다(factory 가 import 하므로 결국 수집엔진 기동 실패).
    함수 안에서의 지연 import 는 허용 — 그게 이 모듈의 규칙이다.
    """
    import ast
    from pathlib import Path

    from ggotaiorder.rpa.roseweb import automator

    tree = ast.parse(Path(automator.__file__).read_text(encoding="utf-8"))
    top_level = []
    for node in tree.body:                      # tree.body = 모듈 최상단만
        if isinstance(node, ast.Import):
            top_level += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            top_level.append(node.module or "")

    assert not any(m.split(".")[0] == "uiautomation" for m in top_level), top_level


def test_auto_submit_is_kept():
    assert _automator(auto_submit=True)._auto_submit is True
    assert _automator(auto_submit=False)._auto_submit is False
    assert _automator()._auto_submit is False   # 기본은 채우기만


def test_running_when_main_window_present(monkeypatch):
    a = _automator()
    calls = []
    _stub(a, windows=[_Win()], popen=lambda *x, **k: calls.append(x), monkeypatch=monkeypatch)

    assert a.is_program_running() is True
    assert calls == []          # 이미 떠 있으면 실행하지 않는다


def test_launches_when_not_running(monkeypatch):
    a = _automator()
    calls = []

    def fake_popen(args, cwd=None, **kw):
        calls.append((args, cwd))

    _stub(a, windows=[None, _Win()], process_running=False,
          popen=fake_popen, monkeypatch=monkeypatch)

    assert a._ensure_running(timeout_s=2.0, poll_s=0.01) is True
    assert calls == [([layout.EXE_PATH], layout.WORKDIR)]


def test_does_not_launch_twice_when_process_already_up(monkeypatch):
    """스플래시 등으로 창이 아직 없을 뿐인데 또 띄우면 인스턴스가 둘이 된다."""
    a = _automator()
    calls = []
    _stub(a, windows=[None, None, _Win()], process_running=True,
          popen=lambda *x, **k: calls.append(x), monkeypatch=monkeypatch)

    assert a._ensure_running(timeout_s=2.0, poll_s=0.01) is True
    assert calls == []


def test_returns_false_when_window_never_appears(monkeypatch):
    a = _automator()
    _stub(a, windows=[], process_running=True,
          popen=lambda *x, **k: None, monkeypatch=monkeypatch)

    assert a._ensure_running(timeout_s=0.05, poll_s=0.01) is False


def test_is_program_running_swallows_errors(monkeypatch):
    """구동 확인이 터져도 예외를 밖으로 던지지 않는다(백업 경로로 흘러야 한다)."""
    a = _automator()

    def boom():
        raise OSError("UIA 실패")

    monkeypatch.setattr(a, "_ensure_running", boom)
    assert a.is_program_running() is False


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout


def test_process_running_reads_korean_tasklist_output(monkeypatch):
    """한국어 Windows 의 tasklist 는 CP949 로 출력한다.

    text=True 로 받으면 UTF-8 디코딩이 터져 결과가 늘 비고, 그러면 '안 떠 있음'으로
    오판해 이미 떠 있는 RoseWeb 을 또 실행한다(인스턴스 2개). 실측에서 잡힌 결함.
    """
    real_output = "roseweb.exe   1234 Console   1   123,456 K\n".encode("cp949")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(real_output))

    assert _automator()._process_running() is True


def test_process_running_false_when_absent(monkeypatch):
    empty = "정보: 지정된 조건에 맞는 작업을 실행하고 있지 않습니다.\n".encode("cp949")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(empty))

    assert _automator()._process_running() is False


def test_process_running_false_when_check_errors(monkeypatch):
    def boom(*a, **k):
        raise OSError("tasklist 없음")

    monkeypatch.setattr(subprocess, "run", boom)
    assert _automator()._process_running() is False


def test_input_order_not_implemented_yet():
    import pytest
    with pytest.raises(NotImplementedError):
        _automator().input_order(object())
