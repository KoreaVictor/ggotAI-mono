"""실측 덤프로 layout+locator 를 검증한다.

`tests/fixtures/roseweb_form_TFmju1inp.json` 은 2026-07-24 라이브 폼에서 뜬 컨트롤
사각형 그대로다(`roseweb_inspect.py dump`). 라이브 없이도 "layout 의 좌표가 진짜 그
칸을 가리키는가"를 확인할 수 있어, 나중에 layout.py 를 잘못 고치면 여기서 잡힌다.
"""

import json
from pathlib import Path

import pytest

from ggotaiorder.rpa.roseweb import layout, locator

FIXTURE = Path(__file__).parent / "fixtures" / "roseweb_form_TFmju1inp.json"

# 각 필드가 실제로 어떤 컨트롤이어야 하는지(클래스와 크기). Task 1 실측.
EXPECTED = {
    "orderer_name": ("TdxDBEdit", 160, 25),
    "orderer_phone": ("TdxDBEdit", 144, 25),
    "product_name": ("TdxDBEdit", 278, 25),
    "unit_price": ("TRxDBCalcEdit", 94, 24),
    "quantity": ("TRxDBCalcEdit", 46, 24),
    "delivery_date": ("TdxDBDateEdit", 116, 25),
    "delivery_time": ("TdxDBPickEdit", 321, 25),
    "delivery_place": ("TdxDBEdit", 464, 25),
    "receiver_name": ("TdxDBEdit", 199, 25),
    "receiver_phone": ("TdxDBEdit", 151, 25),
    "ribbon_congrats": ("TdxDBPickEdit", 561, 25),
    "ribbon_sender": ("TdxDBPickEdit", 781, 25),
    "card": ("TdxDBMemo", 476, 83),
}


class _Rect:
    def __init__(self, left, top, width, height):
        self.left, self.top = left, top
        self.right, self.bottom = left + width, top + height


class _Parent:
    def __init__(self, top, height):
        self.BoundingRectangle = _Rect(0, top, 4000, height)

    def GetParentControl(self):
        return None


class _Ctrl:
    """덤프 한 줄을 UIA 컨트롤처럼 보이게 감싼 것. origin 은 (0,0) 으로 둔다."""

    def __init__(self, rec):
        self.cls = rec["cls"]
        self.w, self.h = rec["w"], rec["h"]
        self.BoundingRectangle = _Rect(rec["dx"], rec["dy"], rec["w"], rec["h"])
        self._parent = _Parent(rec["p_dy"], rec["p_h"])

    def GetParentControl(self):
        return self._parent


@pytest.fixture(scope="module")
def controls():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [_Ctrl(r) for r in data["inputs"]]


def test_fixture_matches_the_measured_form_size():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert (data["window"]["w"], data["window"]["h"]) == layout.FORM_SIZE
    assert data["window"]["cls"] == layout.FORM_CLASS


def test_phantom_grid_rows_are_filtered_out(controls):
    """실측: 전체 113개 중 그리드 스크롤 밖 행 42개가 걸러져 71개가 남는다."""
    visible = locator.visible_edits(controls)
    assert len(controls) == 113
    assert len(visible) == 71


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_each_field_position_resolves_to_the_expected_control(controls, key):
    visible = locator.visible_edits(controls)
    dx, dy = layout.FIELD_POSITIONS[key]

    got = locator.nearest_edit(visible, dx, dy, 0, 0)

    assert got is not None, f"{key}: 실측 좌표에 컨트롤이 없다"
    assert (got.cls, got.w, got.h) == EXPECTED[key]


def test_product_code_anchor_resolves(controls):
    visible = locator.visible_edits(controls)
    dx, dy = layout.PRODUCT_CODE_POS
    got = locator.nearest_edit(visible, dx, dy, 0, 0)
    assert got is not None
    assert (got.cls, got.w, got.h) == ("TdxEdit", 70, 25)


def test_no_two_fields_resolve_to_the_same_control(controls):
    """두 필드가 같은 칸을 가리키면 하나는 덮어써진다 — 조용한 오입력."""
    visible = locator.visible_edits(controls)
    hits = {}
    for key, (dx, dy) in layout.FIELD_POSITIONS.items():
        got = locator.nearest_edit(visible, dx, dy, 0, 0)
        assert id(got) not in hits, f"{key} 와 {hits.get(id(got))} 가 같은 칸을 가리킨다"
        hits[id(got)] = key
