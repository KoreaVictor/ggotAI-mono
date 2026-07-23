"""스마트스토어 커머스API 연동 데이터 모델.

인터라넷 크롤러(scraper.models)와 대칭. server_call_history.channel_order 에는
SMARTSTORE_CHANNEL, audio_file_name 에는 provider 식별 마커 SMARTSTORE_AUDIO_MARKER 를
기록한다(scraper 의 INTRANET_CRAWLED 대칭).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ggotaiorder.pipeline.models import OrderExtraction

# server_call_history.channel_order (수집·중복검증·발주확인 스캐너가 공유하는 단일 출처).
SMARTSTORE_CHANNEL = "쇼핑몰"
# audio_file_name 에 기록하는 provider 식별 마커(발주확인 대상 필터에 사용).
SMARTSTORE_AUDIO_MARKER = "SMARTSTORE_API"
# mall_credentials.provider 값.
PROVIDER_SMARTSTORE = "smartstore"


@dataclass
class MallCredential:
    """mall_credentials 한 행 + 런타임 복호화 secret."""

    shop_key: int
    shop_name: str
    provider: str
    client_id: str
    enc_client_secret: str        # AES 암호문(복호화 전)
    extra: dict = field(default_factory=dict)  # store_id 등 provider별 부가정보
    cursor: str | None = None     # last-changed 조회 커서(ISO8601), 없으면 None
    client_secret: str | None = None  # 복호화된 평문(collector 가 런타임 주입)


@dataclass
class SmartStoreOrder:
    """수집된 단일 스마트스토어 주문."""

    product_order_id: str       # 중복 식별키(server_call_history.channel_classification)
    raw_text: str               # 원문(stt_text 로 저장)
    memo_text: str              # Gemini 에 넣을 자유텍스트(메모+옵션+상품명)
    fields: OrderExtraction     # API 정형값으로 채운 권위 필드(배달일시·리본·카드·분류는 None)


@dataclass
class ConfirmTarget:
    """발주확인 대상(rpa_status='success' && mall_ack_status='pending')."""

    order_id: int
    shop_key: int
    product_order_id: str
    ack_attempts: int
