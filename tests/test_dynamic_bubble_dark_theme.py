from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/skills/generic-chart/scripts/dynamic_bubble.py"


def load_renderer():
    spec = spec_from_file_location("dynamic_bubble_renderer", SCRIPT)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_dynamic_bubble_uses_theme_aware_chart_tokens():
    renderer = load_renderer()
    document = renderer.build_html(
        {
            "title": "Theme check",
            "data": [{"time": "now", "name": "A", "x": 1, "y": 2, "size": 3}],
            "encode": {"time": "time", "name": "name", "x": "x", "y": "y", "size": "size"},
        }
    )

    assert 'document.documentElement.dataset.theme==="dark"' in document
    assert 'backgroundColor:darkMode?"rgba(24,31,42,.98)"' in document
    assert "borderColor:chartBorder" in document
    assert "color:chartText" in document
    assert "color:bubbleLabel" in document
    assert ':root[data-theme="dark"]' in document
