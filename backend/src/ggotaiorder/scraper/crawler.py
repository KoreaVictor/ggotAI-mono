"""인트라넷 정기 폴링 크롤러 (스텁).

PRD 6-3: APScheduler 주기로 Playwright Headless 로그인 → 신규 주문 목록 폴링
→ 중복 검증 → server_call_history INSERT(stt_text=원문,
audio_file_name='INTRANET_CRAWLED') → AI 패스 → order_details INSERT(ready)
→ rpa.enqueue. 연속 3회 실패 시 비상 알림.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

INTRANET_AUDIO_MARKER = "INTRANET_CRAWLED"


async def poll_once() -> None:
    """[스텁] 인트라넷을 1회 폴링한다 (APScheduler가 주기 호출).

    TODO(후속):
      1. setting_info 에서 intranet_url/id/password(복호화) 로딩
      2. Playwright 로그인 세션 획득
      3. 신규 주문번호 추출 → DB 교차검증(중복 제거)
      4. 신규 건 상세 스크래핑(11필드)
      5. server_call_history + order_details(ready) INSERT
      6. await rpa.enqueue(order_detail_id)
      7. 연속 3회 실패 시 notifier 비상 알림
    """
    logger.warning("[STUB] scraper.poll_once() — 크롤링 미구현")
