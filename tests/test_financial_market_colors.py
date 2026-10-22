import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "app/skills/generic-chart/scripts"


def load_renderer(name: str):
    script = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"market_colors_{name}", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("renderer_name,component_type", [("bar_chart", "bar"), ("grouped_bar", "grouped-bar")])
def test_ashare_market_is_inferred_and_embedded(renderer_name, component_type):
    renderer = load_renderer(renderer_name)
    payload = {
        "type": component_type,
        "title": "各板块个股涨跌幅中位数",
        "xField": "board",
        "series": [{"field": "medianPct", "label": "中位涨跌幅"}],
        "data": [
            {"board": "北交所", "medianPct": 0.09},
            {"board": "创业板", "medianPct": -1.05},
        ],
        "visualStyle": {
            "colorRules": [
                {"condition": ">0", "color": "var(--sv-price-up)"},
                {"condition": "<0", "color": "var(--sv-price-down)"},
            ]
        },
    }
    normalized = renderer.normalize_xy_series(payload, component_type, "Test", "bar")
    document = renderer.render_svg_chart(normalized, "bar")

    assert normalized["financialMarket"] == "CN"
    assert '<html lang="zh-CN" data-theme="light" data-financial-market="CN">' in document
    assert ':root[data-financial-market="CN"],:root[data-financial-market="HK"]{--sv-price-up:var(--sv-loss);--sv-price-down:var(--sv-gain)}' in document
    assert "getComputedStyle(probe).color" in document
    assert "color:chartColor(row.__markColors?.[series.field] || series.color)" in document
    assert "fill:chartColor(row.__markColors?.[series.field] || series.color)" in document


@pytest.mark.parametrize("renderer_name,component_type", [("bar_chart", "bar"), ("grouped_bar", "grouped-bar")])
def test_us_market_keeps_green_up_red_down(renderer_name, component_type):
    renderer = load_renderer(renderer_name)
    payload = {
        "type": component_type,
        "financialMarket": "US",
        "title": "US stocks change",
        "xField": "name",
        "series": [{"field": "change", "label": "Change"}],
        "data": [{"name": "NASDAQ", "change": 1.2}],
    }
    normalized = renderer.normalize_xy_series(payload, component_type, "Test", "bar")
    document = renderer.render_svg_chart(normalized, "bar")

    assert normalized["financialMarket"] == "US"
    assert 'data-financial-market="US"' in document
    assert ':root[data-financial-market="US"]{--sv-price-up:var(--sv-gain);--sv-price-down:var(--sv-loss)}' in document
