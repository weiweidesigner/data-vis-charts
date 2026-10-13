#!/usr/bin/env python3
"""Standalone double-ring pie component."""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


COMPONENT_TYPE = "double-ring-pie"

VISUAL_CHANNEL_MAPPINGS = [
    {
        "semantic": "中心文本",
        "field": "centerLabel",
        "aliases": ["marketCapLabel", "totalLabel"],
        "visualChannel": "doubleRing.center.label",
        "required": True,
    },
    {
        "semantic": "基准环",
        "field": "base",
        "aliases": ["track", "marketCap"],
        "visualChannel": "doubleRing.track",
        "required": True,
    },
    {
        "semantic": "双环系列",
        "field": "rings",
        "aliases": ["series"],
        "visualChannel": "doubleRing.arc.progress",
        "required": True,
    },
    {
        "semantic": "底部指标",
        "field": "metrics",
        "aliases": ["fields", "keyValues"],
        "visualChannel": "metricList.items",
    },
]

DATA_CONTRACT = [
    {"field": "centerLabel", "type": "string", "channel": "doubleRing.center.label"},
    {"field": "base.label", "type": "string", "channel": "legend.label"},
    {"field": "base.displayValue", "type": "string", "channel": "legend.value"},
    {"field": "base.color", "type": "string", "channel": "doubleRing.track.color"},
    {"field": "rings[].label", "type": "string", "channel": "legend.label"},
    {"field": "rings[].value", "type": "number", "channel": "doubleRing.arc.length"},
    {"field": "rings[].total", "type": "number", "channel": "doubleRing.arc.scale"},
    {"field": "rings[].color", "type": "string", "channel": "doubleRing.arc.color"},
    {"field": "metrics[].label", "type": "string", "channel": "metric.label"},
    {"field": "metrics[].value", "type": "string", "channel": "metric.value"},
]




def _finalize_document_theme(document, payload):
    theme = "dark" if (payload.get("theme") or (payload.get("props") or {}).get("theme")) == "dark" else "light"
    language = str(payload.get("language") or "zh-CN")
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        language = "en"
    document = re.sub(r'<html\b[^>]*>', '<html lang="' + language + '" data-theme="' + theme + '">', document, count=1)
    boot = """<script>(() => { const theme = new URLSearchParams(location.search).get('theme'); if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme; })();</script>"""
    return document.replace('</head>', boot + '</head>', 1)

def component_schema() -> dict[str, Any]:
    return {
        "type": COMPONENT_TYPE,
        "name": "双环饼图",
        "visualChannelMappings": VISUAL_CHANNEL_MAPPINGS,
        "dataContract": DATA_CONTRACT,
        "builtInDataSources": [],
    }


