"""인트라넷 정기 폴링 크롤러 (오케스트레이션).

PRD 6-3: 주기적으로 인트라넷에서 신규 주문을 수집해 server_call_history +
order_details(rpa_status='ready')로 직접 적재(AI 패스)하고 rpa.enqueue 한다.
연속 3회 스크래핑 실패 시 비상 알림을 보낸다. 실제 사이트 상호작용은
IntranetScraper(Protocol) 뒤로 추상화한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import decrypt
from ggotaiorder.notifier.sms_sender import send as notifier_send
from ggotaiorder.rpa.singleton_macro import enqueue
from ggotaiorder.scraper.models import INTRANET_CHANNEL, IntranetShop, ScrapedOrder
from ggotaiorder.scraper.repository import IntranetRepository, SupabaseIntranetRepository
from ggotaiorder.scraper.scraper_client import IntranetScraper, PlaywrightIntranetScraper

logger = logging.getLogger(__name__)

INTRANET_AUDIO_MARKER = "INTRANET_CRAWLED"

# 연속 스크래핑 실패가 이 값에 도달하면 비상 알림 (PRD 6-3)
_FAILURE_THRESHOLD = 3

# shop_key -> 연속 실패 횟수
_failure_counts: dict[int, int] = {}


async def _default_notify(shop_key: int) -> None:
    """기본 비상 알림: notifier 실패 템플릿으로 발송."""
    await notifier_send(shop_key, channel=INTRANET_CHANNEL, count=0, success=False)


def _call_record(shop: IntranetShop, order: ScrapedOrder) -> dict:
    now = datetime.now()
    return {
        "channel_order": INTRANET_CHANNEL,
        "channel_classification": order.order_no,
        "shop_key": shop.shop_key,
        "shop_name": shop.shop_name,
        "customer_name": "신규",
        "customer_phone_number": "",
        "call_date": now.strftime("%Y-%m-%d"),
        "call_time": now.strftime("%H:%M:%S"),
        "duration_seconds": 0,
        "audio_file_name": INTRANET_AUDIO_MARKER,
        "stt_text": order.raw_text,
        "is_order": "Y",
    }


def _order_payload(shop: IntranetShop, order: ScrapedOrder, call_history_id: int) -> dict:
    f = order.fields
    return {
        "call_history_id": call_history_id,
        "shop_key": shop.shop_key,
        "shop_name": shop.shop_name,
        "customer_name": f.customer_name or "신규",
        "customer_phone_number": f.customer_phone_number or "",
        "product_name": f.product_name,
        "quantity": f.quantity if f.quantity is not None else 1,
        "price": f.price if f.price is not None else 0,
        "delivery_at": f.delivery_at,
        "delivery_place": f.delivery_place,
        "receiver_name": f.receiver_name,
        "receiver_phone_number": f.receiver_phone_number,
        "ribbon_congratulations": f.ribbon_congratulations,
        "card_message": f.card_message,
        "rpa_status": "ready",
    }


async def _handle_failure(shop_key: int, notify) -> None:
    count = _failure_counts.get(shop_key, 0) + 1
    _failure_counts[shop_key] = count
    logger.warning("인트라넷 스크래핑 실패 shop_key=%s (연속 %s회)", shop_key, count)
    if count >= _FAILURE_THRESHOLD:
        await notify(shop_key)
        _failure_counts[shop_key] = 0


async def poll_once(
    *,
    repo: IntranetRepository | None = None,
    scraper: IntranetScraper | None = None,
    notify=None,
) -> None:
    """인트라넷을 1회 폴링한다 (APScheduler가 주기 호출)."""
    repo = repo or SupabaseIntranetRepository()
    scraper = scraper or PlaywrightIntranetScraper()
    notify = notify or _default_notify

    shops = await asyncio.to_thread(repo.list_intranet_shops)
    cfg = load_config()

    for shop in shops:
        try:
            password = decrypt(shop.enc_password, cfg.aes_encryption_key)
            orders = await asyncio.to_thread(
                scraper.fetch_orders, shop.url, shop.username, password
            )
        except Exception:
            logger.exception("인트라넷 수집 실패 shop_key=%s", shop.shop_key)
            await _handle_failure(shop.shop_key, notify)
            continue

        _failure_counts[shop.shop_key] = 0

        for order in orders:
            try:
                if await asyncio.to_thread(repo.order_exists, shop.shop_key, order.order_no):
                    continue
                call_id = await asyncio.to_thread(
                    repo.insert_call_history, _call_record(shop, order)
                )
                order_id = await asyncio.to_thread(
                    repo.insert_order_details, _order_payload(shop, order, call_id)
                )
                await enqueue(order_id)
            except Exception:
                logger.exception(
                    "인트라넷 주문 적재 실패 shop_key=%s order_no=%s",
                    shop.shop_key, order.order_no,
                )
