import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("component,example", [("bar_chart", "bar"), ("dynamic_line", "dynamic_line")])
def test_example_renders_outside_repository(tmp_path, component, example):
    output = tmp_path / "chart.html"
    result = subprocess.run([
        sys.executable, str(ROOT / f"app/skills/generic-chart/scripts/{component}.py"),
        "--payload", str(ROOT / f"examples/{example}.json"), "--output", str(output),
    ], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    html = output.read_text()
    assert len(html) > 1000
    assert "<html" in html.lower()
    assert json.loads((ROOT / f"examples/{example}.json").read_text())["title"] in html


def test_every_component_has_valid_schema_and_help():
    base = ROOT / "app/skills/generic-chart"
    for script in sorted((base / "scripts").glob("*.py")):
        schema = base / "schemas" / f"{script.stem}.schema.json"
        assert isinstance(json.loads(schema.read_text()), dict)
        result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
