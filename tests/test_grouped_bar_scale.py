import importlib.util
import json
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[1]/'app/skills/generic-chart/scripts/grouped_bar.py'


def test_grouped_bar_uses_five_grid_lines_without_empty_positive_band():
    spec = importlib.util.spec_from_file_location('range_grouped_bar', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.normalize_xy_series(module.default_payload(), module.COMPONENT_TYPE, 'Test', 'bar')
    html = module.render_svg_chart(config, 'bar')
    js = html[html.index('const niceStep ='):html.index('function tooltipBounds')]
    inputs = [[-9.76, -8.03, -.3, .01], [-9.76, -8.03, -.3], [1, 3, 9], [-14, 23], [0, 0]]
    js += '\nconsole.log(JSON.stringify('+json.dumps(inputs)+'.map(v=>range(v,5))))'
    results = json.loads(subprocess.check_output(['node', '-e', js], text=True))
    for values, result in zip(inputs, results):
        assert len(result['ticks']) == 5
        assert result['min'] <= min(values) and result['max'] >= max(values)
        assert 0 in result['ticks']
        assert len(set(result['ticks'])) == 5
        assert all(a > b for a,b in zip(result['ticks'],result['ticks'][1:]))
    assert results[0]['max'] <= .5
    assert results[1]['max'] == 0
