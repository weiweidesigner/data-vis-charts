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


def test_outside_top_marks_never_cover_plot_or_each_other_on_mobile():
    import importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('outside_test',ROOT/'app/skills/generic-chart/scripts/group_line.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[{'date':f'2026-01-{i+1:02d}','close':100+i%3} for i in range(9)]
    base={'type':'group-line','title':'Price','xField':'date','data':data,'series':[{'field':'close','label':'Close','axis':'right'}],'leftAxis':{'visible':False},'rightAxis':{'visible':True}}
    marks=[{'type':'pointMarkers','targetField':'close','x':data[i]['date'],'eventTime':data[i]['date'],'eventTitle':name,'labelBox':True,'labelPlacement':'outside-top'} for i,name in [(2,'交易日'),(3,'披露日'),(4,'事件日')]]
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page()
        for width in (1280,390,320):
            page.set_viewport_size({'width':width,'height':900});page.goto('about:blank');page.set_content(m.render_document({**base,'visualStyle':{'overlays':marks}}));page.wait_for_selector('.event-label-box')
            rects=page.locator('.event-label-box rect').evaluate_all('es=>es.map(e=>{const r=e.getBBox();return {x:r.x,y:r.y,w:r.width,h:r.height}})')
            assert len(rects)==3 and all(r['y']+r['h']<=0 for r in rects)
            for i,a in enumerate(rects):
                for b in rects[i+1:]:assert a['x']+a['w']<=b['x'] or b['x']+b['w']<=a['x'] or a['y']+a['h']<=b['y'] or b['y']+b['h']<=a['y']
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        browser.close()


def test_embedded_line_keeps_svg_legend_and_axis_text_inside_frame():
    import html,importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('height_test',ROOT/'app/skills/generic-chart/scripts/group_line.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[{'date':f'2026-01-{i+1:02d}','close':100+i%3} for i in range(9)]
    payload={'type':'group-line','title':'Price','xField':'date','data':data,'series':[{'field':'close','label':'Close','axis':'right'}],'leftAxis':{'visible':False},'rightAxis':{'visible':True,'label':'Close'},'visualStyle':{'title':{'visible':False},'line':{'colorSplit':{'x':data[2]['date'],'beforeLabel':'Before','afterLabel':'After','beforeColor':'#9ca9cc','afterColor':'#ff402b'}}}}
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page()
        for width in (623,320):
            page.goto('about:blank');page.set_content('<iframe style="border:0;width:'+str(width)+'px;height:400px" srcdoc="'+html.escape(m.render_document(payload),quote=True)+'"></iframe>')
            frame=page.frames[1];frame.wait_for_selector('.svg-legend');frame.wait_for_function('[...document.querySelectorAll("svg text")].every(e=>e.getBoundingClientRect().bottom<=innerHeight)')
        browser.close()


def test_inside_event_cards_use_free_grid_space_without_covering_curve():
    import importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('inside_test',ROOT/'app/skills/generic-chart/scripts/group_line.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[{'date':str(i),'close':100+(i%7)*3} for i in range(45)]
    marks=[{'type':'pointMarkers','targetField':'close','x':str(i),'eventTime':'2026-01-01','eventTitle':title,'labelBox':True,'labelPlacement':'inside'} for i,title in [(10,'交易日'),(11,'披露日'),(12,'事件日')]]
    payload={'type':'group-line','title':'Price','xField':'date','data':data,'series':[{'field':'close','label':'Close','axis':'right'}],'leftAxis':{'visible':False},'rightAxis':{'visible':True},'visualStyle':{'overlays':marks}}
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page()
        for width in (1280,623,390,320):
            page.set_viewport_size({'width':width,'height':900});page.goto('about:blank');page.set_content(m.render_document(payload));page.wait_for_selector('.event-label-box')
            result=page.evaluate('''()=>{const boxes=[...document.querySelectorAll('.event-label-box rect')].map(e=>e.getBBox()),lines=[...document.querySelectorAll('.grid-line')],left=+lines[0].getAttribute('x1'),right=+lines[0].getAttribute('x2'),top=Math.min(...lines.map(e=>+e.getAttribute('y1'))),bottom=Math.max(...lines.map(e=>+e.getAttribute('y1')));return {count:boxes.length,bounds:boxes.every(b=>b.x>=left&&b.x+b.width<=right&&b.y>=top&&b.y+b.height<=bottom),overlap:boxes.some((a,i)=>boxes.slice(i+1).some(b=>a.x<b.x+b.width&&b.x<a.x+a.width&&a.y<b.y+b.height&&b.y<a.y+a.height))}}''')
            assert result=={'count':3,'bounds':True,'overlap':False}
        browser.close()

def test_allow_overlap_still_prefers_vertical_gap_above_v_shaped_curve():
    import importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('soft_avoid_test',ROOT/'app/skills/generic-chart/scripts/group_line.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=[{'date':str(i),'close':80+abs(i-4)*10} for i in range(9)]
    payload={'type':'group-line','title':'Price','xField':'date','data':data,'series':[{'field':'close','label':'Close','axis':'right'}],'leftAxis':{'visible':False},'rightAxis':{'visible':True},'visualStyle':{'chart':{'height':'200px','minHeight':'200px'},'overlays':[{'type':'pointMarkers','targetField':'close','x':'4','eventTime':'2026-01-01','eventTitle':'事件日','labelBox':True,'labelPlacement':'inside','allowCurveOverlap':True}]}}
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':720,'height':400});page.set_content(m.render_document(payload));page.wait_for_selector('.event-label-box')
        assert page.evaluate('''()=>{const b=document.querySelector('.event-label-box rect').getBBox(),path=document.querySelector('.line-path');for(let i=0;i<path.getTotalLength();i++){const p=path.getPointAtLength(i);if(p.x>b.x&&p.x<b.x+b.width&&p.y>b.y&&p.y<b.y+b.height)return false;}return true}''')
        browser.close()
