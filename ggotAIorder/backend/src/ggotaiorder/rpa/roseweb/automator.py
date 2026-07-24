"""RoseWebAutomator — 화원박사 ROSEWeb(Delphi 데스크톱 앱)에 주문을 자동 입력한다.

FlowerNT 가 CDP 로 브라우저를 조종하는 것과 달리, 여기는 Windows UI Automation 으로
네이티브 창의 컨트롤을 찾아 `SetFocus()`+`SendKeys()` 로 넣는다. 즉 **입력하는 몇 초 동안
실제 키보드 포커스를 가져간다** — 사장님이 동시에 타이핑하면 충돌한다.

`uiautomation` 은 Windows 전용이자 `[roseweb]` extra 라, **모듈 최상단에서 import 하지
않는다**. factory 가 이 모듈을 import 하므로, 최상단에 두면 리눅스 CI 와 FlowerNT 전용
설치본에서 수집엔진이 아예 못 뜬다(FlowerNT 가 playwright 를 호출 시점에 import 하는 것과
같은 이유). 호출 시점 import 가 실패하면 singleton_macro 가 백업(manual) 경로로 흘린다.
"""

from __future__ import annotations

import logging
import subprocess
import time

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.roseweb import layout

logger = logging.getLogger(__name__)


def _uia():
    """uiautomation 모듈(호출 시점 import). 미설치면 ImportError 가 그대로 올라간다."""
    import uiautomation

    return uiautomation


class RoseWebAutomator:
    """RoseWeb 자동입력. 계약은 `rpa.automator.ProgramAutomator`."""

    def __init__(self, url: str | None = None, login_id: str | None = None,
                 login_password: str | None = None, auto_submit: bool = False) -> None:
        # url/login_id/login_password 는 다른 어댑터와 시그니처를 맞추기 위한 것이다.
        # 화원박사는 실행하면 자동 로그인이라 자격증명을 쓰지 않는다.
        self._auto_submit = bool(auto_submit)

    # --- 창 찾기 --------------------------------------------------------
    def _main_window(self):
        """메인 창(TFmMain). 없으면 None."""
        auto = _uia()
        for w in auto.GetRootControl().GetChildren():
            try:
                if (w.ClassName or "") == layout.MAIN_CLASS:
                    return w
            except Exception:      # 창이 그새 닫히면 속성 접근이 터진다
                continue
        return None

    def _process_running(self) -> bool:
        """roseweb.exe 가 이미 떠 있는가.

        창이 아직 안 뜬 기동 중(스플래시)에 또 실행하면 인스턴스가 둘이 된다.
        판정 실패는 '안 떠 있음'으로 본다 — 그러면 아래 로직이 기존대로 실행을 시도한다.
        """
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {layout.PROC_NAME}.exe", "/NH"],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            logger.debug("RoseWeb 프로세스 확인 실패(%s)", type(exc).__name__)
            return False
        # 한국어 Windows 의 tasklist 는 CP949 로 출력한다. text=True 로 받으면 UTF-8
        # 디코딩이 터져(실측) 결과가 늘 비고, 그러면 이미 떠 있는 RoseWeb 을 또 실행하게
        # 된다. 찾는 문자열이 ASCII 라 디코딩하지 않고 바이트 그대로 뒤진다.
        needle = f"{layout.PROC_NAME}.exe".encode("ascii").lower()
        return needle in (proc.stdout or b"").lower()

    # --- 기동 -----------------------------------------------------------
    def _ensure_running(self, timeout_s: float = 25.0, poll_s: float = 1.0) -> bool:
        """RoseWeb 이 떠 있게 만든다. 이미 떠 있으면 즉시 True."""
        if self._main_window() is not None:
            return True

        if self._process_running():
            logger.info("RoseWeb 프로세스는 있으나 메인 창 미검출 — 기동 대기")
        else:
            logger.info("RoseWeb 미기동 — 실행: %s", layout.EXE_PATH)
            # OCX/DLL 을 상대경로로 찾으므로 반드시 설치 폴더에서 실행해야 한다.
            subprocess.Popen([layout.EXE_PATH], cwd=layout.WORKDIR)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(poll_s)
            win = self._main_window()
            if win is not None:
                logger.info("RoseWeb 기동 확인: %s", (getattr(win, "Name", "") or "")[:60])
                return True
        logger.warning("RoseWeb 기동 확인 실패(%.0f초 대기)", timeout_s)
        return False

    # --- ProgramAutomator 계약 -------------------------------------------
    def is_program_running(self) -> bool:
        try:
            return self._ensure_running()
        except Exception:
            # 여기서 예외를 흘리면 주문이 백업 없이 사라진다(singleton_macro 참조).
            logger.exception("RoseWeb 구동 확인 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        raise NotImplementedError("RoseWeb 자동입력은 Task 5 에서 구현한다.")
