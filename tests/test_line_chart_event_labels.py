import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/skills/generic-chart/scripts/line_chart.py"


def test_line_chart_renders_framed_two_line_event_label(tmp_path: Path) -> None:
    payload = {
        "chartType": "line",
        "title": "事件标记示例",
        "data": [
            {"date": "09-01", "value": 42},
            {"date": "09-02", "value": 48},
            {"date": "09-03", "value": 51},
        ],
        "xField": "date",
        "yField": "value",
        "series": [{"key": "value", "label": "热度", "axis": "right"}],
        "leftAxis": {"visible": False},
        "rightAxis": {"visible": True, "label": "热度"},
        "visualStyle": {
            "overlays": {
                "pointMarkers": [
                    {
                        "xValue": "09-02",
                        "seriesKey": "value",
                        "labelBox": True,
                        "eventTime": "2026-09-02",
                        "eventTitle": "产品发布会",
                    }
                ]
            }
        },
    }
    payload_path = tmp_path / "payload.json"
    output_path = tmp_path / "event-line.html"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--payload", str(payload_path), "--output", str(output_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    html = output_path.read_text(encoding="utf-8")
    assert "drawEventLabel" in html
    assert "event-label-box" in html
    assert "2026-09-02" in html
    assert "产品发布会" in html


def test_line_chart_schema_documents_event_label_box() -> None:
    schema_path = ROOT / "app/skills/generic-chart/schemas/line_chart.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    encoded = json.dumps(schema, ensure_ascii=False)

    assert "labelBox" in encoded
    assert "eventTime" in encoded
    assert "eventTitle" in encoded

