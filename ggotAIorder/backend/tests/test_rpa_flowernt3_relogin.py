"""세션 만료 자가복구: input_order 가 order3 로 이동했을 때 login.asp 로 튕기면
(세션 만료) 재로그인 후 1회 재시도하고, 그래도 실패면 예외를 던지는지 검증한다.

라이브 원인(2026-07-06): 세션 만료 시 order/order3.asp 요청이 member/login.asp 로
리다이렉트되고 그 페이지엔 submit_reg 가 없어 'submit_reg() 미발견' 으로 등록 실패.
실제 브라우저 없이 fake page/frame 으로 프레임 이동·재로그인 흐름만 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ggotaiorder.rpa.flowernt3.automator import CONTENT_FRAME_NAME, FlowerNt3Automator

ORDER_URL = "https://www.flowernt.com/order/order3.asp"
LOGIN_URL = "https://www.flowernt.com/member/login.asp"
MAIN_URL = "https://www.flowernt.com/main/main.asp"


def _automator(tmp_path, url="https://www.flowernt.com"):
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("stub")
    return FlowerNt3Automator(
        url=url, login_id="hable", login_password="pw", auto_submit=True,
        debug_port=9222, profile_dir=str(tmp_path / "profile"),
        chrome_path=str(chrome),
    )


class _FakeContentFrame:
    """order3 로 goto 하면 세션 상태에 따라 order3(로그인됨) 또는 login.asp(만료)로 착지."""

    def __init__(self, session):
        self.name = CONTENT_FRAME_NAME
        self.session = session
        self.url = MAIN_URL
        self.goto_calls = 0

    def goto(self, url, **kwargs):
        self.goto_calls += 1
        self.url = url if self.session["logged_in"] else LOGIN_URL


class _FakePage:
    def __init__(self, content):
        self._content = content
        self.main_frame = content

    @property
    def frames(self):
        return [self._content]

    def goto(self, url, **kwargs):  # main.asp 재로드용(콘텐츠 프레임 존재 시 미사용)
        pass

    def wait_for_timeout(self, ms):
        pass


class _FakeFramesetPage:
    """하드 로그아웃 재현: 로그인 전엔 프레임셋 없음(flowernt3Main 미생성),
    로그인 후 콘텐츠 프레임이 등장한다."""

    def __init__(self, session):
        self.session = session
        self._content = _FakeContentFrame(session)
        self.main_frame = self._content

    @property
    def frames(self):
        return [self._content] if self.session["logged_in"] else []

    def goto(self, url, **kwargs):
        pass

    def wait_for_timeout(self, ms):
        pass


def test_open_order_form_returns_frame_when_session_valid(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    session = {"logged_in": True}
    content = _FakeContentFrame(session)
    page = _FakePage(content)
    login_called = {"n": 0}
    monkeypatch.setattr(a, "_try_login", lambda pg: login_called.__setitem__("n", login_called["n"] + 1) or True)

    frame = a._open_order_form(page)

    assert ORDER_URL in frame.url
    assert login_called["n"] == 0  # 이미 로그인이면 재로그인 안 함
    assert content.goto_calls == 1


def test_open_order_form_relogins_when_redirected_to_login(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    session = {"logged_in": False}  # 세션 만료 상태로 시작
    content = _FakeContentFrame(session)
    page = _FakePage(content)

    def fake_login(pg):
        session["logged_in"] = True  # 재로그인 성공
        return True

    monkeypatch.setattr(a, "_try_login", fake_login)

    frame = a._open_order_form(page)

    assert ORDER_URL in frame.url          # 재로그인 후 order3 정상 착지
    assert content.goto_calls == 2         # 최초 시도 + 재로그인 후 1회 재시도


def test_open_order_form_relogins_when_no_frameset(tmp_path, monkeypatch):
    # 하드 로그아웃: main.asp가 프레임셋을 안 만들어 flowernt3Main 부재 → 재로그인 후 복구
    a = _automator(tmp_path)
    session = {"logged_in": False}
    page = _FakeFramesetPage(session)

    def fake_login(pg):
        session["logged_in"] = True
        return True

    monkeypatch.setattr(a, "_try_login", fake_login)

    frame = a._open_order_form(page)

    assert ORDER_URL in frame.url


def test_open_order_form_raises_when_relogin_fails(tmp_path, monkeypatch):
    a = _automator(tmp_path)
    session = {"logged_in": False}
    content = _FakeContentFrame(session)
    page = _FakePage(content)
    monkeypatch.setattr(a, "_try_login", lambda pg: False)  # 재로그인 실패

    with pytest.raises(RuntimeError, match="세션"):
        a._open_order_form(page)
