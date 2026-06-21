"""관리 프로그램 GUI 자동화 계약.

ProgramAutomator(Protocol)로 계약만 고정한다. 실제 구현체는 프로그램별 어댑터
(rpa.flowernt3.automator.FlowerNt3Automator 등)이며 rpa.factory가 샵 설정으로 선택한다.
미지원/비활성 샵은 rpa.adapters.ManualOnlyAutomator로 백업('manual') 경로로 흐른다.
"""

from __future__ import annotations

from typing import Protocol

from ggotaiorder.rpa.models import RpaOrder


class ProgramAutomator(Protocol):
    """꽃집 관리 프로그램에 주문을 입력하는 계약."""

    def is_program_running(self) -> bool: ...

    def input_order(self, order: RpaOrder) -> None: ...
