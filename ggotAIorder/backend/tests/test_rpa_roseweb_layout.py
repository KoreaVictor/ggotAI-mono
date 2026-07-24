"""layout.py 실측 상수의 형태 검증(라이브 불필요).

좌표 자체가 맞는지는 실측으로만 알 수 있지만, '플레이스홀더가 남았다'·'키가 어긋났다'
같은 사고는 여기서 잡을 수 있다. 필드키는 mapping.order_to_values(Task 2) 와 짝이다.
"""

from ggotaiorder.rpa.roseweb import layout

EXPECTED_KEYS = {
    "orderer_name", "orderer_phone",
    "product_name", "unit_price", "quantity",
    "delivery_date", "delivery_time", "delivery_place",
    "receiver_name", "receiver_phone",
    "ribbon_congrats", "ribbon_sender", "card",
}


def test_field_positions_cover_expected_keys():
    assert set(layout.FIELD_POSITIONS) == EXPECTED_KEYS


def test_no_placeholder_positions_left():
    """(0,0) 은 '아직 안 쟀다'는 뜻 — 실측값으로 대체되지 않은 채 넘어가면 안 된다."""
    spots = list(layout.FIELD_POSITIONS.values()) + [
        layout.PRODUCT_CODE_POS, layout.SAVE_BUTTON_POS,
        layout.CANCEL_BUTTON_POS, layout.STATUS_NORMAL_POS,
    ]
    assert all(pos != (0, 0) for pos in spots)


def test_positions_are_inside_the_measured_form():
    w, h = layout.FORM_SIZE
    for key, (dx, dy) in layout.FIELD_POSITIONS.items():
        assert 0 <= dx < w, key
        assert 0 <= dy < h, key


def test_match_radius_is_tighter_than_field_spacing():
    """실측상 목표칸과 두 번째로 가까운 컨트롤 사이가 최소 26px — 반경은 그보다 한참 작아야 한다."""
    assert 0 < layout.FIELD_MATCH_RADIUS < 26 / 2


def test_product_needs_lookup_popup():
    """상품명 직접 타이핑 불가(실측). True 로 바뀌면 Task 5 의 상품 서브루틴 전제가 깨진다."""
    assert layout.PRODUCT_DIRECT_TYPE is False
    assert layout.LOOKUP_CLASS == "TFmCodesel"
