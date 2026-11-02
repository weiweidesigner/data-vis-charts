import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

SCRIPT = Path(__file__).resolve().parents[1] / 'app/skills/generic-chart/scripts/data_table.py'
spec = importlib.util.spec_from_file_location('data_table', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def payload():
    return {'title': '完整明细', 'theme': 'dark', 'columns': [
        {'field': 'name', 'label': '名称', 'width': 250},
        {'field': 'value', 'label': '数值', 'type': 'number'},
        {'field': 'rate', 'label': '比例', 'type': 'percent'},
        {'field': 'date', 'label': '日期', 'type': 'date'},
    ], 'rows': [{'name': f'Record {i}', 'value': i, 'rate': 4.2, 'date': '20261102'} for i in range(1500)]}


def test_complete_file_and_nested_mapping(tmp_path):
    rows = [{'meta': {'name': str(i)}, 'a.b': None if i else False} for i in range(2001)]
    source = tmp_path / 'source.json'
    raw = json.dumps({'events': rows}).encode()
    source.write_bytes(raw)
    config = module.normalize({'dataSource': {'path': 'source.json', 'recordsPath': ['events']},
        'columns': [{'field': 'meta.name'}, {'field': ['a.b']}]}, tmp_path)
    assert len(config['rows']) == 2001
    assert config['rows'][0] == ['0', False]
    assert config['rows'][-1] == ['2000', None]
    assert config['fileSource']['sha256'] == hashlib.sha256(raw).hexdigest()
    assert config['fileSource']['recordCount'] == 2001
    with pytest.raises(ValueError, match='Row 1: Missing mapped field'):
        module.normalize({'rows': [{}], 'columns': [{'field': 'absent'}]})
    with pytest.raises(ValueError, match='Duplicate'):
        module.normalize({'rows': [], 'columns': [{'field': 'a'}, {'field': 'a'}]})


def test_html_escapes_source():
    p = payload()
    p['rows'] = [{'name': '</script><script>window.PWNED=1</script>', 'value': 0, 'rate': None, 'date': False}]
    html = module.build_html(module.normalize(p))
    assert '</script><script>window.PWNED' not in html
    assert json.loads(html.split('<script id="table-data" type="application/json">')[1].split('</script>')[0])['rows'][0][0] == p['rows'][0]['name']


def test_scroll_sort_details_and_iframe_fullscreen(tmp_path):
    table = tmp_path / 'table.html'
    table.write_text(module.build_html(module.normalize(payload())))
    host = tmp_path / 'host.html'
    host.write_text('<iframe allowfullscreen style="width:100%;height:430px;border:0" src="table.html"></iframe>')
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for width in (1100, 360):
                page = browser.new_page(viewport={'width': width, 'height': 800})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(host.as_uri())
                frame = page.frames[1]
                frame.wait_for_selector('tr[data-row-index]')
                assert frame.locator('tr[data-row-index]').count() < 40
                assert frame.locator('table').get_attribute('aria-rowcount') == '1501'
                assert frame.locator('tbody tr[data-row-index] td').nth(1).evaluate('(e)=>getComputedStyle(e).textAlign') == 'right'
                assert frame.locator('tbody tr[data-row-index] td').nth(2).inner_text() == '4.2%'
                assert frame.locator('tbody tr[data-row-index] td').nth(3).inner_text() == '2026-11-02'
                assert frame.evaluate('document.documentElement.scrollWidth <= innerWidth')
                frame.locator('.table-viewport').evaluate('(e)=>e.scrollTop=e.scrollHeight')
                frame.wait_for_selector('tr[data-row-index="1499"]')
                assert frame.locator('tr[data-row-index]').count() < 40
                assert frame.locator('.table-count, .table-footer').count() == 0
                assert frame.locator('.head-button svg').count() == 0
                frame.locator('.head-button').nth(1).click()
                assert frame.locator('th[aria-sort=descending]').count() == 1
                assert frame.locator('.head-button svg').count() == 1
                frame.locator('.head-button').nth(1).click()
                assert frame.locator('th[aria-sort=ascending]').count() == 1
                assert frame.locator('tr[data-row-index]').first.get_attribute('data-row-index') == '0'
                frame.locator('.head-button').nth(1).click()
                assert frame.locator('tr[data-row-index]').first.get_attribute('data-row-index') == '1499'
                frame.locator('tr[data-row-index] .cell-value').first.click()
                assert frame.locator('dialog').evaluate('(e)=>e.open')
                assert frame.locator('.detail-content').inner_text() == 'Record 1499'
                frame.locator('.close-detail').click()
                normal = frame.locator('.data-table-component').bounding_box()['height']
                frame.locator('.fullscreen-button').click()
                page.wait_for_function('document.fullscreenElement !== null')
                frame.wait_for_function('document.fullscreenElement !== null')
                assert frame.locator('.data-table-component').bounding_box()['height'] == 800
                frame.locator('.table-viewport').evaluate('(e)=>e.scrollTop=e.scrollHeight')
                frame.wait_for_selector('tr[data-row-index="0"]')
                frame.locator('.fullscreen-button').click()
                frame.wait_for_function('document.fullscreenElement === null')
                assert abs(frame.locator('.data-table-component').bounding_box()['height'] - normal) < 2
                assert not errors
                page.close()
        finally:
            browser.close()
