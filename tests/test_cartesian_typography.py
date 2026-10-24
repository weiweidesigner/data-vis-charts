import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "app/skills/generic-chart/scripts"


def render(component: str) -> str:
    path = SCRIPTS / f"{component}.py"
    spec = importlib.util.spec_from_file_location(component, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.normalize_xy_series(
        module.default_payload(), module.COMPONENT_TYPE, "Typography", "bar"
    )
    return module.render_svg_chart(config, "bar")


@pytest.mark.parametrize("component", ["bar_chart", "grouped_bar"])
def test_bar_charts_use_readable_tooltip_and_axis_typography(component):
    html = render(component)
    assert ".axis-label{fill:var(--chart-text-secondary);font-size:13px" in html
    assert ".x-label{fill:var(--chart-text-secondary);font-size:13px" in html
    assert "font-size:14px;line-height:1.55" in html
    assert "min-height:26px" in html
    assert "fontSize: 14" in html
    assert "function measureAxisWidth(labels, fontSize = 13" in html
    assert "measureAxisWidth(tickLabels, 13, 400)" in html
