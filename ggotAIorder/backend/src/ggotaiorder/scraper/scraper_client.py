"""인트라넷 스크래퍼 추상화.

IntranetScraper(Protocol)로 계약을 고정하고, 실제 Playwright 구현은 골격이다.
대상 사이트의 로그인/목록/상세 HTML 구조를 확보해야 셀렉터를 완성할 수 있다(라이브 체크리스트).
"""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.scraper.models import ScrapedOrder

logger = logging.getLogger(__name__)


class IntranetScraper(Protocol):
    """인트라넷에서 신규 주문 목록을 수집하는 계약."""

    def fetch_orders(self, url: str, username: str, password: str) -> list[ScrapedOrder]: ...


class PlaywrightIntranetScraper:
    """Playwright headless 인트라넷 스크래퍼 (골격).

    TODO(라이브): playwright 로그인 → 신규 주문번호 목록 추출 → 상세 페이지에서
    11필드 스크래핑 → ScrapedOrder 목록 반환. 실제 셀렉터는 대상 사이트 확보 후 작성.
    """

    def fetch_orders(self, url: str, username: str, password: str) -> list[ScrapedOrder]:
        logger.warning("[STUB] PlaywrightIntranetScraper.fetch_orders — 실 사이트 미확보")
        raise NotImplementedError(
            "Playwright 인트라넷 스크래핑은 대상 사이트 확보 후 구현됩니다."
        )
