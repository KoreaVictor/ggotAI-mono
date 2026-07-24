"""재로그인이 '느린 화면'에서도 성공해야 한다.

라이브(2026-07-21~22) 세 번의 실패가 전부 **몇 시간 쉰 뒤 첫 주문**에서 났다.
그 상태에서는 Chrome 이 백그라운드 탭을 얼리거나 연결이 식어 화면이 평소보다 늦게 뜬다.
기존 코드는 goto 후 **고정 0.5초**만 기다리고 로그인 칸을 딱 한 번 훑은 뒤,
못 찾으면 로그인을 시도조차 하지 않고 실패로 처리했다.

따뜻한 상태에서는 8번 시도해도 재현되지 않았다(0.5초면 늘 충분했다).
그래서 '얼마나 기다리면 되는가'로 풀지 않고, **조건이 만족될 때까지 기다리도록** 바꾼다.
"""

from __future__ import annotations

from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator

LOGIN_URL = "https://www.flowernt.com/member/login.asp"
MAIN_URL = "https://www.flowernt.com/main.asp"


def _automator(tmp_path):
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("stub")
    return FlowerNt3Automator(
        url="https://www.flowernt.com/main.asp?checkintro=Y",
        login_id="hable", login_password="pw", auto_submit=True,
        debug_port=9222, profile_dir=str(tmp_path / "profile"),
        chrome_path=str(chrome),
    )


class _Element:
    def __init__(self):
        self.filled = None
        self.pressed = None

    def fill(self, value):
        self.filled = value

    def press(self, key):
        self.pressed = key


class _SlowLoginFrame:
    """로그인 칸이 `appear_after` 번째 대기 뒤에야 DOM 에 생기는 프레임."""

    def __init__(self, page, appear_after):
        self.name = "flowernt3Main"
        self.url = LOGIN_URL
        self._page = page
        self._appear_after = appear_after
        self.id_el = _Element()
        self.pw_el = _Element()

    def query_selector(self, selector):
        if self._page.waits < self._appear_after:
            return None
        if selector == "input[name=ms_id]":
            return self.id_el
        if selector == "input[name=ms_pass]":
            return self.pw_el
        return None


class _SlowPage:
    """대기 횟수를 세는 가짜 페이지.

    `login_applies_after` 번째 대기가 지나면 로그인이 반영돼 프레임 URL 이 main 으로 바뀐다.
    """

    def __init__(self, appear_after=0, login_applies_after=0):
        self.url = MAIN_URL
        self.waits = 0
        self._login_applies_after = login_applies_after
        self._frame = _SlowLoginFrame(self, appear_after)
        self.goto_calls = 0

    @property
    def frames(self):
        if self._frame.pw_el.pressed and self.waits >= self._login_applies_after:
            self._frame.url = MAIN_URL
        return [self._frame]

    def goto(self, url, **kwargs):
        self.goto_calls += 1

    def wait_for_timeout(self, ms):
        self.waits += 1

    def wait_for_load_state(self, state):
        pass


def test_login_succeeds_when_form_appears_late(tmp_path):
    """로그인 칸이 늦게 떠도 기다렸다가 채워 넣어야 한다.

    기존 코드는 0.5초 뒤 한 번만 훑어 이 경우 로그인을 시도조차 못 했다.
    """
    a = _automator(tmp_path)
    page = _SlowPage(appear_after=5, login_applies_after=6)

    assert a._try_login(page) is True
    assert page._frame.id_el.filled == "hable"
    assert page._frame.pw_el.filled == "pw"
    assert page._frame.pw_el.pressed == "Enter"


def test_login_waits_for_effect_to_land(tmp_path):
    """엔터 직후엔 아직 로그인 화면이다 — 반영될 때까지 기다려야 한다.

    기존 코드는 고정 0.8초 뒤 한 번 보고 판정해, 늦게 반영되면 실패로 처리했다.
    """
    a = _automator(tmp_path)
    page = _SlowPage(appear_after=0, login_applies_after=8)

    assert a._try_login(page) is True


def test_login_gives_up_when_form_never_appears(tmp_path, caplog):
    """영영 안 뜨면 무한정 기다리지 않고 포기하되, 이유를 로그로 남긴다.

    지금까지 이 경우가 아무 흔적 없이 False 만 남겨 원인 추적이 불가능했다.
    """
    a = _automator(tmp_path)
    page = _SlowPage(appear_after=10_000, login_applies_after=0)

    with caplog.at_level("WARNING"):
        assert a._try_login(page) is False

    assert any("로그인 칸" in r.message or "로그인 칸" in r.getMessage() for r in caplog.records)


def test_login_logs_exception_detail(tmp_path, caplog):
    """예외를 삼키더라도 내용은 남겨야 한다 — 지금은 이유 없이 경고만 찍힌다."""
    a = _automator(tmp_path)

    class _Boom:
        url = MAIN_URL
        frames: list = []

        def goto(self, url, **kwargs):
            raise RuntimeError("연결 끊김")

        def wait_for_timeout(self, ms):
            pass

    with caplog.at_level("WARNING"):
        assert a._try_login(_Boom()) is False

    assert any("연결 끊김" in r.getMessage() for r in caplog.records)
