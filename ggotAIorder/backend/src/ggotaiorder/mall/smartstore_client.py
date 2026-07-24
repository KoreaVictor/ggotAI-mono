"""네이버 커머스API 클라이언트.

SmartStoreClient(Protocol)로 계약을 고정하고, HttpSmartStoreClient 가 실 HTTP 를 구현한다:
OAuth2 토큰(전자서명) → 결제완료(PAYED) 신규주문 조회 → 상세 조회 → SmartStoreOrder 매핑,
그리고 발주확인(승인).

전자서명 규격: message = f"{client_id}_{timestamp_ms}" 를 client_secret 을 bcrypt salt 로 하여
해시한 뒤 base64. client_secret 이 고정 salt 이므로 결정적(단위테스트 가능).

⚠️ 라이브 검증: 커머스API 는 **등록된 IP 에서 온 요청만** 허용한다(커머스API센터에서 등록한
API 호출 IP = 백엔드 공인 IP 여야 함). 아래 응답 필드 매핑(_to_order)은 공식 문서 기준이며,
실주문 첫 응답으로 필드명을 최종 확정한다(LIVE-RECONCILE 주석).
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

import bcrypt
import httpx

from ggotaiorder.mall.models import MallCredential, SmartStoreOrder
from ggotaiorder.pipeline.models import OrderExtraction

logger = logging.getLogger(__name__)

# 네이버 커머스API 베이스 URL 및 경로.
API_BASE = "https://api.commerce.naver.com/external/v1"
TOKEN_PATH = "/oauth2/token"
CHANGED_PATH = "/pay-order/seller/product-orders/last-changed-statuses"
QUERY_PATH = "/pay-order/seller/product-orders/query"
CONFIRM_PATH = "/pay-order/seller/product-orders/confirm"

# OAuth2 토큰 만료 여유(초). 실제 만료(expires_in)에서 이만큼 앞당겨 재발급한다.
TOKEN_TTL_MARGIN_SEC = 60
# 커서(cred.cursor)가 없을 때 조회 시작점: 지금부터 이 시간 전까지 소급.
DEFAULT_LOOKBACK_HOURS = 24
# 요청 타임아웃(초).
HTTP_TIMEOUT_SEC = 15.0
# 서명 timestamp 시계오차 보정(초) — 서버보다 살짝 과거로 서명(권장 관행).
_SIGN_SKEW_SEC = 3

_KST = timezone(timedelta(hours=9))

# 프로세스 메모리 토큰 캐시: client_id -> (access_token, expiry_epoch_sec).
# 모듈 수준이라 client 인스턴스가 폴링마다 새로 생성돼도 토큰을 재사용한다.
_token_cache: dict[str, tuple[str, float]] = {}


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


def _raise_for_status(resp, label: str) -> None:
    """4xx/5xx 면 응답 본문을 로그에 남긴 뒤 예외를 올린다.

    커머스API 는 실패 원인을 **본문에만** 담는다. 실사건 2건 모두 그랬다 —
    403 은 ``GW.IP_NOT_ALLOWED``(등록 IP 아님), 400 은 커서 형식(ISO-8601).
    ``raise_for_status()`` 만 하면 로그에 상태코드만 남아 원인을 못 찾는다.
    """
    if resp.status_code >= 400:
        logger.error(
            "커머스API %s 실패 %s: %s", label, resp.status_code, (resp.text or "")[:500]
        )
    resp.raise_for_status()


class HttpSmartStoreClient:
    """네이버 커머스API 실구현."""

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

    # ---- OAuth2 토큰 ----

    def _request_token(self, cred: MallCredential) -> tuple[str, int]:
        """토큰을 새로 발급받아 (access_token, expires_in초) 반환."""
        if not cred.client_secret:
            raise RuntimeError("client_secret 미주입 — 토큰 발급 불가(호출 전 복호화 필요)")
        timestamp_ms = int((time.time() - _SIGN_SKEW_SEC) * 1000)
        signature = self._make_signature(cred.client_id, cred.client_secret, timestamp_ms)
        # 판매자 유형: 본인 스토어는 SELF. (대행사 연동은 SELLER + account_id — 후속)
        data = {
            "client_id": cred.client_id,
            "timestamp": str(timestamp_ms),
            "client_secret_sign": signature,
            "grant_type": "client_credentials",
            "type": "SELF",
        }
        resp = httpx.post(API_BASE + TOKEN_PATH, data=data, timeout=HTTP_TIMEOUT_SEC)
        _raise_for_status(resp, "토큰 발급")
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise RuntimeError(f"토큰 발급 응답에 access_token 없음: {body}")
        expires_in = int(body.get("expires_in") or 10800)  # 기본 ~3시간
        return token, expires_in

    def _get_token(self, cred: MallCredential) -> str:
        """유효한 토큰을 반환한다(만료 여유 전이면 캐시 사용)."""
        cached = _token_cache.get(cred.client_id)
        now = time.time()
        if cached and cached[1] > now:
            return cached[0]
        token, expires_in = self._request_token(cred)
        _token_cache[cred.client_id] = (token, now + expires_in - TOKEN_TTL_MARGIN_SEC)
        return token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    # ---- 신규주문 수집 ----

    def fetch_new_orders(
        self, cred: MallCredential
    ) -> tuple[list[SmartStoreOrder], str]:
        token = self._get_token(cred)
        last_changed_from = self._normalize_iso(cred.cursor) or self._default_from()

        # 1) 결제완료(PAYED) 상태로 바뀐 상품주문 번호 목록.
        changed = httpx.get(
            API_BASE + CHANGED_PATH,
            headers=self._auth_headers(token),
            params={"lastChangedFrom": last_changed_from, "lastChangedType": "PAYED"},
            timeout=HTTP_TIMEOUT_SEC,
        )
        _raise_for_status(changed, "변경상태 조회")
        cdata = changed.json().get("data") or {}
        statuses = cdata.get("lastChangeStatuses") or []
        product_order_ids = [
            s.get("productOrderId") for s in statuses if s.get("productOrderId")
        ]
        # 다음 커서: 응답이 알려주는 lastChangedTo(없으면 현재 시각). 응답값이라도
        # 그대로 믿지 않고 정규화한다 — 다음 요청의 lastChangedFrom 이 되기 때문이다.
        next_cursor = self._normalize_iso(cdata.get("lastChangedTo")) or self._now_iso()

        if not product_order_ids:
            return [], next_cursor

        # 2) 상세 조회로 주문 필드 확보.
        detail = httpx.post(
            API_BASE + QUERY_PATH,
            headers=self._auth_headers(token),
            json={"productOrderIds": product_order_ids},
            timeout=HTTP_TIMEOUT_SEC,
        )
        _raise_for_status(detail, "주문상세 조회")
        items = detail.json().get("data") or []
        orders = [self._to_order(item) for item in items]
        orders = [o for o in orders if o is not None]
        return orders, next_cursor

    def _to_order(self, item: dict) -> SmartStoreOrder | None:
        """커머스API 상세 응답 1건 → SmartStoreOrder.

        LIVE-RECONCILE: 아래 필드 경로는 공식 문서 기준 추정이다. 실주문 첫 응답으로
        정확한 필드명을 확인해 필요 시 수정한다(테스트의 가짜 JSON 과 함께). API 정형값은
        권위 필드로 채우고, 배달일시·리본·카드·상품분류는 None 으로 둔다(수집 단계에서
        메모 Gemini 로 병합). 배송메모·옵션은 memo_text 로 모아 Gemini 입력이 된다.
        """
        po = item.get("productOrder") or {}
        order = item.get("order") or {}

        product_order_id = po.get("productOrderId")
        if not product_order_id:
            logger.warning("productOrderId 없는 상세 응답 스킵: %r", item)
            return None

        ship = po.get("shippingAddress") or {}
        delivery_place = " ".join(
            p for p in (ship.get("baseAddress"), ship.get("detailAddress")) if p
        ).strip() or None

        # Gemini 입력용 자유텍스트(배송메모+옵션+상품명). 리본/카드/배달일시가 여기 담긴다.
        memo_parts = [
            po.get("shippingMemo"),
            po.get("productOption"),
            po.get("productName"),
        ]
        memo_text = "\n".join(p for p in memo_parts if p)

        fields = OrderExtraction(
            product_name=po.get("productName"),
            quantity=po.get("quantity"),
            price=po.get("totalPaymentAmount"),
            customer_name=order.get("ordererName"),
            customer_phone_number=order.get("ordererTel"),
            receiver_name=ship.get("name"),
            receiver_phone_number=ship.get("tel1"),
            delivery_place=delivery_place,
            # 아래는 수집 단계 Gemini 병합 대상 → None
            delivery_at=None,
            delivery_at_text=None,
            ribbon_congratulations=None,
            card_message=None,
            sang_divi=None,
        )
        return SmartStoreOrder(
            product_order_id=product_order_id,
            raw_text=memo_text or (po.get("productName") or ""),
            memo_text=memo_text,
            fields=fields,
        )

    # ---- 발주확인 ----

    def confirm_order(self, cred: MallCredential, product_order_id: str) -> None:
        token = self._get_token(cred)
        resp = httpx.post(
            API_BASE + CONFIRM_PATH,
            headers=self._auth_headers(token),
            json={"productOrderIds": [product_order_id]},
            timeout=HTTP_TIMEOUT_SEC,
        )
        _raise_for_status(resp, "발주확인")
        data = resp.json().get("data") or {}
        fail_ids = data.get("failProductOrderIds") or []
        if product_order_id in fail_ids:
            raise RuntimeError(f"발주확인 실패 productOrderId={product_order_id}: {data}")

    # ---- 시간 유틸 ----

    def _now_iso(self) -> str:
        return datetime.now(_KST).isoformat(timespec="milliseconds")

    def _default_from(self) -> str:
        return (datetime.now(_KST) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)).isoformat(
            timespec="milliseconds"
        )

    def _normalize_iso(self, value: str | None) -> str | None:
        """커서를 커머스API 가 받는 ISO-8601 형식(밀리초 필수)으로 맞춘다.

        네이버는 `lastChangedFrom` 에 밀리초가 없으면 400("유효한 ISO-8601 포맷이
        아닙니다")을 준다. 타임존 오프셋과 시각의 오래됨은 무관하다(라이브 확인).
        커서는 폴링이 성공해야 전진하므로, 형식이 어긋난 값이 한 번 저장되면 수집이
        영구히 멈춘다 — 그래서 저장할 때도 쓸 때도 여기를 거친다.

        읽을 수 없는 값은 None 을 돌려 호출부가 기본 조회창으로 되돌아가게 한다.
        """
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).isoformat(timespec="milliseconds")
        except ValueError:
            logger.warning("커서 형식을 읽을 수 없어 기본 조회창으로 대체: %r", value)
            return None
