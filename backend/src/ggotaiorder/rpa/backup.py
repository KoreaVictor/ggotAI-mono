"""관리 프로그램 미구동/입력 실패 시 비상 백업 생성.

PRD 6-5: .xlsx(데이터) + .txt(사람이 읽는 영수증)를 백업 폴더에 생성한다.
사장님이 수동으로 관리 프로그램에 입력할 수 있게 한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

_HEADERS = [
    "주문ID", "꽃집KEY", "꽃집명", "채널", "고객명", "고객전화", "상품명",
    "수량", "가격", "배송일시", "배송지", "받는분", "받는분전화",
    "리본_보내는분", "리본_경조사", "카드메시지",
]


def _row(o: RpaOrder) -> list:
    return [
        o.order_detail_id, o.shop_key, o.shop_name, o.channel,
        o.customer_name, o.customer_phone_number, o.product_name,
        o.quantity, o.price, o.delivery_at, o.delivery_place,
        o.receiver_name, o.receiver_phone_number,
        o.ribbon_sender, o.ribbon_congratulations, o.card_message,
    ]


def _v(value: object) -> str:
    """영수증 표시용: None은 '-'로 렌더(사장님이 읽는 출력)."""
    return "-" if value is None else str(value)


def _receipt_text(o: RpaOrder) -> str:
    return "\n".join([
        "===== ggotAI 주문 영수증 (수동 입력 백업) =====",
        f"주문ID: {o.order_detail_id}",
        f"꽃집: {o.shop_name} (key={o.shop_key})",
        f"채널: {o.channel}",
        f"상품: {o.product_name} x {o.quantity} ({o.price}원)",
        f"배송일시: {_v(o.delivery_at)}",
        f"배송지: {_v(o.delivery_place)}",
        f"받는분: {_v(o.receiver_name)} / {_v(o.receiver_phone_number)}",
        f"고객: {o.customer_name} / {o.customer_phone_number}",
        f"리본(보내는분): {_v(o.ribbon_sender)}",
        f"리본(경조사): {_v(o.ribbon_congratulations)}",
        f"카드메시지: {_v(o.card_message)}",
        "==========================================",
    ])


class BackupWriter:
    """주문 1건을 .xlsx + .txt 영수증으로 백업 폴더에 기록한다."""

    def __init__(self, backup_dir: Path) -> None:
        self._dir = Path(backup_dir)

    def write(self, order: RpaOrder) -> tuple[Path, Path]:
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        base = f"{order.shop_key}_{order.order_detail_id}_{stamp}"
        xlsx_path = self._dir / f"{base}.xlsx"
        txt_path = self._dir / f"{base}.txt"

        wb = Workbook()
        ws = wb.active
        ws.title = "주문"
        ws.append(_HEADERS)
        ws.append(_row(order))
        wb.save(xlsx_path)

        txt_path.write_text(_receipt_text(order), encoding="utf-8")

        logger.info("RPA 백업 생성 id=%s -> %s", order.order_detail_id, base)
        return xlsx_path, txt_path
