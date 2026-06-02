"""pywin32 기반 Windows Service 래퍼.

서비스명 'ggotAIorder'. SvcDoRun에서 워커 스레드로 asyncio 이벤트 루프를
돌리며 Orchestrator를 구동하고, SvcStop에서 정상 종료를 요청한다.

설치(관리자 PowerShell):
    backend\\.venv\\Scripts\\python.exe -m ggotaiorder.service install
    backend\\.venv\\Scripts\\python.exe -m ggotaiorder.service start
"""

from __future__ import annotations

import asyncio
import logging

import servicemanager
import win32event
import win32service
import win32serviceutil

from ggotaiorder.logging_setup import setup_logging
from ggotaiorder.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class GgotAIOrderService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ggotAIorder"
    _svc_display_name_ = "ggotAIorder 주문 수집 서비스"
    _svc_description_ = "다중 채널 주문 수집·정형화·자동입력 백그라운드 서비스."

    def __init__(self, args) -> None:
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orchestrator: Orchestrator | None = None

    def SvcStop(self) -> None:
        """SCM 정지 요청 처리 (net stop)."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._loop is not None and self._orchestrator is not None:
            asyncio.run_coroutine_threadsafe(self._orchestrator.stop(), self._loop)
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self) -> None:
        """SCM 시작 요청 처리 (net start)."""
        setup_logging()
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._orchestrator = Orchestrator()
        try:
            self._loop.run_until_complete(self._orchestrator.start())
        finally:
            self._loop.close()


def main() -> None:
    win32serviceutil.HandleCommandLine(GgotAIOrderService)


if __name__ == "__main__":
    main()
