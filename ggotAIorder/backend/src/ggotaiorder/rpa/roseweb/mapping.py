"""RpaOrder → RoseWeb 주문폼(TFmju1inp) 필드값 순수 매핑.

UIA 의존이 없어 단위테스트로 전부 검증한다. 실제 입력은 automator 가 이 dict 를 받아
`layout.FIELD_POSITIONS` 의 자리에 타이핑한다. 따라서 **키는 layout.FIELD_POSITIONS 의
키와 같아야 한다** — 없는 키를 만들면 그 값은 조용히 버려진다.
"""

from __future__ import annotations

from ggotaiorder.rpa.format import normalize_price, split_delivery_datetime
from ggotaiorder.rpa.models import RpaOrder

__all__ = ["normalize_price", "split_delivery_datetime", "order_to_values"]


def order_to_values(order: RpaOrder) -> dict[str, str]:
    """필드키 → 타이핑할 문자열. 빈 값은 키 자체를 뺀다(칸을 건드리지 않는다).

    빈 값을 굳이 넣으면 lookup/검증 칸이 반응해 팝업이 뜰 수 있고, 이미 채워진
    기본값(예: 발주자 '개인')을 지우게 된다.
    """
    date_str, time_str = split_delivery_datetime(order.delivery_at)
    values: dict[str, str] = {
        "orderer_name": order.customer_name or "",
        "orderer_phone": order.customer_phone_number or "",
        "product_name": order.product_name or "",
        # 단가는 0도 유효한 값이라 빈값 생략 규칙에 걸리지 않게 항상 문자열로 만든다.
        "unit_price": normalize_price(order.price),
        "quantity": str(order.quantity or 1),
        "delivery_date": date_str,
        # 시각을 못 뽑았으면 들은 원문("오후 2시경")이라도 넣는다 — 배달시간 칸은
        # 자유입력이라 그대로 들어가고, 비워두면 정보가 사라진다.
        "delivery_time": time_str or (order.delivery_at_text or ""),
        "delivery_place": order.delivery_place or "",
        "receiver_name": order.receiver_name or "",
        "receiver_phone": order.receiver_phone_number or "",
        "ribbon_congrats": order.ribbon_congratulations or "",
        "ribbon_sender": order.ribbon_sender or "",
        "card": order.card_message or "",
    }
    return {k: v for k, v in values.items() if v != ""}
