"""서비스 등록 없이 오케스트레이터를 로컬에서 직접 구동한다 (디버그용).

실행: backend\\.venv\\Scripts\\python.exe backend\\run_dev.py
Ctrl+C 로 종료.
"""

from __future__ import annotations

import asyncio

from ggotaiorder.logging_setup import setup_logging
from ggotaiorder.orchestrator import Orchestrator


async def _main() -> None:
    setup_logging()
    orch = Orchestrator()
    try:
        await orch.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        await orch.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
