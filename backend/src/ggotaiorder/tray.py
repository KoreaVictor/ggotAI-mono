"""pystray 기반 시스템 트레이 아이콘.

상태: 🟢 수집 중 / 🔴 수집 중지. 우클릭 메뉴: 상황판 열기 / 주문수집 상태 /
ggotAIorder 정보. 더블클릭 시 ggotAIya UI 호출(후속).
"""

from __future__ import annotations

import logging

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _make_status_image(running: bool) -> Image.Image:
    """상태 색상 원(🟢/🔴)을 그린 32x32 아이콘 이미지를 생성한다."""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (40, 200, 80) if running else (220, 50, 50)
    draw.ellipse((4, 4, 28, 28), fill=color)
    return img


def build_tray(running: bool = True) -> pystray.Icon:
    """트레이 아이콘 객체를 생성해 반환한다 (run()은 호출측에서)."""
    menu = pystray.Menu(
        pystray.MenuItem("상황판 열기", _on_open_dashboard, default=True),
        pystray.MenuItem(
            lambda item: "🟢 주문 수집 중" if running else "🔴 주문 수집 중지",
            None,
            enabled=False,
        ),
        pystray.MenuItem("ggotAIorder 정보", _on_about),
    )
    return pystray.Icon(
        "ggotAIorder",
        icon=_make_status_image(running),
        title="ggotAIorder",
        menu=menu,
    )


def _on_open_dashboard(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """[스텁] ggotAIya UI 호출. TODO(후속): Electron 앱 실행/포커스."""
    logger.warning("[STUB] 상황판 열기 클릭")


def _on_about(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    logger.info("ggotAIorder v0.1.0")
