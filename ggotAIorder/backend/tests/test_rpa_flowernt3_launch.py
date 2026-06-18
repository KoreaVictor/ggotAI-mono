"""FlowerNt3Automator 가 RPA 전용 Chrome 을 직접 기동하는지 검증.

꽃집 사장님은 브라우저/로그인을 직접 못 하므로, 백엔드가 CDP 가 죽어 있으면
Chrome 을 띄우고(프로필+디버그포트) CDP 가 응답할 때까지 대기해야 한다.
실제 Chrome 을 띄우지 않도록 _cdp_alive/subprocess.Popen 을 모킹한다.
"""

from __future__ import annotations

from pathlib import Path

from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator


def _automator(tmp_path, chrome_exists=True):
    chrome = tmp_path / "chrome.exe"
    if chrome_exists:
        chrome.write_text("stub")
    return FlowerNt3Automator(
        url="https://www.flowernt.com",
        login_id="hable",
        login_password="pw",
        auto_submit=False,
        debug_port=9222,
        profile_dir=str(tmp_path / "profile"),
        chrome_path=str(chrome),
    )


def test_ensure_skips_launch_when_cdp_alive(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    monkeypatch.setattr(a, "_cdp_alive", lambda: True)
    called = {"popen": False}
    monkeypatch.setattr(
        "subprocess.Popen", lambda *x, **k: called.__setitem__("popen", True)
    )
    assert a._ensure_browser_running() is True
    assert called["popen"] is False  # 이미 떠 있으면 새로 띄우지 않는다


def test_ensure_launches_when_cdp_down(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    states = iter([False, False, True])  # 첫 체크 죽음 → 기동 → 폴링 시 살아남
    monkeypatch.setattr(a, "_cdp_alive", lambda: next(states))
    launched = {"args": None}

    def fake_popen(args, *x, **k):
        launched["args"] = args
        return object()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert a._ensure_browser_running() is True
    assert launched["args"] is not None
    joined = " ".join(launched["args"])
    assert "--remote-debugging-port=9222" in joined
    assert "profile" in joined  # user-data-dir 에 프로필 경로 포함


def test_ensure_false_when_chrome_missing(tmp_path, monkeypatch):
    a = _automator(tmp_path, chrome_exists=False)
    monkeypatch.setattr(a, "_cdp_alive", lambda: False)
    called = {"popen": False}
    monkeypatch.setattr(
        "subprocess.Popen", lambda *x, **k: called.__setitem__("popen", True)
    )
    assert a._ensure_browser_running() is False
    assert called["popen"] is False  # 실행파일 없으면 시도조차 안 한다


def test_is_program_running_false_when_launch_fails(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    monkeypatch.setattr(a, "_ensure_browser_running", lambda: False)
    # 기동 실패 시 CDP 연결 시도 없이 즉시 False(→ 백업/수동)
    assert a.is_program_running() is False
