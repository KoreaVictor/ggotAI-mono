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
    # 실제 UIA 로 새어나가지 않게 막는다(테스트가 이 PC 의 창 상태에 좌우되면 안 된다).
    monkeypatch.setattr(a, "_find_window", lambda cls: None)
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


########################################################################
# input_order (Task 5)
########################################################################

import pytest  # noqa: E402

from ggotaiorder.rpa.models import RpaOrder  # noqa: E402
from ggotaiorder.rpa.roseweb import layout  # noqa: E402


class _Rect:
    def __init__(self, left, top, width, height):
        self.left, self.top = left, top
        self.right, self.bottom = left + width, top + height


class _Cell:
    def __init__(self, key, left, top):
        self.key = key
        self.BoundingRectangle = _Rect(left, top, 100, 25)
        self.focused = False

    def GetParentControl(self):
        return None

    def SetFocus(self):
        self.focused = True


class _Form:
    """실측 좌표대로 칸이 놓인 가짜 주문폼."""

    ORIGIN = (421, 113)

    def __init__(self, *, size=layout.FORM_SIZE, drop=()):
        w, h = size
        self.BoundingRectangle = _Rect(*self.ORIGIN, w, h)
        ox, oy = self.ORIGIN
        self.cells = [
            _Cell(k, ox + dx, oy + dy)
            for k, (dx, dy) in layout.FIELD_POSITIONS.items()
            if k not in drop
        ]


def _order(**kw):
    base = dict(order_detail_id=1, shop_key=19, shop_name="꽃집", channel="쇼핑몰",
                customer_name="김발주", customer_phone_number="01011112222",
                product_name="장미꽃다발", quantity=1, price=55000,
                delivery_at="2026-07-25T14:30:00", delivery_place="서울 강남구 논현로 1",
                receiver_name="이받는", receiver_phone_number="01033334444",
                ribbon_sender="김발주", ribbon_congratulations="축 개업",
                card_message="번창하세요")
    base.update(kw)
    return RpaOrder(**base)


def _wired(monkeypatch, form, *, auto_submit=False):
    """UIA 를 건드리는 지점만 가짜로 바꾼 automator + 타이핑 기록."""
    a = _automator(auto_submit=auto_submit)
    typed = []
    saved = []
    monkeypatch.setattr(a, "_ensure_running", lambda *_a, **_k: True)
    monkeypatch.setattr(a, "_open_new_order", lambda: form)
    monkeypatch.setattr(a, "_collect_edits", lambda f: list(f.cells))
    monkeypatch.setattr(a, "_type", lambda ctrl, value, multiline=False: typed.append((ctrl.key, value)))
    monkeypatch.setattr(a, "_save", lambda f: saved.append(f))
    monkeypatch.setattr(a, "_blocking_dialog", lambda: None)
    return a, typed, saved


def test_input_order_fills_every_mapped_field(monkeypatch):
    form = _Form()
    a, typed, saved = _wired(monkeypatch, form)

    a.input_order(_order())

    got = dict(typed)
    assert got["product_name"] == "장미꽃다발"
    assert got["receiver_name"] == "이받는"
    assert got["delivery_date"] == "2026-07-25"
    assert got["delivery_time"] == "14:30"
    assert got["card"] == "번창하세요"
    assert saved == []          # auto_submit=N 이면 저장하지 않는다


def test_input_order_saves_only_when_auto_submit(monkeypatch):
    form = _Form()
    a, _typed, saved = _wired(monkeypatch, form, auto_submit=True)

    a.input_order(_order())

    assert saved == [form]


def test_missing_field_aborts_instead_of_filling_partially(monkeypatch):
    """칸 하나를 못 찾으면 레이아웃이 어긋난 것이다 — 다른 칸도 못 믿는다.

    부분 입력은 '받는분이 비었거나 남의 칸에 들어간 주문'을 남기고, 그게 저장되면
    오배송이다. 통째로 중단해 백업(수동입력) 경로로 보낸다.
    """
    form = _Form(drop=("receiver_name",))
    a, _typed, _saved = _wired(monkeypatch, form)

    with pytest.raises(RuntimeError, match="receiver_name"):
        a.input_order(_order())


def test_unexpected_form_size_aborts(monkeypatch):
    """좌표는 실측 폼 크기 기준이다. 크기가 다르면 엉뚱한 칸에 넣게 된다."""
    form = _Form(size=(1200, 900))
    a, _typed, _saved = _wired(monkeypatch, form)

    with pytest.raises(RuntimeError, match="폼 크기"):
        a.input_order(_order())


def test_program_not_running_raises(monkeypatch):
    a = _automator()
    monkeypatch.setattr(a, "_ensure_running", lambda *_a, **_k: False)

    with pytest.raises(RuntimeError, match="미기동"):
        a.input_order(_order())


def test_card_is_typed_as_multiline(monkeypatch):
    """카드내용만 메모 칸이라 줄바꿈을 살린다."""
    form = _Form()
    a = _automator()
    calls = []
    monkeypatch.setattr(a, "_ensure_running", lambda *_a, **_k: True)
    monkeypatch.setattr(a, "_open_new_order", lambda: form)
    monkeypatch.setattr(a, "_collect_edits", lambda f: list(f.cells))
    monkeypatch.setattr(a, "_type",
                        lambda ctrl, value, multiline=False: calls.append((ctrl.key, multiline)))

    a.input_order(_order())

    modes = dict(calls)
    assert modes["card"] is True
    assert modes["delivery_place"] is False


