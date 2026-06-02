"""전체 모듈 import 및 핵심 계약 스모크 테스트."""

import importlib

import pytest

MODULES = [
    "ggotaiorder.config",
    "ggotaiorder.logging_setup",
    "ggotaiorder.core.crypto",
    "ggotaiorder.core.supabase_client",
    "ggotaiorder.orchestrator",
    "ggotaiorder.tray",
    "ggotaiorder.api.routes",
    "ggotaiorder.realtime.listener",
    "ggotaiorder.pipeline.engine",
    "ggotaiorder.scraper.crawler",
    "ggotaiorder.rpa.singleton_macro",
    "ggotaiorder.notifier.sms_sender",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_pipeline_has_11_fields():
    from ggotaiorder.pipeline.engine import ORDER_FIELDS
    assert len(ORDER_FIELDS) == 11


def test_fastapi_app_has_health_route():
    from ggotaiorder.api.routes import create_app
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/v1/gate-phone/upload" in paths


def test_notifier_template_rendering():
    from ggotaiorder.notifier.sms_sender import render_template
    out = render_template("{channel} 주문 {count}건 완료", "인터라넷", 3)
    assert out == "인터라넷 주문 3건 완료"
