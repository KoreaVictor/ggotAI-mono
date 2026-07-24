"""샵 RPA 설정으로부터 알맞은 ProgramAutomator를 생성한다."""

from __future__ import annotations

from ggotaiorder.rpa.adapters import ManualOnlyAutomator
from ggotaiorder.rpa.automator import ProgramAutomator
from ggotaiorder.rpa.flowernt3.automator import FlowerNt3Automator
from ggotaiorder.rpa.program_settings import RpaProgramSettings
from ggotaiorder.rpa.roseweb.automator import RoseWebAutomator


def build_automator(
    settings: RpaProgramSettings | None,
    *,
    debug_port: int,
    profile_dir: str | None = None,
    chrome_path: str | None = None,
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
            profile_dir=profile_dir,
            chrome_path=chrome_path,
        )
    if settings.program_type == "roseweb":
        # debug_port/profile_dir/chrome_path 는 브라우저용이라 RoseWeb 은 안 쓴다.
        # RoseWeb 은 실행 시 자동 로그인이라 자격증명도 쓰지 않는다.
        return RoseWebAutomator(auto_submit=settings.auto_submit)
    return ManualOnlyAutomator()