class _Button:
    def __init__(self, name):
        self.Name = name
        self.ControlTypeName = "ButtonControl"
        self.clicked = False

    def Click(self):
        self.clicked = True


class _Dialog:
    def __init__(self, name, buttons):
        self.Name = name
        self.buttons = [_Button(b) for b in buttons]

    def GetChildren(self):
        return self.buttons


def test_dialog_during_fill_aborts_and_names_the_field(monkeypatch):
    """모달이 뜨면 폼이 비활성이라 이후 입력이 전부 허공으로 간다.

    RoseWeb 은 확인창을 Delphi TMessageForm 으로 띄운다(#32770 아님) — 실측.
    """
    form = _Form()
    a, typed, _saved = _wired(monkeypatch, form)
    dialog = _Dialog("화원박사-ROSEWeb", ["OK"])
    seen = {"n": 0}

    def after_one_field():
        seen["n"] += 1
        return dialog if seen["n"] >= 2 else None

    monkeypatch.setattr(a, "_blocking_dialog", after_one_field)

    with pytest.raises(RuntimeError, match="대화상자"):
        a.input_order(_order())

    assert dialog.buttons[0].clicked is True   # 버튼 하나짜리 안내창은 닫아준다
    assert len(typed) == 2                     # 두 번째 칸에서 멈췄다


def test_multi_button_dialog_is_left_alone(monkeypatch):
    """'저장할까요?' 같은 선택지는 우리가 고를 일이 아니다."""
    form = _Form()
    a, _typed, _saved = _wired(monkeypatch, form)
    dialog = _Dialog("화원박사-ROSEWeb", ["예", "아니오"])
    monkeypatch.setattr(a, "_blocking_dialog", lambda: dialog)

    with pytest.raises(RuntimeError, match="닫지 않음"):
        a.input_order(_order())

    assert all(b.clicked is False for b in dialog.buttons)


def test_open_new_order_refuses_when_a_form_is_already_open(monkeypatch):
    """Insert 를 또 누르면 같은 자리에 폼이 겹쳐 떠서 어디에 넣었는지 알 수 없다."""
    a = _automator()
    monkeypatch.setattr(a, "_find_window", lambda cls: object() if cls == layout.FORM_CLASS else None)

    with pytest.raises(RuntimeError, match="이미 열려"):
        a._open_new_order()


class _FakeUia:
    """SendKeys/클립보드 호출을 순서대로 기록하는 가짜 uiautomation."""

    def __init__(self, clipboard="사장님이 복사해둔 것"):
        self.calls = []
        self.clipboard = clipboard

    def SendKeys(self, text, waitTime=None):
        self.calls.append(("keys", text))

    def SetClipboardText(self, text):
        self.calls.append(("clip", text))
        self.clipboard = text

    def GetClipboardText(self):
        return self.clipboard


def test_type_pastes_over_selection(monkeypatch):
    """입력 순서: 전체선택 → 클립보드 → 붙여넣기 → Tab.

    키를 하나씩 보내면 한글이 깨지고(실측 '김발주'→'주癰償') 날짜 마스크도 어긋난다.
    Ctrl+A 뒤에 Delete 를 넣으면 조합 잔여물('?김발주')이 남아, 선택 상태에서 그대로
    덮어쓴다.
    """
    fake = _FakeUia()
    monkeypatch.setattr("ggotaiorder.rpa.roseweb.automator._uia", lambda: fake)
    a = _automator()
    a._ui_pause = a._key_wait = a._clip_pause = 0
    cell = _Cell("x", 0, 0)

    a._type(cell, "김발주")

    assert cell.focused is True
    assert fake.calls == [
        ("keys", "{Ctrl}a"),
        ("clip", "김발주"),
        ("keys", "{Ctrl}v"),
        ("keys", "{Tab}"),
    ]
    assert ("keys", "{Delete}") not in fake.calls


def test_clipboard_is_restored_after_filling(monkeypatch):
    """붙여넣기로 입력하느라 클립보드를 빌려 쓴다 — 사장님 것을 말없이 날리면 안 된다."""
    fake = _FakeUia(clipboard="원래 내용")
    monkeypatch.setattr("ggotaiorder.rpa.roseweb.automator._uia", lambda: fake)
    form = _Form()
    a = _automator()
    a._ui_pause = a._key_wait = a._clip_pause = 0
    monkeypatch.setattr(a, "_ensure_running", lambda *_a, **_k: True)
    monkeypatch.setattr(a, "_open_new_order", lambda: form)
    monkeypatch.setattr(a, "_collect_edits", lambda f: list(f.cells))
    monkeypatch.setattr(a, "_blocking_dialog", lambda: None)

    a.input_order(_order())

    assert fake.clipboard == "원래 내용"


def test_already_open_form_blocks_automation(monkeypatch):
    """사장님이 열어둔 주문폼에 타이핑하면 그분 작업을 덮어쓴다.

    미구동과 같이 취급해 백업(manual)으로 흘린다 — 재시도 스캐너가 나중에 다시 집는다.
    """
    a = _automator()
    monkeypatch.setattr(a, "_ensure_running", lambda *_a, **_k: True)
    monkeypatch.setattr(a, "_find_window", lambda cls: object() if cls == layout.FORM_CLASS else None)

    assert a.is_program_running() is False