def _extract_component(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") == COMPONENT_TYPE:
        return payload
    root = payload.get("root")
    if isinstance(root, dict) and root.get("type") == "component" and isinstance(root.get("component"), dict):
        return root["component"]
    component = payload.get("component")
    if isinstance(component, dict):
        return component
    raise ValueError("payload must contain a double-ring-pie component")


def _normalize_component(component: dict[str, Any]) -> dict[str, Any]:
    props = component.get("props", {})
    base = props.get("base") if isinstance(props.get("base"), dict) else {}
    rings = props.get("rings") or component.get("data") or []
    if not isinstance(rings, list) or not rings:
        raise ValueError("double-ring-pie rings must be a non-empty array")
    palette = ["#4285f4", "#4bc3d5"]
    normalized_rings = []
    for index, raw in enumerate(rings):
        if not isinstance(raw, dict):
            raw = {"label": str(index + 1), "value": raw}
        value = float(raw.get("value") or 0)
        total = float(raw.get("total") or base.get("value") or max(value, 1))
        normalized_rings.append(
            {
                "label": str(raw.get("label") or raw.get("name") or index + 1),
                "value": max(0, value),
                "total": max(total, 0.000001),
                "displayValue": str(raw.get("displayValue") or ""),
                "color": str(raw.get("color") or palette[index % len(palette)]),
            }
        )
    metrics = props.get("metrics") or []
    normalized_metrics = []
    if isinstance(metrics, list):
        for metric in metrics:
            if isinstance(metric, dict):
                normalized_metrics.append(
                    {
                        "label": str(metric.get("label") or metric.get("key") or ""),
                        "value": str(metric.get("value") or ""),
                    }
                )
    return {
        "title": str(component.get("title") or props.get("title") or ""),
        "centerLabel": str(props.get("centerLabel") or component.get("title") or ""),
        "height": int(props.get("height") or 430),
        "base": {
            "label": str(base.get("label") or "市值"),
            "value": float(base.get("value") or 0),
            "displayValue": str(base.get("displayValue") or props.get("centerLabel") or ""),
            "color": str(base.get("color") or "#9b9b9b"),
            "trackColor": str(base.get("trackColor") or "#f0f0f0"),
        },
        "rings": normalized_rings,
        "metrics": normalized_metrics,
    }


def render_document(payload: dict[str, Any]) -> str:
    config = _normalize_component(_extract_component(payload))
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(config["title"] or "双环饼图")
    contract = html.escape(json.dumps(component_schema(), ensure_ascii=False), quote=True)
    return _finalize_document_theme(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light;--business-text-171717:#171717;--business-bg-fff:#fff;--business-bg-2f2f2f:#2f2f2f;--business-text-fff:#fff;--business-text-4b5563:#4b5563;}}
:root[data-theme="dark"]{{color-scheme:dark;--business-text-171717:#e8edf5;--business-bg-fff:#202b3a;--business-bg-2f2f2f:#263242;--business-text-fff:#f5f7fb;--business-text-4b5563:#a8b3c4;}}

*{{box-sizing:border-box}}
	html,body{{width:100%;min-height:0;margin:0;background:transparent}}
	body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;color:var(--business-text-171717);overflow:hidden}}
	.double-ring-component{{width:100%;min-height:0;padding:8px 18px 10px;background:var(--business-bg-fff)}}
	.ring-layout{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;width:100%;max-width:560px;margin:0 auto}}
	.ring-stage{{position:relative;width:100%;height:250px;display:flex;align-items:center;justify-content:center}}
	.ring-side{{width:100%;display:flex;justify-content:center}}
	svg{{display:block;width:240px;height:240px;overflow:visible}}
.center-text{{font-size:18px;font-weight:500;fill:var(--business-text-171717);text-anchor:middle;dominant-baseline:middle}}
.ring-track,.ring-arc,.ring-highlight{{transition:opacity .12s ease}}
.ring-arc{{cursor:pointer}}
.ring-arc:hover{{opacity:.88}}
.ring-highlight{{pointer-events:none}}
.ring-tooltip{{position:absolute;z-index:5;min-width:150px;padding:8px 11px;background:var(--business-bg-2f2f2f);color:var(--business-text-fff);border-radius:4px;font-size:13px;line-height:1.5;pointer-events:none;opacity:0;visibility:hidden;transition:opacity .12s ease}}
.ring-tooltip::after{{content:"";position:absolute;top:50%;transform:translateY(-50%) rotate(45deg);width:10px;height:10px;background:var(--business-bg-2f2f2f)}}
.ring-tooltip[data-side="right"]::after{{left:-5px}}
.ring-tooltip[data-side="left"]::after{{right:-5px}}
.tooltip-title{{display:flex;align-items:center;gap:9px;white-space:nowrap}}
.tooltip-value{{padding-left:18px;white-space:nowrap}}
.tooltip-dot{{width:9px;height:9px;border-radius:50%;flex:none}}
.ring-tooltip.active{{opacity:1;visibility:visible}}
	.ring-legend{{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px 16px;width:100%;max-width:560px;margin:0 auto;color:var(--business-text-4b5563);font-size:12px;line-height:1.2}}
	.legend-item{{display:flex;align-items:center;gap:7px;white-space:nowrap}}
	.legend-dot{{width:8px;height:8px;border-radius:50%;flex:none}}
		.metric-list{{display:none;grid-template-columns:minmax(0,1fr) auto;gap:14px 18px;width:100%;max-width:460px;margin:22px auto 0;font-size:14px;line-height:1.2}}
.metric-label{{color:var(--business-text-171717);white-space:nowrap}}
.metric-value{{font-weight:800;text-align:right;white-space:nowrap}}
		@media(min-width:760px){{.double-ring-component{{max-width:820px;margin:0 auto}}.ring-layout{{gap:8px}}.ring-stage{{height:250px}}.ring-side{{width:100%;max-width:560px}}.ring-legend{{justify-content:center;margin:0;font-size:12px;gap:10px 16px}}}}
	@media(max-width:520px){{.double-ring-component{{padding:12px 14px 10px}}svg{{width:220px;height:220px}}.ring-stage{{height:230px}}.ring-legend{{gap:9px 12px;font-size:12px}}}}
</style>
</head>
<body>
<section class="double-ring-component" data-component-contract="{contract}">
  <div class="ring-layout">
    <div class="ring-stage"><svg role="img" aria-label="{title}"></svg><div class="ring-tooltip"></div></div>
    <div class="ring-side">
      <div class="ring-legend"></div>
      <div class="metric-list"></div>
    </div>
  </div>
</section>
<script>
const config = {config_json};
const root = document.querySelector('.double-ring-component');
const stage = root.querySelector('.ring-stage');
const svg = root.querySelector('svg');
const legend = root.querySelector('.ring-legend');
const metrics = root.querySelector('.metric-list');
const tooltip = root.querySelector('.ring-tooltip');
const NS = 'http://www.w3.org/2000/svg';

const node = (name, attrs = {{}}, text = '') => {{
  const el = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value));
  if (text !== '') el.textContent = text;
  return el;
}};
const polar = (cx, cy, r, angle) => {{
  const rad = (angle - 90) * Math.PI / 180;
  return {{x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad)}};
}};
const arcPath = (cx, cy, outerR, innerR, start, end) => {{
  const large = end - start > 180 ? 1 : 0;
  const p1 = polar(cx, cy, outerR, start);
  const p2 = polar(cx, cy, outerR, end);
  const p3 = polar(cx, cy, innerR, end);
  const p4 = polar(cx, cy, innerR, start);
  return `M ${{p1.x}} ${{p1.y}} A ${{outerR}} ${{outerR}} 0 ${{large}} 1 ${{p2.x}} ${{p2.y}} L ${{p3.x}} ${{p3.y}} A ${{innerR}} ${{innerR}} 0 ${{large}} 0 ${{p4.x}} ${{p4.y}} Z`;
}};

