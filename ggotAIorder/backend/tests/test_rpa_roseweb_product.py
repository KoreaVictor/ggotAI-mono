"""AI 상품명 → RoseWeb 상품 마스터 검색어(순수 로직)."""

import pytest

from ggotaiorder.rpa.roseweb.product import FALLBACK_TERM, MASTER_TERMS, resolve_search_term


@pytest.mark.parametrize("product_name,expected", [
    # 화환 — '근조'가 '화환'보다 먼저 걸려야 한다
    ("근조화환 3단", "근조3단화환"),
    ("조화 화환", "근조3단화환"),
    ("축하화환", "축하3단화환"),
    ("개업 화환", "축하3단화환"),
    # 난 — '동양란'이 '란'보다 먼저
    ("동양란", "동양란"),
    ("서양란 대", "서양란"),
    ("호접란", "서양란"),
    # 화분·식물
    ("관엽식물", "관엽식물"),
    ("공기정화 화분", "관엽식물"),
    # 꽃다발 / 바구니 — '꽃다발'이 '꽃'보다 먼저
    ("장미꽃다발", "꽃다발"),
    ("생화 꽃다발", "꽃다발"),
    ("부케", "꽃다발"),
    ("꽃바구니", "꽃바구니"),
    ("과일바구니", "과일+꽃바구니"),
])
def test_keyword_rules(product_name, expected):
    assert resolve_search_term(product_name) == expected


def test_unknown_falls_back():
    """마스터에 못 맞추면 '기타'. 코드가 비면 그 행은 주문으로 성립하지 않는다."""
    assert resolve_search_term("이상한 신상품 ABC") == FALLBACK_TERM
    assert resolve_search_term("") == FALLBACK_TERM
    assert resolve_search_term(None) == FALLBACK_TERM


def test_every_rule_points_at_a_known_master_name():
    """검색어가 마스터에 없으면 '선택'을 눌러 RoseWeb 을 죽인다(Access violation).

    그래서 규칙이 내놓는 값은 반드시 마스터에 있는 이름이어야 한다.
    """
    samples = ["근조화환", "축하화환", "동양란", "서양란", "화분", "장미꽃다발",
               "꽃바구니", "과일바구니", "듣도보도 못한 것"]
    for name in samples:
        assert resolve_search_term(name) in MASTER_TERMS


def test_fallback_term_is_in_master():
    assert FALLBACK_TERM in MASTER_TERMS
