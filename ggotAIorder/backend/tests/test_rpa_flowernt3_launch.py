"""FlowerNt3Automator 가 RPA 전용 Chrome 을 직접 기동하는지 검증.

꽃집 사장님은 브라우저/로그인을 직접 못 하므로, 백엔드가 CDP 가 죽어 있으면
Chrome 을 띄우고(프로필+디버그포트) CDP 가 응답할 때까지 대기해야 한다.
실제 Chrome 을 띄우지 않도록 _cdp_alive/subprocess.Popen 을 모킹한다.
"""

from __future__ import annotations

from pathlib import Path

from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator


def _automator(tmp_path, chrome_exists=True, url="https://www.flowernt.com"):
    chrome = tmp_path / "chrome.exe"
    if chrome_exists:
        chrome.write_text("stub")
    return FlowerNt3Automator(
        url=url,
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
    # 웹기동 시 rpa_program_url(랜딩 URL)로 연다
    assert "https://www.flowernt.com" in launched["args"]


def test_launch_opens_program_url(tmp_path, monkeypatch):
    landing = "https://www.flowernt.com/main.asp?checkintro=Y"
    a = _automator(tmp_path, url=landing)
    states = iter([False, True])
    monkeypatch.setattr(a, "_cdp_alive", lambda: next(states))
    launched = {"args": None}
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda args, *x, **k: launched.__setitem__("args", args),
    )
    monkeypatch.setattr("time.sleep", lambda *_: None)
    a._ensure_browser_running()
    assert landing in launched["args"]  # DB의 rpa_program_url 그대로 기동


def test_order_url_uses_origin_not_landing_path(tmp_path):
    # rpa_program_url 에 경로·쿼리가 있어도 주문폼 URL은 origin 기준으로 만든다
    a = _automator(tmp_path, url="https://www.flowernt.com/main.asp?checkintro=Y")
    assert a._order_url() == "https://www.flowernt.com/order/order3.asp"


def test_order_url_with_plain_domain(tmp_path):
    a = _automator(tmp_path, url="https://www.flowernt.com")
    assert a._order_url() == "https://www.flowernt.com/order/order3.asp"


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


class _FakePage:
    def __init__(self, url):
        self.url = url


class _FakeCtx:
    def __init__(self, pages):
        self.pages = pages
        self.new_page_called = False

    def new_page(self):
        self.new_page_called = True
        return _FakePage("about:blank#new")


def test_active_page_prefers_flowernt_page(tmp_path):
    a = _automator(tmp_path)
    blank = _FakePage("")
    good = _FakePage("https://www.flowernt.com/main.asp")
    ctx = _FakeCtx([blank, good])
    # 빈/detached 페이지(pages[0])를 피하고 flowernt 페이지를 고른다
    assert a._active_page(ctx) is good
    assert ctx.new_page_called is False


def test_active_page_opens_new_when_no_flowernt(tmp_path):
    a = _automator(tmp_path)
    ctx = _FakeCtx([_FakePage(""), _FakePage("about:blank")])
    # 정상 flowernt 페이지가 없으면(빈/detached뿐) 새 페이지를 연다
    page = a._active_page(ctx)
    assert ctx.new_page_called is True
    assert page is not None


def test_active_page_skips_page_whose_url_raises(tmp_path):
    class _Detached:
        @property
        def url(self):
            raise RuntimeError("Frame has been detached")

    a = _automator(tmp_path)
    good = _FakePage("https://www.flowernt.com/order/order3.asp")
    ctx = _FakeCtx([_Detached(), good])
    assert a._active_page(ctx) is good
