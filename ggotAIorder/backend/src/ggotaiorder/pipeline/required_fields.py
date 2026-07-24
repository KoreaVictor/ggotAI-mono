"""RPA 등록 필수값 누락 판정.

카톡·문자 주문은 손님이 안 적으면 필드가 빈 채로 들어온다. FlowerNT는 배송일·배달장소
등이 없으면 등록 자체가 안 되므로, 누락이 있으면 자동입력을 돌리지 않고 보류
(rpa_status='hold')한 뒤 사장님이 ggotAIya에서 채우게 한다.

is_order(상품명+가격)보다 엄격한 기준이다 — 주문이긴 하나 아직 등록할 수 없는 상태.
"""

from __future__ import annotations

from ggotaiorder.pipeline.models import DELIVERY_AT_UNKNOWN, OrderExtraction
from ggotaiorder.pipeline.order_payload import normalize_delivery_at

# FlowerNT 주문 등록에 필요한 필드(보고 순서 = 이 순서).
REQUIRED_FIELDS = (
    "product_name", "price", "delivery_at", "delivery_place", "receiver_name",
)


def missing_required(extraction: OrderExtraction) -> list[str]:
    """등록에 필요한데 비어 있는 필드명을 순서대로 반환한다(없으면 빈 리스트).

    delivery_at 은 값이 있어도 ISO 파싱이 안 되면(자연어) 센티넬로 떨어지므로
    누락으로 본다 — 원문은 delivery_at_text 에 남아 사장님 보완의 단서가 된다.
    """
    data = extraction.model_dump()
    missing = []
    for name in REQUIRED_FIELDS:
        value = data[name]
        if value is None:
            missing.append(name)
        elif isinstance(value, str) and value.strip() == "":
            missing.append(name)
        elif name == "delivery_at" and normalize_delivery_at(value) == DELIVERY_AT_UNKNOWN:
            missing.append(name)
    return missing
