"""칸에 넣기 전 값 다듬기.

입력은 **클립보드 붙여넣기**로 한다(`automator._type`). 키를 하나씩 보내는
`SendKeys` 로는 한글이 깨졌다 — 실측에서 '김발주'가 '주癰償', '축 개업'이 '내?개업'
으로 들어갔다(IME 조합이 DB 연동 칸의 자동완성과 엉킨다). 날짜 칸도 타이핑하면
'2026-  -07' 처럼 마스크가 어긋나는데 붙여넣기는 정확하다.

붙여넣기라 SendKeys 의 `{}` 문법 이스케이프는 **하면 안 된다**(그대로 문자로 들어간다).
여기서 하는 일은 공백 정리뿐이다.
"""

from __future__ import annotations


def prepare(text: str | None, *, multiline: bool = False) -> str:
    """붙여넣을 문자열. 한 줄짜리 칸이면 줄바꿈·탭을 공백으로 눌러 넣는다.

    한 줄 칸에 줄바꿈이 붙어 들어가면 칸마다 처리가 제각각이라(잘리거나, 뒷부분이
    사라지거나) 결과를 예측할 수 없다. 메모 칸(카드내용)만 줄바꿈을 살린다.
    """
    if not text:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if multiline:
        return s.replace("\t", " ")
    return s.replace("\n", " ").replace("\t", " ")
