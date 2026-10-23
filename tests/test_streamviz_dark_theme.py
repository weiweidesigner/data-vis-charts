import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "app/skills/generic-chart/scripts"


CASES = {
    "bar_chart": {
        "type": "bar", "theme": "dark", "financialMarket": "CN", "title": "涨跌幅", "xField": "name",
        "series": [{"field": "value", "label": "涨跌幅"}],
        "data": [{"name": "A", "value": 1.2}, {"name": "B", "value": -0.8}],
    },
    "grouped_bar": {
        "type": "grouped-bar", "theme": "dark", "title": "对比", "xField": "name",
        "series": [{"field": "a", "label": "A"}, {"field": "b", "label": "B"}],
        "data": [{"name": "一", "a": 2, "b": 3}],
    },
    "line_chart": {
        "type": "line", "theme": "dark", "title": "趋势", "xField": "date", "yField": "value",
        "data": [{"date": "1", "value": 2}, {"date": "2", "value": 3}],
    },
    "group_line": {
        "type": "group-line", "theme": "dark", "title": "趋势对比", "xField": "date",
        "series": [{"field": "a", "label": "A", "axis": "right"}],
        "data": [{"date": "1", "a": 2}, {"date": "2", "a": 3}],
    },
    "bar_line": {
        "type": "bar-line", "theme": "dark", "title": "柱折图", "xField": "date",
        "columnSeries": [{"field": "amount", "label": "金额"}],
        "lineSeries": [{"field": "rate", "label": "增速"}],
        "data": [{"date": "1", "amount": 2, "rate": 3}],
    },
    "pie": {
        "type": "pie", "theme": "dark", "props": {"items": [{"label": "A", "value": 2}]},
    },
    "double_ring_pie": {
        "type": "double-ring-pie", "theme": "dark",
        "props": {"rings": [{"label": "A", "value": 2, "total": 5}]},
    },
    "waterfall": {
        "type": "waterfall", "theme": "dark", "props": {"items": [{"label": "A", "value": 2}]},
    },
    "treemap": {
        "type": "treemap", "theme": "dark", "props": {"items": [{"label": "A", "value": 2}]},
    },
}


@pytest.mark.parametrize("component", CASES)
def test_foundation_components_follow_streamviz_dark_tokens(tmp_path, component):
    payload = tmp_path / f"{component}.json"
    output = tmp_path / f"{component}.html"
    payload.write_text(json.dumps(CASES[component], ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / f"{component}.py"), "--payload", str(payload), "--output", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    document = output.read_text(encoding="utf-8")
    assert 'data-theme="dark"' in document
    assert "#f1f5f9" in document
    assert "#c1cad7" in document
    assert "URLSearchParams(location.search).get('theme')" in document
