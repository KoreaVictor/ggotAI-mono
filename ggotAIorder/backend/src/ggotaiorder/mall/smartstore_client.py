"""네이버 커머스API 클라이언트 추상화.

SmartStoreClient(Protocol)로 계약을 고정하고, 실제 HTTP(OAuth2 토큰·주문조회·발주확인)는
client_id/secret 확보 후 구현(라이브 체크리스트). 단, 전자서명(_make_signature)은 결정적이라
지금 구현·단위테스트한다.

전자서명 규격(네이버 커머스API): message = f"{client_id}_{timestamp_ms}" 를 client_secret 을
bcrypt salt 로 하여 해시한 뒤 base64 인코딩. client_secret 이 고정 salt 이므로 결정적이다.
"""

from __future__ import annotations

import base64
import logging
from typing import Protocol

import bcrypt

from ggotaiorder.mall.models import MallCredential, SmartStoreOrder

logger = logging.getLogger(__name__)

# OAuth2 토큰 만료 여유(초). 라이브 구현 시 만료시각까지 프로세스 메모리 캐시.
TOKEN_TTL_MARGIN_SEC = 60


class SmartStoreClient(Protocol):
    """스마트스토어 신규주문 수집·발주확인 계약."""

    def fetch_new_orders(
        self, cred: MallCredential
    ) -> tuple[list[SmartStoreOrder], str]:
        """결제완료(PAYED) 신규주문 목록과 다음 커서(ISO8601)를 반환."""
        ...

    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        """발주확인(승인) — 외부 쓰기."""
        ...


class HttpSmartStoreClient:
    """네이버 커머스API 실구현 (초기 스텁).

    TODO(라이브): OAuth2 토큰(_make_signature 서명, ~3h 캐시)
      → last-changed-statuses(lastChangedFrom=cursor, status=PAYED)
      → product-orders/query 상세 → SmartStoreOrder 매핑
      → confirm_order: 발주확인 엔드포인트 호출.
    실제 HTTP 는 client_id/secret 확보 후. fetch/confirm 은 현재 NotImplementedError.
    """

    def _make_signature(
        self, client_id: str, client_secret: str, timestamp_ms: int
    ) -> str:
        """전자서명 생성: bcrypt(f"{client_id}_{ts}", salt=client_secret) → base64.

        client_secret 은 네이버가 발급한 bcrypt salt 문자열($2a$.../$2b$...)이다.
        salt 가 고정이므로 동일 입력에 동일 서명(결정적) → 단위테스트 가능.
        """
        message = f"{client_id}_{timestamp_ms}".encode("utf-8")
        hashed = bcrypt.hashpw(message, client_secret.encode("utf-8"))
        return base64.b64encode(hashed).decode("utf-8")

    def fetch_new_orders(
        self, cred: MallCredential
    ) -> tuple[list[SmartStoreOrder], str]:
        logger.warning("[STUB] HttpSmartStoreClient.fetch_new_orders — 자격증명 미확보")
        raise NotImplementedError(
            "네이버 커머스API 주문조회는 client_id/secret 확보 후 구현됩니다."
        )

    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        logger.warning("[STUB] HttpSmartStoreClient.confirm_order — 자격증명 미확보")
        raise NotImplementedError(
            "네이버 커머스API 발주확인은 client_id/secret 확보 후 구현됩니다."
        )
