"""RPA 엔진 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RpaOrder:
    """RPA가 관리 프로그램에 입력/백업할 단일 주문.

    order_details 행 + server_call_history.channel_order(channel) 조인 결과.
    """

    order_detail_id: int
    shop_key: int
    shop_name: str
    channel: str                        # 전화/쇼핑몰/인터라넷 (server_call_history.channel_order)
    customer_name: str
    customer_phone_number: str
    product_name: str
    quantity: int
    price: int
    delivery_at: str | None
    delivery_place: str | None
    receiver_name: str | None
    receiver_phone_number: str | None
    ribbon_sender: str | None
    ribbon_congratulations: str | None
    card_message: str | None
    delivery_at_text: str | None = None  # 배송시간 원본 문구(말한 그대로)
    sang_divi: str | None = None         # AI 추출 상품분류(FlowerNT 옵션). 없으면 키워드 폴백
