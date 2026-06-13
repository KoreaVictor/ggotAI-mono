"""서비스 등록 없이 오케스트레이터를 로컬에서 직접 구동한다 (디버그용).

실행: backend\\.venv\\Scripts\\python.exe backend\\run_dev.py
Ctrl+C 로 종료.
"""

from __future__ import annotations

import os
import sys

# pythonw.exe(콘솔 없음)로 실행되면 sys.stdout/stderr 가 None 이라, uvicorn·로깅이
# 표준 스트림에 쓰려다 크래시한다(작업 스케줄러 백그라운드 실행). None 이면 devnull 로 보정.
# (실제 로그는 logging_setup 의 회전 파일 핸들러로 남는다)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import asyncio

from ggotaiorder.logging_setup import setup_logging
from ggotaiorder.orchestrator import Orchestrator


async def _main() -> None:
    setup_logging()
    orch = Orchestrator()
    try:
        await orch.start()
    finally:
        await orch.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
