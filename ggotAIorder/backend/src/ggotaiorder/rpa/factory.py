"""샵 RPA 설정으로부터 알맞은 ProgramAutomator를 생성한다."""

from __future__ import annotations

from ggotaiorder.rpa.adapters import ManualOnlyAutomator, RoseWebAutomator
from ggotaiorder.rpa.automator import ProgramAutomator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings


def build_automator(
    settings: RpaProgramSettings | None, *, debug_port: int
) -> ProgramAutomator:
    if settings is None or not settings.enabled:
        return ManualOnlyAutomator()
    if settings.program_type == "flowernt":
        return FlowerNt3Automator(
            url=settings.url,
            login_id=settings.login_id,
            login_password=settings.login_password,
            auto_submit=settings.auto_submit,
            debug_port=debug_port,
        )
    if settings.program_type == "roseweb":
        return RoseWebAutomator(
            url=settings.url, login_id=settings.login_id,
            login_password=settings.login_password, debug_port=debug_port,
        )
    return ManualOnlyAutomator()
