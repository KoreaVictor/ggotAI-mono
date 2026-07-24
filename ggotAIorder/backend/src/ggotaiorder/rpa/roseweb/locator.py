"""폼 기준 상대좌표로 입력칸(UIA 컨트롤)을 찾는다.

RoseWeb 은 컨트롤 식별자가 폼을 열 때마다 바뀌어 쓸 수 없다(실측). 대신 위치는
±1px 안에서 재현되므로 좌표로 찾는다 — 근거·수치는 `layout` 참조.

UIA 에 직접 의존하지 않는다: 컨트롤에서 쓰는 것은 `BoundingRectangle` 과
`GetParentControl()` 뿐이라 단위테스트에서 가짜 객체로 대체할 수 있다.
"""

from __future__ import annotations

from ggotaiorder.rpa.roseweb import layout

DEFAULT_RADIUS = layout.FIELD_MATCH_RADIUS


def is_clipped(ctrl) -> bool:
    """부모 세로 영역을 벗어난(=화면에 안 보이는) 컨트롤인가.

    상품 그리드는 화면에 3줄만 보이는데 UIA 에는 스크롤 밖 행의 편집 컨트롤까지
    노출한다(실측: 그리드 자식 61개 중 42개). 그것들이 배달장소·경조사어 등 아래쪽
    실제 칸과 위치가 겹쳐 오입력을 부른다. `IsOffscreen` 은 전부 False 라 못 쓰고,
    부모 영역을 벗어났는지가 유일하게 통하는 판별이었다.
    """
    try:
        parent = ctrl.GetParentControl()
    except Exception:
        return False
    if parent is None:
        return False
    r = ctrl.BoundingRectangle
    p = parent.BoundingRectangle
    return r.top < p.top or r.bottom > p.bottom


def visible_edits(edits) -> list:
    """유령 행을 걸러낸 입력칸 목록."""
    return [e for e in edits if not is_clipped(e)]


def nearest_edit(edits, rel_x: int, rel_y: int, origin_x: int, origin_y: int,
                 radius: int = DEFAULT_RADIUS):
    """(rel_x, rel_y) 에 가장 가까운 컨트롤. 허용 반경 밖이면 None.

    반경은 좁게 유지할 것 — 넓히면 목표 칸이 없어졌을 때 조용히 옆 칸을 집는다.
    호출 전에 `visible_edits` 로 유령 행을 걸러 넘기는 것을 전제한다.
    """
    best = None
    best_d2 = None
    for e in edits:
        r = e.BoundingRectangle
        dx = (r.left - origin_x) - rel_x
        dy = (r.top - origin_y) - rel_y
        d2 = dx * dx + dy * dy
        if best_d2 is None or d2 < best_d2:
            best, best_d2 = e, d2
    if best is None or best_d2 > radius * radius:
        return None
    return best
