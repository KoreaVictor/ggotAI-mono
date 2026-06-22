"""RpaOrder → FlowerNT3 주문폼(order_form2) 순수 매핑.

브라우저 의존성이 없어 단위테스트로 전부 검증한다. 실제 입력은 automator가
이 dict를 받아 DOM에 채운다.
"""

from __future__ import annotations

import re

from ggotaiorder.rpa.models import RpaOrder

# channel(server_call_history.channel_order) → FlowerNT3 주문구분(order_divi) value.
# 라디오 실제 value(라이브 확인): 인터넷 / 전화 / 팩스 / 매장 / 프로그램간 / 기타.
# fill_order_form은 이 value로 라디오를 선택한다.
CHANNEL_TO_ORDER_DIVI = {
    "전화": "전화",
    "가게전화": "전화",
    "핸드폰": "전화",
    "가게음성": "매장",
    "쇼핑몰": "인터넷",
    "인터라넷": "프로그램간",
}
DEFAULT_ORDER_DIVI = "기타"


def channel_to_order_divi(channel: str | None) -> str:
    """channel_order 값 → FlowerNT3 주문구분(order_divi) value. 미상은 '기타'."""
    return CHANNEL_TO_ORDER_DIVI.get((channel or "").strip(), DEFAULT_ORDER_DIVI)


# 상품명 키워드 → 상품분류(sang_divi) 옵션 텍스트. 위에서부터 먼저 맞는 것을 택한다.
# 실제 옵션(라이브): 축하화환/화분/쌀화환/근조화환/동양란/서양란/생화/과일바구니/축하오브제/근조오브제/기타.
_SANG_DIVI_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("쌀화환", "쌀"), "쌀화환"),
    (("근조오브제",), "근조오브제"),
    (("축하오브제", "오브제"), "축하오브제"),
    (("근조화환", "근조", "조화"), "근조화환"),
    (("축하화환", "화환", "개업화환"), "축하화환"),
    (("서양란", "서양", "호접", "심비디움"), "서양란"),
    (("화분", "관엽", "식물"), "화분"),
    (("과일", "과일바구니"), "과일바구니"),
    (("꽃다발", "부케", "꽃바구니", "장미", "생화", "꽃", "바구니"), "생화"),
)


DEFAULT_SANG_DIVI = "기타"

# FlowerNT3 상품분류(sang_divi) select 의 실제 옵션 텍스트(라이브 확인). AI 추출값이
# 이 집합에 속할 때만 신뢰하고, 아니면(오타·자유서술·미상) 키워드 휴리스틱으로 폴백한다.
SANG_DIVI_OPTIONS: frozenset[str] = frozenset({
    "축하화환", "화분", "쌀화환", "근조화환", "동양란", "서양란",
    "생화", "과일바구니", "축하오브제", "근조오브제", "기타",
})


def resolve_sang_divi(order: RpaOrder) -> str:
    """주문의 상품분류를 결정한다. AI 추출값(order.sang_divi)이 유효 옵션이면 그걸
    쓰고, 없거나 목록에 없으면 상품명 키워드 규칙(product_to_sang_divi)으로 폴백한다.

    AI 분류는 STT 전체 맥락을 보므로 키워드보다 정확하지만, 환각·오타 위험이 있어
    유효 옵션 화이트리스트로 검증한다 → 어떤 경우에도 기존 동작보다 나빠지지 않는다.
    """
    ai = (order.sang_divi or "").strip()
    if ai in SANG_DIVI_OPTIONS:
        return ai
    return product_to_sang_divi(order.product_name)


def product_to_sang_divi(product_name: str | None) -> str:
    """상품명 → 상품분류(sang_divi) 옵션 텍스트. 빈 상품명만 '', 그 외 미매칭은 '기타'.

    sang_divi는 FlowerNT 서버 필수값이라 미선택('')이면 "상품분류는 반드시
    선택해주세요"로 등록이 거부된다(라이브 확인). 따라서 키워드 미매칭이어도
    '기타'로 폴백해 등록이 통과되게 한다. 키워드 휴리스틱은 _SANG_DIVI_RULES로 보강.
    """
    n = (product_name or "").strip()
    if not n:
        return ""
    # '동양란'은 '화분' 키워드보다 우선
    if "동양란" in n or "동양" in n:
        return "동양란"
    for keywords, category in _SANG_DIVI_RULES:
        if any(k in n for k in keywords):
            return category
    return DEFAULT_SANG_DIVI


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


def order_to_fields(order: RpaOrder) -> dict[str, str]:
    """order_form2 의 text/textarea name → 값. (radio order_divi는 별도)

    리본 필드(라이브 확인): event_txt=경조사명(경조문구), people_txt=사람명(보내는분),
    msg_text=카드메시지.
    """
    fields: dict[str, str] = {
        "customer_name": order.customer_name or "",
        "customer_hp": order.customer_phone_number or "",
        "sang_name": order.product_name or "",
        "sang_money": normalize_price(order.price),       # 소비정가
        "sang_realMoney": normalize_price(order.price),   # 판매가 = 소비정가 동일
        "receive_name": order.receiver_name or "",
        "receive_hp": order.receiver_phone_number or "",
        "receive_address1": order.delivery_place or "",
        "event_txt": order.ribbon_congratulations or "",
        "people_txt": order.ribbon_sender or "",
        "msg_text": order.card_message or "",
    }
    date, time = split_delivery_datetime(order.delivery_at)
    if date:
        fields["hope_date"] = date
    if time:
        fields["hope_time"] = time
    return fields
