"""FlowerNt3Automator — 전용 프로필 Chrome(CDP)에 붙어 주문폼을 채우고 등록한다.

singleton_macro가 asyncio.to_thread로 동기 호출하므로 sync Playwright를 쓰며,
매 호출마다 connect_over_cdp로 연결→작업→해제를 완결한다(스레드 귀속 회피).
connect_over_cdp 브라우저는 sync_playwright 컨텍스트가 닫아주지 않으므로 모든
경로에서 try/finally로 browser.close()를 보장한다.
"""

from __future__ import annotations

import logging

from ggotaiorder.rpa.flowernt3 import mapping
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

ORDER_FRAME_MARK = "order/order3.asp"
ORDER_PATH = "/order/order3.asp"


def _cdp_url(debug_port: int) -> str:
    # localhost는 ::1(IPv6)로 풀려 CDP 연결이 거부될 수 있어 127.0.0.1로 고정.
    return f"http://127.0.0.1:{debug_port}"


def fill_order_form(frame, order: RpaOrder, *, auto_submit: bool) -> None:
    """order_form2 프레임에 주문을 채우고, auto_submit이면 등록까지 실행한다.

    auto_submit인데 submit_reg()를 찾지 못하면 RuntimeError를 던진다 — 무음으로
    'success' 처리되어 주문이 유실되는 것을 막기 위함(호출자가 백업+fail로 처리).
    """
    # 1) 주문구분 라디오: value 속성으로 선택(라이브 확인 — 라벨 텍스트 노드 없음, value에 한글)
    target = mapping.channel_to_order_divi(order.channel)
    frame.evaluate(
        """(val) => {
            const radios = Array.from(document.getElementsByName('order_divi'));
            for (const r of radios) {
                if (r.value === val) { r.click(); return true; }
            }
            return false;
        }""",
        target,
    )
    # 1-b) 상품분류(sang_divi) select: 상품명 키워드로 분류해 옵션 텍스트로 선택(매칭 없으면 미선택)
    category = mapping.product_to_sang_divi(order.product_name)
    if category:
        try:
            frame.select_option("select[name=sang_divi]", label=category)
        except Exception:
            logger.debug("FlowerNT3 상품분류 옵션 매칭 실패(미선택): %s", category)
    # 2) text/textarea 채움. 읽기전용(달력 등) 필드는 fill()이 막히므로 JS로 값+이벤트 주입.
    for name, value in mapping.order_to_fields(order).items():
        if value == "":
            continue
        el = frame.query_selector(f"[name={name}]")
        if el is None:
            logger.debug("FlowerNT3 필드 없음(스킵): %s", name)
            continue
        editable = el.evaluate("e => !e.readOnly && !e.disabled")
        if editable:
            el.fill(value)
        else:
            frame.evaluate(
                """([name, val]) => {
                    const e = document.getElementsByName(name)[0];
                    if (!e) return;
                    e.value = val;
                    e.dispatchEvent(new Event('input', { bubbles: true }));
                    e.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                [name, value],
            )
    # 3) 등록 — submit_reg 호출 여부를 반환받아 미발견 시 실패로 간주
    if auto_submit:
        called = frame.evaluate(
            "() => { if (typeof submit_reg === 'function') { submit_reg(); return true; }"
            " return false; }"
        )
        if not called:
            raise RuntimeError(
                "FlowerNT3 submit_reg() 미발견 — 등록 실패(폼/프레임 확인 필요)"
            )


class FlowerNt3Automator:
    def __init__(self, *, url, login_id, login_password, auto_submit, debug_port):
        # FlowerNT는 모든 가게가 동일한 flowernt.com을 쓰므로 미설정 시 기본 도메인이 곧 정답.
        self.url = url or "https://www.flowernt.com"
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port

    # --- 세션 ---
    def _connect(self, p):
        return p.chromium.connect_over_cdp(_cdp_url(self.debug_port))

    def _logged_in(self, page) -> bool:
        """어느 프레임에도 로그인 폼(login.asp)이 없으면 로그인 상태로 간주.

        FlowerNT3는 프레임셋이라 최상위 URL은 로그아웃 시에도 main.asp로 남는다.
        따라서 자식 프레임 중 login.asp 존재 여부로 판정한다.
        """
        for f in page.frames:
            if "login.asp" in (f.url or "").lower():
                return False
        return "flowernt.com" in (page.url or "").lower()

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
                try:
                    ctx = browser.contexts[0] if browser.contexts else None
                    if ctx is None:
                        return False
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    if not self._logged_in(page):
                        return self._try_login(page)
                    return True
                finally:
                    browser.close()
        except Exception:
            logger.info("FlowerNT3 CDP 연결 실패 — 미구동으로 처리(백업)")
            return False

    def _try_login(self, page) -> bool:
        """저장된 자격증명으로 로그인 시도. 실패/자격증명 없음이면 False."""
        if not (self.login_id and self.login_password):
            return False
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            # 로그인 폼(ms_id/ms_pass)은 프레임 안에 있을 수 있어 전 프레임을 탐색.
            for fr in page.frames:
                id_el = fr.query_selector("input[name=ms_id]")
                pw_el = fr.query_selector("input[name=ms_pass]")
                if id_el and pw_el:
                    id_el.fill(self.login_id)
                    pw_el.fill(self.login_password)
                    pw_el.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(800)
                    return self._logged_in(page)
            # 로그인 폼을 못 찾았으면 이미 로그인 상태일 수 있음
            return self._logged_in(page)
        except Exception:
            logger.warning("FlowerNT3 자동 로그인 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = self._connect(p)
            try:
                ctx = browser.contexts[0] if browser.contexts else None
                if ctx is None:
                    raise RuntimeError("FlowerNT3 브라우저 컨텍스트 없음 — 입력 불가")
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.on("dialog", lambda d: d.accept())
                # 주문입력 프레임을 신규폼으로 새로고침(if/else 모두 재조회 후 폴백)
                order_url = self.url.rstrip("/") + ORDER_PATH
                frame = self._order_frame(page)
                if frame is not None:
                    frame.goto(order_url, wait_until="domcontentloaded")
                else:
                    page.goto(order_url, wait_until="domcontentloaded")
                frame = self._order_frame(page) or page.main_frame
                fill_order_form(frame, order, auto_submit=self.auto_submit)
                # 등록 POST가 끝날 때까지 대기(close로 in-flight 취소 방지). 타임아웃은 무시.
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    logger.debug("FlowerNT3 networkidle 대기 타임아웃 — 계속 진행")
            finally:
                browser.close()
