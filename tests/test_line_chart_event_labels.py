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



def test_temporal_color_split_preserves_original_line_geometry_and_exact_boundary():
    import importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('split_test',ROOT/'app/skills/generic-chart/scripts/group_line.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[{'date':f'2026-01-{i+1:02d}','close':100+i} for i in range(5)]
    base={'type':'group-line','title':'Price','xField':'date','data':data,'series':[{'field':'close','label':'Close','axis':'right'}],'leftAxis':{'visible':False},'rightAxis':{'visible':True}}
    split={'x':data[2]['date'],'field':'close','beforeColor':'#9ca9cc','afterColor':'#ff402b','beforeLabel':'Before trade','afterLabel':'After trade'}
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1000,'height':700})
        page.set_content(m.render_document(base));page.wait_for_selector('.line-path');original=page.locator('.line-path').get_attribute('d')
        page.goto('about:blank');page.set_content(m.render_document({**base,'visualStyle':{'line':{'colorSplit':split}}}));page.wait_for_selector('linearGradient',state='attached')
        assert page.locator('.line-path').get_attribute('d')==original
        assert page.locator('linearGradient stop').evaluate_all('es=>es.map(e=>e.getAttribute("offset"))')==['0.5','0.5']
        assert page.locator('.svg-legend').text_content().replace('\n','')=='Before tradeAfter trade'
        page.goto('about:blank');page.set_content(m.render_document({**base,'visualStyle':{'line':{'colorSplit':{**split,'x':'missing'}}}}));page.wait_for_selector('.line-path')
        assert page.locator('linearGradient').count()==0 and page.locator('.line-path').get_attribute('d')==original
        browser.close()
