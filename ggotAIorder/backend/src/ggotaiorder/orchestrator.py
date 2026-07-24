"""백엔드 서브시스템 오케스트레이터 (단일 asyncio 이벤트 루프).

FastAPI(uvicorn)·Realtime 리스너·APScheduler(크롤러)를 한 이벤트 루프에서
구동한다. 수집 on/off는 paused 플래그로 제어한다(서비스 stop/start 대응).
"""

from __future__ import annotations

import logging

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ggotaiorder.api.routes import create_app
from ggotaiorder.config import load_config
from ggotaiorder.core.heartbeat import record_heartbeat
from ggotaiorder.mall.collector import poll_once as mall_poll_once
from ggotaiorder.mall.confirm_scanner import MallConfirmScanner
from ggotaiorder.pipeline.catchup import CatchupScanner
from ggotaiorder.realtime.listener import RealtimeListener
from ggotaiorder.rpa.retry import RpaRetryScanner
from ggotaiorder.scraper.crawler import poll_once

logger = logging.getLogger(__name__)

# 크롤러 폴링 기본 주기(분). 후속: setting_info 값으로 동적 재설정.
_DEFAULT_INTRANET_INTERVAL_MIN = 30

# catch-up 스캔 주기(분). 부팅 1회 후 이 간격으로 미처리분을 따라잡는다.
_CATCHUP_INTERVAL_MIN = 30

# manual(미구동) RPA 주문 재시도 주기(분). 상한(retry.RPA_MAX_ATTEMPTS)까지 따라잡는다.
_RPA_RETRY_INTERVAL_MIN = 5

# 스마트스토어 커머스API 폴링 주기(분). 후속: setting_info 값으로 동적화.
_SMARTSTORE_INTERVAL_MIN = 10

# 발주확인 스캔 주기(분). RPA 성공분을 이 간격으로 승인한다.
_MALL_CONFIRM_INTERVAL_MIN = 5

# 하트비트 주기(초). 상황판은 최근 90초 내 신호로 '가동중'을 판정한다(get_dashboard).
_HEARTBEAT_INTERVAL_SEC = 20

# realtime 연결 watchdog 주기(초). realtime-py 가 서버발 1001 후 자가복구를 못 해
# 소켓이 죽은 채 남는 wedge 를 감지·재구독하기 위한 주기(하트비트 25초보다 촘촘히).
_REALTIME_WATCHDOG_INTERVAL_SEC = 30


