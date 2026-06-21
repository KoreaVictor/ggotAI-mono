"""FlowerNt3Automator — 전용 프로필 Chrome(CDP)에 붙어 주문폼을 채우고 등록한다.

singleton_macro가 asyncio.to_thread로 동기 호출하므로 sync Playwright를 쓰며,
매 호출마다 connect_over_cdp로 연결→작업→해제를 완결한다(스레드 귀속 회피).
connect_over_cdp 브라우저는 sync_playwright 컨텍스트가 닫아주지 않으므로 모든
경로에서 try/finally로 browser.close()를 보장한다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from ggotaiorder.rpa.flowernt3 import mapping
from ggotaiorder.rpa.models import RpaOrder

logger = logging.getLogger(__name__)

ORDER_FRAME_MARK = "order/order3.asp"
ORDER_PATH = "/order/order3.asp"
MAIN_PATH = "/main.asp"
# FlowerNT3는 main.asp 프레임셋 구조. 주문폼은 콘텐츠 프레임(flowernt3Main)에 로드해야
# 제출 대상인 숨은 프레임(inputform)이 살아 있어 등록이 완료된다. 최상위 page를
# 직접 order3.asp로 이동하면 프레임셋이 깨져 inputform이 사라지고 등록이 누락된다.
CONTENT_FRAME_NAME = "flowernt3Main"


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
    # 2-b) 총금액(total_money/total_sumoney)은 readonly 자동계산 필드다. 배달비용
    # (baesong_money) 입력 이벤트가 '총금액 = 판매가 - 배달비용' 계산을 트리거한다.
    # RPA가 값만 주입하면 onchange/onkeyup이 안 걸려 총금액이 0으로 남으므로, 배달비용을
    # 명시 입력하고 계산 이벤트를 직접 발생시킨다(라이브 확인).
    frame.evaluate(
        """(fee) => {
            const f = document.forms['order_form2'];
            if (!f || !f.baesong_money) return;
            f.baesong_money.value = fee;
            if (typeof getPriceString === 'function') {
                try { getPriceString(f.baesong_money, 0, 1); } catch (e) {}
            }
            for (const ev of ['keyup', 'change', 'blur']) {
                f.baesong_money.dispatchEvent(new Event(ev, { bubbles: true }));
            }
        }""",
        "0",
    )
    # 3) 등록 — submit_reg 호출 여부를 반환받아 미발견 시 실패로 간주.
    # submit_reg 는 confirm()/alert() 네이티브 다이얼로그를 띄운다. CDP 환경에선
    # Playwright dialog 핸들러의 accept()가 레이스에 져('No dialog is showing')
    # confirm 이 기본값(취소=false)으로 닫히면 등록이 조용히 중단된다. 이를 막으려
    # 호출 직전 window.confirm/alert 를 무력화(자동 '예')해 다이얼로그 자체를 없앤다.
    if auto_submit:
        called = frame.evaluate(
            "() => {"
            " window.confirm = () => true;"
            " window.alert = () => {};"
            " if (typeof submit_reg === 'function') { submit_reg(); return true; }"
            " return false; }"
        )
        if not called:
            raise RuntimeError(
                "FlowerNT3 submit_reg() 미발견 — 등록 실패(폼/프레임 확인 필요)"
            )


class FlowerNt3Automator:
    def __init__(
        self, *, url, login_id, login_password, auto_submit, debug_port,
        profile_dir=None, chrome_path=None,
    ):
        # FlowerNT는 모든 가게가 동일한 flowernt.com을 쓰므로 미설정 시 기본 도메인이 곧 정답.
        self.url = url or "https://www.flowernt.com"
        self.login_id = login_id
        self.login_password = login_password
        self.auto_submit = auto_submit
        self.debug_port = debug_port
        # 전용 Chrome 자동기동용(사장님이 브라우저/로그인을 직접 다루지 않도록).
        self.profile_dir = profile_dir
        self.chrome_path = chrome_path

    def _order_url(self) -> str:
        """주문폼 URL. rpa_program_url에 경로·쿼리(main.asp?checkintro=Y 등)가
        있어도 origin(scheme+host)만 뽑아 ORDER_PATH를 붙인다."""
        parts = urlsplit(self.url)
        origin = f"{parts.scheme}://{parts.netloc}" if parts.netloc else self.url
        return origin + ORDER_PATH

    # --- 세션 ---
    def _connect(self, p):
        return p.chromium.connect_over_cdp(_cdp_url(self.debug_port))

    def _cdp_alive(self) -> bool:
        """CDP DevTools 엔드포인트가 응답하면 전용 Chrome이 떠 있는 것."""
        import urllib.request

        try:
            url = _cdp_url(self.debug_port) + "/json/version"
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                return resp.status == 200
        except Exception:
            return False

    def _ensure_browser_running(self, *, timeout_s: float = 20.0) -> bool:
        """전용 Chrome이 안 떠 있으면 직접 기동하고 CDP가 응답할 때까지 대기한다.

        사장님은 브라우저 실행을 직접 못 하므로 백엔드가 대신 띄운다. 로그인은
        이후 _try_login(저장된 자격증명)이 처리한다. 실행파일이 없거나 시간 내
        CDP가 안 올라오면 False(→ 호출자가 백업/수동입력으로 폴백).
        """
        import subprocess
        import time

        if self._cdp_alive():
            return True
        if not self.chrome_path or not Path(self.chrome_path).exists():
            logger.warning("RPA Chrome 실행파일 없음 — 자동기동 불가: %s", self.chrome_path)
            return False
        if self.profile_dir:
            Path(self.profile_dir).mkdir(parents=True, exist_ok=True)

        args = [
            str(self.chrome_path),
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            # 웹기동 시 DB의 rpa_program_url(랜딩 URL)로 직접 연다(프로그램별 상이).
            self.url,
        ]
        try:
            subprocess.Popen(args)  # noqa: S603 - 고정 인자, 사용자 입력 없음
        except Exception:
            logger.exception("RPA Chrome 기동 실패")
            return False

        logger.info("RPA Chrome 기동 — CDP 대기(127.0.0.1:%s)", self.debug_port)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._cdp_alive():
                return True
            time.sleep(0.5)
        logger.warning("RPA Chrome 기동 후 CDP 미응답(%.0fs) — 미구동 처리", timeout_s)
        return False

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

    def _main_url(self) -> str:
        parts = urlsplit(self.url)
        origin = f"{parts.scheme}://{parts.netloc}" if parts.netloc else self.url
        return origin + MAIN_PATH

    def _content_frame(self, page):
        """프레임셋 콘텐츠 프레임(flowernt3Main). 이름은 네비게이션 후에도 유지된다."""
        for f in page.frames:
            if f.name == CONTENT_FRAME_NAME:
                return f
        return None

    def _active_page(self, ctx):
        """작업할 정상 페이지를 고른다. flowernt 페이지를 우선하고, 빈/detached
        페이지(진단·세션꼬임으로 남은 about:blank 등)는 피한다. 정상 페이지가
        없으면 새로 연다. ctx.pages[0]가 빈 페이지면 goto가 'Frame has been
        detached'로 터져 로그인/입력이 통째로 실패하던 문제를 방지한다.
        """
        for pg in ctx.pages:
            try:
                if "flowernt" in (pg.url or "").lower():
                    return pg
            except Exception:
                continue
        return ctx.new_page()

    def is_program_running(self) -> bool:
        # 전용 Chrome이 꺼져 있으면 직접 띄운다(사장님 무조작). 실패 시 미구동→백업.
        if not self._ensure_browser_running():
            return False
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = self._connect(p)
                try:
                    ctx = browser.contexts[0] if browser.contexts else None
                    if ctx is None:
                        return False
                    page = self._active_page(ctx)
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
                page = self._active_page(ctx)

                # 폼 외 다이얼로그(로그인/네비게이션) 폴백 처리. CDP 환경에선 다이얼로그가
                # 이미 자동 처리된 뒤 accept()가 와 'No dialog is showing'이 날 수 있어
                # 레이스 예외를 삼킨다(등록 confirm 은 fill_order_form 에서 별도 무력화).
                def _accept_dialog(d) -> None:
                    try:
                        d.accept()
                    except Exception:
                        logger.debug("FlowerNT3 dialog accept 레이스 — 무시")

                page.on("dialog", _accept_dialog)
                # 주문폼은 반드시 프레임셋 콘텐츠 프레임(flowernt3Main) 안에서 연다.
                # 최상위 page를 order3.asp로 직접 이동하면 프레임셋이 깨져 제출 대상
                # (inputform) 프레임이 사라지고, submit_reg는 돌지만 등록이 누락된다.
                order_url = self._order_url()
                content = self._content_frame(page)
                if content is None:
                    page.goto(self._main_url(), wait_until="domcontentloaded")
                    page.wait_for_timeout(1000)
                    content = self._content_frame(page)
                if content is None:
                    raise RuntimeError(
                        "FlowerNT3 콘텐츠 프레임(flowernt3Main) 없음 — 입력 불가"
                    )
                content.goto(order_url, wait_until="domcontentloaded")
                frame = self._content_frame(page) or page.main_frame
                fill_order_form(frame, order, auto_submit=self.auto_submit)
                # 등록 POST가 끝날 때까지 대기(close로 in-flight 취소 방지). 타임아웃은 무시.
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    logger.debug("FlowerNT3 networkidle 대기 타임아웃 — 계속 진행")
            finally:
                browser.close()
