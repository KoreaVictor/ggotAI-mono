from pathlib import Path

import pytest

from ggotaiorder.rpa.models import RpaOrder

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _chrome_ok() -> bool:
    return any(Path(p).exists() for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ])


pytestmark = pytest.mark.skipif(not _chrome_ok(), reason="시스템 Chrome 필요")

FIXTURE = Path(__file__).parent / "fixtures" / "flowernt3_order_form.html"


def _order():
    return RpaOrder(
        order_detail_id=1, shop_key=19, shop_name="t", channel="쇼핑몰",
        customer_name="홍길동", customer_phone_number="01011112222",
        product_name="장미", quantity=1, price=50000,
        delivery_at="2026-06-20T15:30:00", delivery_place="서울 강남",
        receiver_name="김영희", receiver_phone_number="01033334444",
        ribbon_sender="홍길동", ribbon_congratulations="축 개업",
        card_message="축하", delivery_at_text=None,
    )


def test_fill_order_form_populates_fields():
    from ggotaiorder.rpa.flowernt3.automator import fill_order_form
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto(FIXTURE.as_uri())
        fill_order_form(page.main_frame, _order(), auto_submit=True)
        val = lambda n: page.eval_on_selector(f"[name={n}]", "e=>e.value")
        assert val("customer_name") == "홍길동"
        assert val("sang_money") == "50000"
        assert val("sang_realMoney") == "50000"  # 판매가 = 소비정가
        # 배달비용 0 입력으로 총금액(readonly 자동계산) = 판매가 - 배달비용 = 50000
        assert val("baesong_money") == "0"
        assert val("total_money") == "50000"
        assert val("total_sumoney") == "50000"
        # 상품분류: '장미' → 생화 (value '82626|생화')
        assert page.eval_on_selector("select[name=sang_divi]", "e=>e.value") == "82626|생화"
        assert val("hope_date") == "2026-06-20"
        assert val("hope_time") == "15:30"
        assert val("receive_address1") == "서울 강남"
        checked = page.eval_on_selector(
            "input[name=order_divi]:checked", "e=>e.value")
        assert checked == "인터넷"  # 채널 '쇼핑몰' → order_divi value '인터넷'
        assert page.title() == "REG_CALLED"
        browser.close()
