"""파이프라인 데이터 모델: Gemini 추출 스키마 및 수집 이력 DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field

# 배송일시 미상 시 NOT NULL(timestamptz) 충족용 센티넬(=보정 필요). 설계서 §6.
DELIVERY_AT_UNKNOWN = "2099-12-31T23:59:59+09:00"


class OrderExtraction(BaseModel):
    """Gemini가 stt_text에서 추출하는 11개 표준 주문 필드(누락은 None)."""

    customer_name: Optional[str] = Field(default=None, description="주문자 이름")
    customer_phone_number: Optional[str] = Field(default=None, description="주문자 전화번호")
    product_name: Optional[str] = Field(default=None, description="상품명")
    quantity: Optional[int] = Field(default=None, description="수량")
    price: Optional[int] = Field(default=None, description="가격(원 단위 정수)")
    delivery_at: Optional[str] = Field(default=None, description="배달 일시")
    delivery_place: Optional[str] = Field(default=None, description="배달 장소")
    receiver_name: Optional[str] = Field(default=None, description="받는 사람 이름")
    receiver_phone_number: Optional[str] = Field(default=None, description="받는 사람 전화번호")
    ribbon_congratulations: Optional[str] = Field(default=None, description="리본 경조사 문구")
    card_message: Optional[str] = Field(default=None, description="카드 메시지")


@dataclass
class CallHistory:
    """server_call_history 한 행의 파이프라인 사용 필드."""

    id: int
    shop_key: int
    shop_name: str
    customer_name: Optional[str]
    customer_phone_number: Optional[str]
    stt_text: Optional[str]
    audio_file_name: Optional[str]
    channel_order: str
