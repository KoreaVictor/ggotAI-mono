"""붙여넣을 값 다듬기(순수 로직)."""

from ggotaiorder.rpa.roseweb.keys import prepare


def test_plain_text_passes_through():
    assert prepare("장미꽃다발") == "장미꽃다발"


def test_braces_are_not_escaped():
    """입력은 붙여넣기다 — SendKeys 문법으로 이스케이프하면 그 문자가 그대로 들어간다."""
    assert prepare("{Enter}") == "{Enter}"
    assert prepare("축 개업(본점)") == "축 개업(본점)"


def test_newlines_become_spaces_for_single_line_fields():
    """한 줄 칸에 줄바꿈이 들어가면 칸마다 처리가 제각각이라 결과를 예측할 수 없다."""
    assert prepare("서울시 강남구\n논현로 1") == "서울시 강남구 논현로 1"
    assert prepare("a\r\nb") == "a b"


def test_multiline_keeps_line_breaks():
    """카드내용은 메모 칸이라 줄바꿈을 살린다(붙여넣기라 Enter 키가 아니다)."""
    assert prepare("첫 줄\n둘째 줄", multiline=True) == "첫 줄\n둘째 줄"
    assert prepare("첫 줄\r\n둘째 줄", multiline=True) == "첫 줄\n둘째 줄"


def test_tabs_become_spaces():
    assert prepare("a\tb") == "a b"
    assert prepare("a\tb", multiline=True) == "a b"


def test_empty_and_none():
    assert prepare("") == ""
    assert prepare(None) == ""