function render() {{
  svg.innerHTML = '';
  legend.innerHTML = '';
  metrics.innerHTML = '';
  const width = svg.clientWidth || 260;
  const height = svg.clientHeight || 260;
  const cx = width / 2;
  const cy = height / 2;
  const outerR = Math.min(width, height) * .44;
  const innerR = outerR * .62;
  const gap = 0;
  const track = node('path', {{d:arcPath(cx,cy,outerR,innerR,0,359.99),fill:config.base.trackColor,class:'ring-track'}});
  svg.appendChild(track);
  config.rings.forEach((ring, index) => {{
    const ratio = Number(ring.value || 0) / Math.max(Number(ring.total || 1), 0.000001);
    const bandW = (outerR - innerR - gap) / 2;
    const bandOuter = index === 0 ? outerR : outerR - bandW - gap;
    const bandInner = bandOuter - bandW;
	    const cappedRatio = Math.max(0, Math.min(1, ratio));
	    const end = cappedRatio >= .999 ? 359.99 : Math.max(.4, cappedRatio * 360);
    const highlight = node('path', {{d:arcPath(cx,cy,bandOuter + 6,bandOuter,0,end),fill:ring.color,class:'ring-highlight','data-index':index}});
    highlight.style.opacity = '0';
    svg.appendChild(highlight);
    const arc = node('path', {{d:arcPath(cx,cy,bandOuter,bandInner,0,end),fill:ring.color,class:'ring-arc','data-index':index}});
    arc.addEventListener('mouseenter', event => showTooltip(event, ring, index));
    arc.addEventListener('mousemove', event => showTooltip(event, ring, index));
    arc.addEventListener('mouseleave', hideTooltip);
    svg.appendChild(arc);
  }});
  svg.appendChild(node('text', {{x:cx,y:cy,class:'center-text'}}, config.centerLabel));

  const baseLegend = document.createElement('span');
  baseLegend.className = 'legend-item';
  baseLegend.innerHTML = `<i class="legend-dot" style="background:${{config.base.color}}"></i>${{config.base.label}}`;
  legend.appendChild(baseLegend);
  config.rings.slice().reverse().forEach(ring => {{
    const item = document.createElement('span');
    item.className = 'legend-item';
    item.innerHTML = `<i class="legend-dot" style="background:${{ring.color}}"></i>${{ring.label}}`;
    legend.appendChild(item);
  }});

	  config.metrics.forEach(metric => {{
	    const label = document.createElement('div');
    label.className = 'metric-label';
    label.textContent = metric.label;
    const value = document.createElement('div');
    value.className = 'metric-value';
    value.textContent = metric.value;
	    metrics.appendChild(label);
	    metrics.appendChild(value);
	  }});
	  postChartHeight();
	}}
