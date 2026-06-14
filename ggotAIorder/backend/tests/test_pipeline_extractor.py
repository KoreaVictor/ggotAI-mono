"""extractor 오프라인 테스트(genai 클라이언트 목) — 현재시각 주입 + delivery_at_text 통과."""

from __future__ import annotations

import ggotaiorder.pipeline.extractor as ex_mod
from ggotaiorder.pipeline.models import OrderExtraction


class _FakeResp:
    def __init__(self, parsed: OrderExtraction):
        self.parsed = parsed
        self.text = parsed.model_dump_json()


class _FakeModels:
    def __init__(self, parsed: OrderExtraction):
        self._parsed = parsed
        self.captured: dict = {}

    def generate_content(self, model, contents, config):
        self.captured["contents"] = contents
        return _FakeResp(self._parsed)


class _FakeClient:
    def __init__(self, parsed: OrderExtraction):
        self.models = _FakeModels(parsed)


def test_extract_injects_reference_time_and_returns_delivery_text(monkeypatch):
    parsed = OrderExtraction(
        product_name="장미", delivery_at="2026-06-14T15:00:00+09:00",
        delivery_at_text="내일 오후 3시",
    )
    fc = _FakeClient(parsed)
    monkeypatch.setattr(ex_mod, "_get_client", lambda: fc)

    out = ex_mod.extract_order(
        "내일 오후 3시 장미 주문", reference_time="2026-06-13T15:00:00+09:00"
    )

    assert "현재 시각: 2026-06-13T15:00:00+09:00" in fc.models.captured["contents"]
    assert "내일 오후 3시 장미 주문" in fc.models.captured["contents"]
    assert out.delivery_at == "2026-06-14T15:00:00+09:00"
    assert out.delivery_at_text == "내일 오후 3시"


def test_extract_defaults_reference_time_to_now(monkeypatch):
    fc = _FakeClient(OrderExtraction())
    monkeypatch.setattr(ex_mod, "_get_client", lambda: fc)
    ex_mod.extract_order("잡담")
    assert "현재 시각:" in fc.models.captured["contents"]
