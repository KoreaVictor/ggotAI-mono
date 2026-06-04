"""관리 프로그램 GUI 자동화 추상화.

ProgramAutomator(Protocol)로 계약을 고정하고, 실제 Windows 구현은 골격이다.
대상 꽃집 관리 프로그램의 창 제목·입력 폼 Tab 순서를 확보해야 완성할 수 있다(라이브 체크리스트).
"""

from __future__ import annotations

import logging
from typing import Protocol

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class ProgramAutomator(Protocol):
    """꽃집 관리 프로그램에 주문을 입력하는 계약."""

    def is_program_running(self) -> bool: ...

    def input_order(self, order: RpaOrder) -> None: ...


class WindowsProgramAutomator:
    """Windows 관리 프로그램 GUI 자동화 (골격).

    라이브 전엔 is_program_running()이 항상 False를 반환해 안전하게 백업 경로로 흐른다.
    """

    def is_program_running(self) -> bool:
        # TODO(라이브): pygetwindow로 관리 프로그램 창 탐색. 실 프로그램 창 제목 확보 후.
        logger.debug("[STUB] WindowsProgramAutomator.is_program_running -> False")
        return False

    def input_order(self, order: RpaOrder) -> None:
        # TODO(라이브): pyperclip 클립보드 + Tab 키 시퀀스 입력. 실 프로그램 UI 확보 후.
        logger.warning("[STUB] WindowsProgramAutomator.input_order — 실 프로그램 미확보")
        raise NotImplementedError(
            "관리 프로그램 GUI 입력은 대상 프로그램 확보 후 구현됩니다."
        )
