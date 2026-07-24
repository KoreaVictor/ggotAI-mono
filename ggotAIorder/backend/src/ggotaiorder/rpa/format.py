"""관리 프로그램과 무관한 값 포맷 helper.

가격·일시 포맷은 어느 프로그램에 넣든 규칙이 같다. 프로그램별 mapping 모듈이 각자
구현하면 파서가 갈라져 언젠가 서로 다르게 동작한다(같은 주문이 FlowerNT 에선 14:30,
RoseWeb 에선 빈칸이 되는 식). 그래서 여기 한 벌만 둔다.
"""

from __future__ import annotations

import re


def normalize_price(price: object) -> str:
    """숫자만 남긴 문자열. None/빈값은 ''. float는 자릿수 붕괴를 막으려 int로 절삭."""
    if price is None:
        return ""
    if isinstance(price, float):
        price = int(price)
    return re.sub(r"[^0-9]", "", str(price))


def split_delivery_datetime(delivery_at: str | None) -> tuple[str, str]:
    """ISO/공백구분 일시를 (YYYY-MM-DD, HH:MM)로 분리. 시각 없으면 ('date','').

    타임존 접미사(+09:00)는 폼이 현지시각 기준이라 버린다. 시·분이 비면 시각은 ''.
    """
    if not delivery_at:
        return ("", "")
    s = str(delivery_at).strip().replace("T", " ")
    parts = s.split(" ", 1)
    date = parts[0]
    time = ""
    if len(parts) > 1 and parts[1].strip():
        hm = parts[1].strip().split(":")
        if len(hm) >= 2 and hm[0].strip() and hm[1].strip():
            time = f"{hm[0].zfill(2)}:{hm[1].zfill(2)}"
    return (date, time)
