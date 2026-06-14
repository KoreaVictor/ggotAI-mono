"""Supabase Realtime 감시.

PRD 6-2: public.server_call_history 의 INSERT 이벤트를 구독하여, 채널이
'핸드폰'/'가게음성'인 신규 행에 대해서만 pipeline.process 를 예약한다.
('가게전화'는 api가, '인터라넷'은 크롤러가 직접 처리 → 이중 처리 방지)
"""

from __future__ import annotations

import asyncio
import logging

from supabase import acreate_client

from ggotaiorder.config import load_config
from ggotaiorder.pipeline.engine import REALTIME_CHANNELS, process

logger = logging.getLogger(__name__)


class RealtimeListener:
    """server_call_history INSERT 구독 리스너.

    Realtime 은 supabase-py 의 비동기 클라이언트에서만 동작하므로(sync 클라이언트는
    NotImplementedError) acreate_client 로 별도 async 클라이언트를 만들어 구독한다.
    """

    def __init__(self, shop_key: int | None = None) -> None:
        self._client = None
        self._channel = None
        self._tasks: set[asyncio.Task] = set()
        # None 이면 start() 에서 config 로부터 해석한다(테스트는 명시 주입).
        self._shop_key = shop_key

    async def start(self) -> None:
        """Realtime 채널 구독을 시작한다."""
        cfg = load_config()
        if self._shop_key is None:
            self._shop_key = cfg.shop_key
        self._client = await acreate_client(
            cfg.supabase_url, cfg.supabase_service_role_key
        )
        self._channel = self._client.channel("server_call_history_inserts")
        # 서버측 필터: 내 가게(shop_key) INSERT 만 푸시받는다(멀티샵 교차처리 차단).
        self._channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="server_call_history",
            filter=f"shop_key=eq.{self._shop_key}",
            callback=self._on_message,
        )
        await self._channel.subscribe()
        logger.info(
            "Realtime 구독 시작: server_call_history INSERT (shop_key=%s)",
            self._shop_key,
        )

    async def stop(self) -> None:
        """구독을 해제하고 async 클라이언트 소켓을 닫는다."""
        if self._channel is not None:
            await self._channel.unsubscribe()
            self._channel = None
        if self._client is not None:
            try:
                await self._client.realtime.close()
            except Exception:  # noqa: BLE001 - 종료 best-effort
                logger.debug("realtime close 중 예외(무시)", exc_info=True)
            self._client = None
        logger.info("Realtime 구독 해제")

    def _on_message(self, payload: dict) -> None:
        """raw Realtime 메시지에서 record를 방어적으로 추출해 처리로 넘긴다."""
        try:
            record = (
                payload.get("data", {}).get("record")
                or payload.get("record")
                or payload.get("new")
            )
            if record:
                self._process_record(record)
            else:
                logger.warning("Realtime 메시지에서 record 추출 실패(빈/누락): %s", payload)
        except Exception:  # noqa: BLE001 - 구독 유지를 위해 콜백 예외 흡수
            logger.exception("Realtime 콜백 처리 실패")

    def _on_task_done(self, task: "asyncio.Task") -> None:
        """완료된 process 태스크를 정리하고, 실패 시 즉시 로깅한다."""
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Realtime process 태스크 실패", exc_info=task.exception()
            )

    def _process_record(self, record: dict) -> None:
        """채널이 핸드폰/가게음성이고 내 가게(shop_key)면 process(id)를 예약한다."""
        channel = record.get("channel_order")
        call_history_id = record.get("id")
        # 방어적 재확인: 서버측 필터가 어떤 이유로 적용 안 됐어도 남의 가게는 skip.
        # (self._shop_key 가 None 이면 필터 미설정 — 단일샵 하위호환으로 전건 통과.)
        if self._shop_key is not None and record.get("shop_key") != self._shop_key:
            logger.debug(
                "Realtime skip(타 shop): shop_key=%s id=%s",
                record.get("shop_key"),
                call_history_id,
            )
            return
        if channel in REALTIME_CHANNELS and call_history_id is not None:
            task = asyncio.create_task(process(call_history_id))
            self._tasks.add(task)
            task.add_done_callback(self._on_task_done)
        else:
            logger.debug(
                "Realtime skip: channel=%s id=%s", channel, call_history_id
            )
