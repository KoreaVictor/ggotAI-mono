"""RPA 백업 폴백 어댑터: 항상 미구동으로 보고해 'manual' 백업 경로로 흐른다."""

from __future__ import annotations

from ggotaiorder.rpa.models import RpaOrder


class ManualOnlyAutomator:
    """RPA 비활성/미지원 프로그램용. is_program_running 항상 False."""

    def is_program_running(self) -> bool:
        return False

    def input_order(self, order: RpaOrder) -> None:  # pragma: no cover - 호출 안 됨
        raise RuntimeError("ManualOnlyAutomator.input_order 는 호출되면 안 됩니다.")


# RoseWebAutomator 스텁은 rpa.roseweb.automator 의 실제 구현으로 대체됨(factory 참조).
