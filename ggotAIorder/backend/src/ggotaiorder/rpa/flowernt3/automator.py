"""FlowerNt3Automator — 전용 프로필 Chrome(CDP)에 붙어 주문폼을 채우고 등록한다.

singleton_macro가 asyncio.to_thread로 동기 호출하므로 sync Playwright를 쓰며,
매 호출마다 connect_over_cdp로 연결→작업→해제를 완결한다(스레드 귀속 회피).
"""

from __future__ import annotations

import logging

from ggotaiorder.rpa.flowernt3 import mapping
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

ORDER_FRAME_MARK = "order/order3.asp"
ORDER_PATH = "/order/order3.asp"


def _cdp_url(debug_port: int) -> str:
    return f"http://localhost:{debug_port}"


def fill_order_form(frame, order: RpaOrder, *, auto_submit: bool) -> None:
    """order_form2 프레임에 주문을 채우고, auto_submit이면 등록까지 실행한다."""
    # 1) 주문구분 라디오: 라벨 텍스트로 선택(인코딩 안전)
    target = mapping.channel_to_order_divi(order.channel)
    frame.evaluate(
        """(label) => {
            const radios = Array.from(document.getElementsByName('order_divi'));
            for (const r of radios) {
                const t = (r.parentElement?.innerText || '').trim();
                if (t.includes(label)) { r.click(); return true; }
            }
            return false;
        }""",
        target,
    )
    # 2) text/textarea 채움
    for name, value in mapping.order_to_fields(order).items():
        if value == "":
            continue
        sel = f"[name={name}]"
        el = frame.query_selector(sel)
        if el is None:
            logger.debug("FlowerNT3 필드 없음(스킵): %s", name)
            continue
        el.fill(value)
    # 3) 등록
    if auto_submit:
        frame.evaluate("() => { if (typeof submit_reg === 'function') submit_reg(); }")


class FlowerNt3Automator:
    def __init__(self, *, url, login_id, login_password, auto_submit, debug_port):
        self.url = url or "https://www.flowernt.com"
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port

    # --- 세션 ---
    def _connect(self, p):
        return p.chromium.connect_over_cdp(_cdp_url(self.debug_port))

    def _logged_in(self, page) -> bool:
        """로그인 페이지로 튕기지 않으면 로그인 상태로 간주."""
        url = (page.url or "").lower()
        return "login" not in url and "flowernt.com" in url

    def _order_frame(self, page):
        for f in page.frames:
            if ORDER_FRAME_MARK in (f.url or ""):
                return f
        return None

    def is_program_running(self) -> bool:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = self._connect(p)
                ctx = browser.contexts[0] if browser.contexts else None
                if ctx is None or not ctx.pages:
                    page = (ctx or browser.new_context()).new_page()
                else:
                    page = ctx.pages[0]
                if not self._logged_in(page):
                    ok = self._try_login(page)
                    browser.close()
                    return ok
                browser.close()
                return True
        except Exception:
            logger.info("FlowerNT3 CDP 연결 실패 — 미구동으로 처리(백업)")
            return False

    def _try_login(self, page) -> bool:
        """저장된 자격증명으로 로그인 시도. 실패/자격증명 없음이면 False."""
        if not (self.login_id and self.login_password):
            return False
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            # FlowerNT 로그인 폼 필드명은 라이브에서 확정(후속). 가능한 후보 시도.
            page.fill("input[name=member_id], input[name=user_id], input[name=id]",
                      self.login_id)
            page.fill("input[type=password]", self.login_password)
            page.keyboard.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            return self._logged_in(page)
        except Exception:
            logger.warning("FlowerNT3 자동 로그인 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = self._connect(p)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            # 주문입력 프레임을 신규폼으로 새로고침
            frame = self._order_frame(page)
            if frame is not None:
                frame.goto(self.url.rstrip("/") + ORDER_PATH,
                           wait_until="domcontentloaded")
                frame = self._order_frame(page)
            else:
                page.goto(self.url.rstrip("/") + ORDER_PATH,
                          wait_until="domcontentloaded")
                frame = self._order_frame(page) or page.main_frame
            fill_order_form(frame, order, auto_submit=self.auto_submit)
            page.wait_for_timeout(800)  # 등록 처리 대기
            browser.close()