class Orchestrator:
    """모든 백엔드 서브시스템의 수명주기를 관리한다."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._host = host
        self._port = port
        self._paused = False
        self._shop_key: int | None = None  # start() 시점에 로딩(테스트는 start 미호출)
        self._listener = RealtimeListener()
        self._scanner = CatchupScanner()
        self._rpa_retry = RpaRetryScanner()
        self._mall_confirm = MallConfirmScanner()
        self._scheduler = AsyncIOScheduler()
        self._server: uvicorn.Server | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """수집을 일시정지한다 (net stop 대응). 프로세스는 유지."""
        self._paused = True
        logger.info("수집 일시정지 (paused=True)")

    def resume(self) -> None:
        """수집을 재개한다 (net start 대응)."""
        self._paused = False
        logger.info("수집 재개 (paused=False)")

    async def _scheduled_poll(self) -> None:
        """일시정지 상태가 아니면 크롤러를 1회 폴링한다."""
        if self._paused:
            logger.debug("paused 상태 — 크롤링 스킵")
            return
        await poll_once()

    async def _scheduled_catchup(self) -> None:
        """일시정지가 아니면 catch-up 스캔을 1회 수행한다(누락분 따라잡기)."""
        if self._paused:
            logger.debug("paused 상태 — catch-up 스킵")
            return
        try:
            await self._scanner.scan_once()
        except Exception:
            logger.exception("catch-up 스캔 실패(다음 주기에 재시도)")

    async def _scheduled_rpa_retry(self) -> None:
        """일시정지가 아니면 manual RPA 주문을 1회 재시도 스캔한다."""
        if self._paused:
            logger.debug("paused 상태 — RPA 재시도 스킵")
            return
        try:
            await self._rpa_retry.scan_once()
        except Exception:
            logger.exception("RPA 재시도 스캔 실패(다음 주기에 재시도)")

    async def _scheduled_mall_poll(self) -> None:
        """일시정지가 아니면 스마트스토어를 1회 폴링한다."""
        if self._paused:
            logger.debug("paused 상태 — 스마트스토어 폴링 스킵")
            return
        try:
            await mall_poll_once()
        except Exception:
            logger.exception("스마트스토어 폴링 실패(다음 주기에 재시도)")

    async def _scheduled_mall_confirm(self) -> None:
        """일시정지가 아니면 발주확인 스캔을 1회 수행한다."""
        if self._paused:
            logger.debug("paused 상태 — 발주확인 스킵")
            return
        try:
            await self._mall_confirm.scan_once()
        except Exception:
            logger.exception("발주확인 스캔 실패(다음 주기에 재시도)")

    async def _scheduled_realtime_watchdog(self) -> None:
        """realtime 연결이 wedge 면 재구독한다(paused 와 무관 — 연결 유지가 기준).

        realtime-py 2.5.3 은 서버발 1001(going away)에 재연결을 못 걸어, 재시작 전까지
        실시간 처리가 죽고 catch-up 안전망만 남는다(2026-07-23 실측 14시간 wedge).
        """
        try:
            await self._listener.ensure_healthy()
        except Exception:
            logger.exception("realtime watchdog 실패(다음 주기에 재시도)")

    async def _heartbeat(self) -> None:
        """수집엔진 생존 신호를 기록한다(paused 와 무관 — 프로세스 생존이 기준)."""
        if self._shop_key is None:
            return
        try:
            record_heartbeat(self._shop_key)
        except Exception:
            logger.exception("하트비트 기록 실패(다음 주기 재시도)")

    async def start(self) -> None:
        """모든 서브시스템을 기동하고 종료될 때까지 대기한다."""
        logger.info("오케스트레이터 시작")

        self._shop_key = load_config().shop_key

        await self._listener.start()

        self._scheduler.add_job(
            self._scheduled_poll,
            "interval",
            minutes=_DEFAULT_INTRANET_INTERVAL_MIN,
            id="intranet_poll",
        )
        # 부팅 직후 1회: 스케줄러가 시작되면 즉시 실행(오프라인/절전 누락분 따라잡기).
        # 일회성 잡으로 위임해 uvicorn/스케줄러 기동을 블로킹하지 않는다.
        # (리스너 구독은 이미 위에서 끝났으므로, 스캔 중 도착분은 Realtime이 받고 in-flight로 중복 방지.)
        self._scheduler.add_job(
            self._scheduled_catchup,
            "date",
            id="catchup_boot",
        )
        self._scheduler.add_job(
            self._scheduled_catchup,
            "interval",
            minutes=_CATCHUP_INTERVAL_MIN,
            id="catchup_scan",
            max_instances=1,
            coalesce=True,
        )
        # manual(미구동) RPA 주문 재시도: 부팅 1회 + 주기적으로(브라우저 복구 시 자동 등록).
        self._scheduler.add_job(self._scheduled_rpa_retry, "date", id="rpa_retry_boot")
        self._scheduler.add_job(
            self._scheduled_rpa_retry,
            "interval",
            minutes=_RPA_RETRY_INTERVAL_MIN,
            id="rpa_retry",
            max_instances=1,
            coalesce=True,
        )
        # 스마트스토어 커머스API 폴링(신규주문 수집).
        self._scheduler.add_job(
            self._scheduled_mall_poll,
            "interval",
            minutes=_SMARTSTORE_INTERVAL_MIN,
            id="smartstore_poll",
            max_instances=1,
            coalesce=True,
        )
        # 발주확인: 부팅 1회 + 주기적으로(RPA 성공분 승인).
        self._scheduler.add_job(self._scheduled_mall_confirm, "date", id="mall_confirm_boot")
        self._scheduler.add_job(
            self._scheduled_mall_confirm,
            "interval",
            minutes=_MALL_CONFIRM_INTERVAL_MIN,
            id="mall_confirm",
            max_instances=1,
            coalesce=True,
        )
        # realtime watchdog: 연결 wedge 를 주기적으로 감지·재구독(실시간 처리 되살림).
        self._scheduler.add_job(
            self._scheduled_realtime_watchdog,
            "interval",
            seconds=_REALTIME_WATCHDOG_INTERVAL_SEC,
            id="realtime_watchdog",
            max_instances=1,
            coalesce=True,
        )
        # 하트비트: 기동 직후 1회 + 주기적으로. 상황판 '가동중' 표시의 근거.
        self._scheduler.add_job(self._heartbeat, "date", id="heartbeat_boot")
        self._scheduler.add_job(
            self._heartbeat,
            "interval",
            seconds=_HEARTBEAT_INTERVAL_SEC,
            id="heartbeat",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()

        config = uvicorn.Config(
            create_app(), host=self._host, port=self._port, log_level="info"
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()  # 종료 신호 전까지 블로킹

    async def stop(self) -> None:
        """모든 서브시스템을 정상 종료한다."""
        logger.info("오케스트레이터 종료")
        if self._server is not None:
            self._server.should_exit = True
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        await self._listener.stop()
