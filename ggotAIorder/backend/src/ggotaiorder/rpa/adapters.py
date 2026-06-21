"""RPA 백업 폴백 어댑터: 항상 미구동으로 보고해 'manual' 백업 경로로 흐른다."""

from __future__ import annotations

import logging

from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)


class ManualOnlyAutomator:
    """RPA 비활성/미지원 프로그램용. is_program_running 항상 False."""

    def is_program_running(self) -> bool:
        return False

    def input_order(self, order: RpaOrder) -> None:  # pragma: no cover - 호출 안 됨
        raise RuntimeError("ManualOnlyAutomator.input_order 는 호출되면 안 됩니다.")


class RoseWebAutomator:
    """Roseweb 어댑터(스텁). 실제 입력 로직은 후속 과제 — 현재는 백업 폴백."""

    def __init__(self, url: str | None, login_id: str | None,
                 login_password: str | None, debug_port: int) -> None:
        self._url = url
        self._login_id = login_id
        self._login_password = login_password
        self._debug_port = debug_port

    def is_program_running(self) -> bool:
        logger.info("RoseWebAutomator 미구현 — 백업(manual) 경로로 처리")
        return False

    def input_order(self, order: RpaOrder) -> None:  # pragma: no cover
        raise NotImplementedError("Roseweb 자동입력은 후속 구현 예정입니다.")
