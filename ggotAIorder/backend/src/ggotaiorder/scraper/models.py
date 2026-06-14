"""인트라넷 크롤러 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass

from ggotaiorder.pipeline.models import OrderExtraction

# server_call_history.channel_order 에 기록되는 인트라넷 채널 식별자.
# crawler(적재)와 repository(중복검증)가 동일 값을 써야 하므로 단일 상수로 공유한다.
INTRANET_CHANNEL = "인터라넷"


@dataclass
class IntranetShop:
    """인트라넷 설정이 있는 꽃집."""

    shop_key: int
    shop_name: str
    url: str
    username: str
    enc_password: str  # AES 암호문(복호화 전)


@dataclass
class ScrapedOrder:
    """스크래핑된 단일 주문."""

    order_no: str               # 인트라넷 주문번호(중복 식별키)
    raw_text: str               # 원문(stt_text 로 저장)
    fields: OrderExtraction     # 11필드 (pipeline.models.OrderExtraction 재사용)