function setHighlight(index) {{
  svg.querySelectorAll('.ring-highlight').forEach(item => item.style.opacity = item.dataset.index == index ? '.22' : '0');
}}
function showTooltip(event, ring, index) {{
  setHighlight(index);
  tooltip.innerHTML = `<div class="tooltip-title"><i class="tooltip-dot" style="background:${{ring.color}}"></i>${{ring.label}}</div><div class="tooltip-value">${{ring.displayValue || ring.value}}</div>`;
  tooltip.classList.add('active');
  const rect = stage.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const tooltipW = tooltip.offsetWidth;
  const tooltipH = tooltip.offsetHeight;
  const side = x < stage.clientWidth / 2 ? 'right' : 'left';
  tooltip.dataset.side = side;
  const left = side === 'right' ? x + 16 : x - tooltipW - 16;
  tooltip.style.left = `${{Math.max(0, Math.min(stage.clientWidth - tooltipW, left))}}px`;
  tooltip.style.top = `${{Math.max(0, Math.min(stage.clientHeight - tooltipH, y - tooltipH / 2))}}px`;
}}
	function hideTooltip() {{
	  tooltip.classList.remove('active');
	  svg.querySelectorAll('.ring-highlight').forEach(item => item.style.opacity = '0');
	}}
	function postChartHeight() {{
	  const height = Math.ceil(Math.max(180, root.getBoundingClientRect().height || document.body.scrollHeight || 0)) + 2;
	  try {{ parent.postMessage({{type:'analysis-planner-chart-height',height}}, '*'); }} catch (e) {{}}
	}}
	window.addEventListener('resize', render);
	render();
	setTimeout(postChartHeight,80);
	setTimeout(postChartHeight,300);
	</script>
</body>
</html>""", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the double-ring pie component.")
    parser.add_argument("--payload", help="Path to component JSON payload.")
    parser.add_argument("--output", help="Output HTML path.")
    parser.add_argument("--schema", action="store_true", help="Print component schema.")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(component_schema(), ensure_ascii=False, indent=2))
        return 0
    if not args.payload or not args.output:
        raise SystemExit("--payload and --output are required.")
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_document(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
