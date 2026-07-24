"""폼 기준 상대좌표로 입력칸을 찾는 로직(순수). UIA 컨트롤은 가짜로 대체한다."""

from ggotaiorder.rpa.roseweb import layout, locator


class _Rect:
    def __init__(self, left, top, width=100, height=25):
        self.left, self.top = left, top
        self.right, self.bottom = left + width, top + height


class _Ctrl:
    def __init__(self, name, left, top, width=100, height=25, parent=None):
        self.name = name
        self.BoundingRectangle = _Rect(left, top, width, height)
        self._parent = parent

    def GetParentControl(self):
        return self._parent

    def __repr__(self):
        return f"<{self.name}>"


# 폼 origin. 실측값(421,113)을 그대로 쓴다.
OX, OY = 421, 113


def test_nearest_edit_picks_closest_by_relative_pos():
    # 목표 상대 (120, 50) → 스크린 (541,163) 근처.
    a = _Ctrl("date", OX + 119, OY + 52)
    b = _Ctrl("far", 900, 500)
    assert locator.nearest_edit([a, b], 120, 50, OX, OY) is a


def test_nearest_edit_none_when_all_out_of_radius():
    b = _Ctrl("far", 900, 500)
    assert locator.nearest_edit([b], 120, 50, OX, OY) is None


def test_nearest_edit_none_for_empty_list():
    assert locator.nearest_edit([], 120, 50, OX, OY) is None


def test_default_radius_is_tight_enough_to_reject_the_neighbouring_row():
    """실측상 이웃 칸은 26px 이상 떨어져 있다 — 기본 반경으로는 안 잡혀야 한다.

    넓게 잡으면 목표 칸이 사라졌을 때 조용히 옆 칸에 값을 넣는다(= 오배송).
    """
    neighbour = _Ctrl("row_below", OX + 99, OY + 458)
    assert locator.nearest_edit([neighbour], 99, 430, OX, OY) is None
    assert locator.DEFAULT_RADIUS == layout.FIELD_MATCH_RADIUS


def test_one_pixel_jitter_still_matches():
    """폼을 다시 열면 dy 가 1px 흔들린다(실측)."""
    jittered = _Ctrl("place", OX + 99, OY + 431)
    assert locator.nearest_edit([jittered], 99, 430, OX, OY) is jittered


def test_clipped_control_is_detected():
    """그리드는 화면 밖 행의 편집 컨트롤까지 노출한다 — 부모 영역을 벗어나면 유령이다."""
    grid = _Ctrl("grid", OX + 12, OY + 232, 1020, 131)
    phantom = _Ctrl("row9", OX + 63, OY + 533, 70, 25, parent=grid)
    real = _Ctrl("row1", OX + 63, OY + 275, 70, 25, parent=grid)
    assert locator.is_clipped(phantom) is True
    assert locator.is_clipped(real) is False


def test_control_without_parent_is_not_clipped():
    assert locator.is_clipped(_Ctrl("orphan", 10, 10)) is False


def test_visible_edits_drops_the_phantom_rows():
    grid = _Ctrl("grid", OX + 12, OY + 232, 1020, 131)
    real = _Ctrl("row1", OX + 63, OY + 275, 70, 25, parent=grid)
    phantom = _Ctrl("row9", OX + 63, OY + 533, 70, 25, parent=grid)
    panel = _Ctrl("panel", OX + 4, OY + 32, 1069, 771)
    card = _Ctrl("card", OX + 99, OY + 545, 476, 83, parent=panel)

    got = locator.visible_edits([real, phantom, card])

    assert got == [real, card]


def test_phantom_row_cannot_be_picked_after_filtering():
    """카드내용(99,545) 근처엔 유령 행(63,533)이 있다. 걸러내면 후보에서 사라진다."""
    grid = _Ctrl("grid", OX + 12, OY + 232, 1020, 131)
    phantom = _Ctrl("row9", OX + 99, OY + 540, 70, 25, parent=grid)

    assert locator.nearest_edit([phantom], 99, 545, OX, OY) is phantom  # 필터 전엔 잡힌다
    assert locator.nearest_edit(locator.visible_edits([phantom]), 99, 545, OX, OY) is None
