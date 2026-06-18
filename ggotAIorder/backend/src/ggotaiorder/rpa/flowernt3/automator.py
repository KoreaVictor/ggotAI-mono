"""FlowerNt3Automator — 후속 태스크에서 Playwright 본구현. 우선 import 가능한 골격."""

from __future__ import annotations

from ggotaiorder.rpa.models import RpaOrder


class FlowerNt3Automator:
    def __init__(self, *, url, login_id, login_password, auto_submit, debug_port):
        self.url = url
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port

    def is_program_running(self) -> bool:
        return False

    def input_order(self, order: RpaOrder) -> None:
        raise NotImplementedError
