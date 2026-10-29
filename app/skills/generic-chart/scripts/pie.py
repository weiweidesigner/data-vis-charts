#!/usr/bin/env python3
"""Standalone donut pie component."""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


COMPONENT_TYPE = "pie"

VISUAL_CHANNEL_MAPPINGS = [
    {
        "semantic": "扇区列表",
        "field": "items",
        "aliases": ["slices", "segments"],
        "visualChannel": "pie.arc.angle",
        "required": True,
    },
    {
        "semantic": "中心文本",
        "field": "centerLabel",
        "aliases": ["totalLabel"],
        "visualChannel": "pie.center.label",
    },
    {
        "semantic": "环形宽度",
        "field": "ringWidth",
        "aliases": ["thickness"],
        "visualChannel": "pie.ring.width",
        "default": 28,
    },
    {
        "semantic": "下标题",
        "field": "subtitle",
        "aliases": ["subTitle", "caption"],
        "visualChannel": "text.subtitle",
    },
    {
        "semantic": "标题",
        "field": "title",
        "aliases": ["name"],
        "visualChannel": "text.title",
    },
    {
        "semantic": "图例位置",
        "field": "legendPosition",
        "visualChannel": "legend.layout",
        "default": "bottom",
        "supportedValues": ["bottom"],
    },
]

DATA_CONTRACT = [
    {"field": "items[].label", "type": "string", "channel": "legend.label"},
    {"field": "items[].value", "type": "number", "channel": "pie.arc.angle"},
    {"field": "items[].displayValue", "type": "string", "channel": "legend.value"},
    {"field": "items[].color", "type": "string", "channel": "pie.arc.color"},
    {"field": "title", "type": "string", "channel": "text.title"},
    {"field": "subtitle", "type": "string", "channel": "text.subtitle"},
    {"field": "showLegendValues", "type": "boolean", "channel": "legend.valueVisibility"},
    {"field": "showCenterLabel", "type": "boolean", "channel": "pie.center.visibility"},
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
        "name": "pie",
        "visualChannelMappings": VISUAL_CHANNEL_MAPPINGS,
        "dataContract": DATA_CONTRACT,
        "builtInDataSources": [],
    }


def _extract_component(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("chartPayload"), dict):
        chart_payload = dict(payload["chartPayload"])
        for key in ("title", "name"):
            if key in payload and key not in chart_payload:
                chart_payload[key] = payload[key]
        payload = chart_payload
    if payload.get("type") == COMPONENT_TYPE:
        return payload
    if isinstance(payload.get("props"), dict) or isinstance(payload.get("items"), list) or isinstance(payload.get("data"), list):
        return payload
    root = payload.get("root")
    if isinstance(root, dict) and root.get("type") == "component" and isinstance(root.get("component"), dict):
        return root["component"]
    component = payload.get("component")
    if isinstance(component, dict):
        return component
    raise ValueError("payload must contain a pie component")


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return bool(value)


def _normalize_component(component: dict[str, Any]) -> dict[str, Any]:
    if isinstance(component.get("chartPayload"), dict):
        chart_payload = dict(component["chartPayload"])
        for key in ("title", "name"):
            if key in component and key not in chart_payload:
                chart_payload[key] = component[key]
        component = chart_payload
    props = component.get("props", {})
    items = props.get("items") or component.get("items") or component.get("data") or []
    if not isinstance(items, list) or not items:
        raise ValueError("pie items must be a non-empty array")
    palette = ["#4d63f6", "#00b899", "#ff2f57", "#d97706", "#8e4ec6", "#0090ff", "#ab4aba", "#46a758"]
    reserved_colors = {str(item.get("color")).lower() for item in items if isinstance(item, dict) and item.get("color")}
    available_colors = [color for color in palette if color.lower() not in reserved_colors] or palette
    normalized_items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {"label": str(index + 1), "value": item}
        value = float(item.get("value") or 0)
        normalized_items.append(
            {
                "label": str(item.get("label") or item.get("name") or index + 1),
                "value": max(0, value),
                "displayValue": str(item.get("displayValue") or ""),
                "color": str(item.get("color") or f"var(--sv-chart-series-{palette.index(available_colors[index % len(available_colors)])+1},{available_colors[index % len(available_colors)]})"),
            }
        )
    total = sum(item["value"] for item in normalized_items)
    for item in normalized_items:
        percent = item["value"] / total * 100 if total else 0
        item["percent"] = percent
        if not item["displayValue"]:
            item["displayValue"] = f"{item['value']:,.2f} ({percent:.2f}%)"
    return {
        "items": normalized_items,
        "title": str(props.get("title") or component.get("title") or component.get("name") or ""),
        "centerLabel": str(props.get("centerLabel") or component.get("title") or f"{total:,.2f}"),
        "subtitle": str(props.get("subtitle") or props.get("subTitle") or props.get("caption") or ""),
        "badgeLabel": str(props.get("badgeLabel") or props.get("yearLabel") or props.get("periodLabel") or ""),
        "legendPosition": "bottom",
        "showLegendValues": _as_bool(props.get("showLegendValues"), False),
        "showCenterLabel": _as_bool(props.get("showCenterLabel"), True),
        "ringWidth": int(props.get("ringWidth") or 28),
        "height": int(props.get("height") or 360),
    }


def render_document(payload: dict[str, Any]) -> str:
    config = _normalize_component(_extract_component(payload))
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    contract = html.escape(json.dumps(component_schema(), ensure_ascii=False), quote=True)
    light = ['#4d63f6','#00b899','#ff2f57','#d97706','#8e4ec6','#0090ff','#ab4aba','#46a758']
    dark = ['#8294ff','#34d3ad','#ff7188','#f6ad55','#d19dff','#70b8ff','#e796f3','#7ce2bd']
    series_css = ':root{' + ''.join(f'--sv-chart-series-{i+1}:{color};' for i,color in enumerate(light)) + '}:root[data-theme="dark"]{' + ''.join(f'--sv-chart-series-{i+1}:{color};' for i,color in enumerate(dark)) + '}'
    return _finalize_document_theme(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pie</title>
<style>
{series_css}
:root{{color-scheme:light;--business-text-151922:#151922;--business-text-687386:#687386;--business-text-fff:#fff;--business-text-4b5563:#4b5563;}}
:root[data-theme="dark"]{{color-scheme:dark;--business-text-151922:#f1f5f9;--business-text-687386:#c1cad7;--business-text-fff:#f1f5f9;--business-text-4b5563:#c1cad7;}}

*{{box-sizing:border-box}}
html,body{{width:100%;min-height:0;margin:0;background:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;color:var(--business-text-151922);overflow:hidden}}
.pie-component{{position:relative;width:100%;min-height:0;padding:0 1px 0 0;background:transparent;overflow:hidden;container-type:inline-size}}
.pie-header{{display:grid;grid-template-columns:minmax(0,1fr);align-items:start;column-gap:12px;width:100%;margin:0 0 10px}}
.pie-heading{{min-width:0}}
.pie-title{{margin:0;padding:0;color:var(--business-text-151922);font-size:20px;font-weight:700;line-height:1.35;letter-spacing:-.15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pie-title:empty{{display:none}}
.pie-subtitle{{margin:4px 0 0;padding:0;color:var(--business-text-687386);font-size:13px;font-weight:400;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pie-subtitle:empty{{display:none}}
.pie-badge{{align-self:start;margin:3px 0 0;padding:0;color:var(--business-text-687386);font-size:12px;font-weight:500;line-height:1.2;white-space:nowrap}}
.pie-badge:empty{{display:none}}
.pie-layout{{display:grid;grid-template-columns:minmax(160px,220px) fit-content(360px);align-items:center;justify-content:start;gap:clamp(12px,4cqw,48px);width:100%;min-width:0}}
.pie-stage{{position:relative;width:100%;height:210px;min-width:0;margin:0;overflow:visible}}
svg{{display:block;width:100%;height:100%;overflow:visible}}
.pie-center{{font-size:16px;font-weight:600;fill:var(--business-text-151922);text-anchor:middle;dominant-baseline:middle}}
.pie-slice{{cursor:pointer;transition:opacity .12s ease}}
.pie-highlight{{pointer-events:none;transition:opacity .12s ease}}
.pie-tooltip{{position:absolute;z-index:5;min-width:150px;max-width:calc(100% - 2px);padding:9px 12px;background:rgba(21,25,34,.94);color:var(--business-text-fff);border-radius:6px;font-size:12px;line-height:1.5;pointer-events:none;opacity:0;visibility:hidden;transition:opacity .12s ease}}
.pie-tooltip::after{{content:"";position:absolute;top:50%;width:10px;height:10px;background:rgba(21,25,34,.94);transform:translateY(-50%) rotate(45deg)}}
.pie-tooltip[data-side="right"]::after{{left:-5px}}
.pie-tooltip[data-side="left"]::after{{right:-5px}}
.tooltip-title{{display:flex;align-items:center;gap:8px;min-width:0;white-space:nowrap}}
.tooltip-title span{{overflow:hidden;text-overflow:ellipsis}}
.tooltip-dot,.legend-dot{{width:8px;height:8px;border-radius:50%;flex:0 0 8px}}
.tooltip-value{{padding-left:16px;white-space:nowrap}}
.pie-tooltip.active{{opacity:1;visibility:visible}}
.pie-legend{{display:flex;flex-wrap:wrap;align-items:center;justify-self:start;gap:10px 18px;width:max-content;max-width:100%;min-width:0;margin:0;padding:0 1px 0 0;font-size:10px;line-height:1.25}}
.legend-entry{{display:inline-flex;align-items:center;gap:8px;min-width:0}}
.legend-label{{display:flex;align-items:center;gap:8px;min-width:0;color:var(--business-text-4b5563)}}
.legend-label span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.legend-value{{color:var(--business-text-151922);font-weight:700;text-align:left;white-space:nowrap}}
.pie-component.legend-bottom .pie-layout{{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:4px}}
.pie-component.legend-bottom .pie-stage{{width:min(100%,320px);height:190px;margin:0 auto}}
.pie-component.legend-bottom .pie-legend{{display:flex;justify-content:center;align-content:center;justify-self:center;gap:10px 18px;width:min(100%,720px);max-width:100%;padding-right:1px;font-size:10px}}
.pie-component.legend-bottom .legend-entry{{display:inline-flex;align-items:center;gap:8px;max-width:100%}}
.pie-component.legend-bottom .legend-label{{gap:7px}}
.pie-component.legend-bottom .legend-value{{font-weight:600}}
@media(max-width:759px){{
 .pie-component{{min-height:0}}
 .pie-header{{margin-bottom:8px;column-gap:8px}}
 .pie-title{{font-size:17px}}
 .pie-subtitle{{margin-top:3px;font-size:12px}}
 .pie-badge{{margin-top:2px;font-size:11px}}
 .pie-layout{{grid-template-columns:1fr;justify-items:center;gap:8px}}
 .pie-stage{{width:min(100%,260px);height:190px;margin:0 auto}}
 .pie-legend{{justify-content:center;justify-self:center;gap:8px 14px;width:min(100%,360px);font-size:10px}}
 .legend-entry{{gap:8px}}
 .pie-center{{font-size:14px}}
 .pie-tooltip{{min-width:140px;font-size:11px}}
 .pie-component.legend-bottom .pie-stage{{width:min(100%,260px);height:178px}}
 .pie-component.legend-bottom .pie-legend{{gap:8px;font-size:10px}}
}}
</style>
</head>
<body>
<section class="pie-component" data-renderer-version="pie-spacing-v2" data-component-contract="{contract}">
  <div class="pie-header">
    <div class="pie-heading">
      <h2 class="pie-title">{html.escape(config["title"])}</h2>
      <div class="pie-subtitle">{html.escape(config["subtitle"])}</div>
    </div>
  </div>
  <div class="pie-layout">
    <div class="pie-stage"><svg role="img" aria-label="pie"></svg><div class="pie-tooltip"></div></div>
    <div class="pie-legend"></div>
  </div>
</section>
<script>
const config = {config_json};
const root = document.querySelector('.pie-component');
const stage = root.querySelector('.pie-stage');
const svg = root.querySelector('svg');
const legend = root.querySelector('.pie-legend');
const tooltip = root.querySelector('.pie-tooltip');
const NS = 'http://www.w3.org/2000/svg';
const total = config.items.reduce((sum,item) => sum + Number(item.value || 0), 0);
root.classList.toggle('legend-bottom', config.legendPosition === 'bottom');

const node = (name, attrs = {{}}, text = '') => {{
  const el = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value));
  if (text !== '') el.textContent = text;
  return el;
}};
const polar = (cx, cy, r, angle) => {{
  const rad = (angle - 90) * Math.PI / 180;
  return {{x:cx + r * Math.cos(rad), y:cy + r * Math.sin(rad)}};
}};
const arcPath = (cx, cy, outerR, innerR, start, end) => {{
  const large = end - start > 180 ? 1 : 0;
  const p1 = polar(cx, cy, outerR, start);
  const p2 = polar(cx, cy, outerR, end);
  const p3 = polar(cx, cy, innerR, end);
  const p4 = polar(cx, cy, innerR, start);
  return `M ${{p1.x}} ${{p1.y}} A ${{outerR}} ${{outerR}} 0 ${{large}} 1 ${{p2.x}} ${{p2.y}} L ${{p3.x}} ${{p3.y}} A ${{innerR}} ${{innerR}} 0 ${{large}} 0 ${{p4.x}} ${{p4.y}} Z`;
}};
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function render() {{
  svg.innerHTML = '';
  legend.innerHTML = '';
  const width = svg.clientWidth || 320;
  const height = svg.clientHeight || 250;
  const safe = 8;
  const cx = width / 2;
  const cy = height / 2;
  const outerR = Math.max(24, Math.min(88, Math.min(width, height) / 2 - safe));
  const ringWidth = clamp(Number(config.ringWidth) || 28, 12, Math.max(12, outerR * 0.32));
  const innerR = Math.max(20, outerR - ringWidth);
  let angle = 0;

  config.items.forEach((item, index) => {{
    const start = angle;
    const end = angle + (total ? Number(item.value || 0) / total * 360 : 0);
    angle = end;
    if (end <= start) return;
    const slice = node('path', {{d:arcPath(cx,cy,outerR,innerR,start,end),fill:item.color,class:'pie-slice','data-index':index}});
    slice.addEventListener('mouseenter', event => showTooltip(event, item, index));
    slice.addEventListener('mousemove', event => showTooltip(event, item, index));
    slice.addEventListener('mouseleave', hideTooltip);
    svg.appendChild(slice);
    const highlight = node('path', {{d:arcPath(cx,cy,outerR + 6,outerR,start,end),fill:item.color,class:'pie-highlight','data-index':index}});
    highlight.style.opacity = '0';
    svg.appendChild(highlight);
  }});

  if (config.showCenterLabel) {{
    const centerText = String(config.centerLabel || '');
    const centerFontSize = centerText.length > 14 ? 11 : centerText.length > 9 ? 13 : 16;
    svg.appendChild(node('text', {{x:cx,y:cy,class:'pie-center','font-size':centerFontSize}}, centerText));
  }}

  config.items.forEach(item => {{
    const entry = document.createElement('div');
    entry.className = 'legend-entry';
    const label = document.createElement('div');
    label.className = 'legend-label';
    label.innerHTML = `<i class="legend-dot" style="background:${{item.color}}"></i><span>${{item.label}}</span>`;
    entry.appendChild(label);
    if (config.showLegendValues) {{
      const value = document.createElement('div');
      value.className = 'legend-value';
      value.textContent = item.displayValue;
      entry.appendChild(value);
    }}
    legend.appendChild(entry);
  }});
  postChartHeight();
}}
function setHighlight(index) {{
  svg.querySelectorAll('.pie-highlight').forEach(item => item.style.opacity = item.dataset.index == index ? '.22' : '0');
}}
function showTooltip(event, item, index) {{
  setHighlight(index);
  tooltip.innerHTML = `<div class="tooltip-title"><i class="tooltip-dot" style="background:${{item.color}}"></i><span>${{item.label}}</span></div><div class="tooltip-value">${{item.displayValue}}</div>`;
  tooltip.classList.add('active');
  const rect = stage.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const tooltipW = tooltip.offsetWidth;
  const tooltipH = tooltip.offsetHeight;
  const side = x < stage.clientWidth / 2 ? 'right' : 'left';
  tooltip.dataset.side = side;
  const proposedLeft = side === 'right' ? x + 14 : x - tooltipW - 14;
  const safe = 1;
  tooltip.style.left = `${{clamp(proposedLeft, safe, Math.max(safe, stage.clientWidth - tooltipW - safe))}}px`;
  tooltip.style.top = `${{clamp(y - tooltipH / 2, safe, Math.max(safe, stage.clientHeight - tooltipH - safe))}}px`;
}}
function hideTooltip() {{
  tooltip.classList.remove('active');
  svg.querySelectorAll('.pie-highlight').forEach(item => item.style.opacity = '0');
}}
function postChartHeight() {{
  const height = Math.ceil(Math.max(180, root.getBoundingClientRect().bottom || document.body.scrollHeight || 0)) + 2;
  try {{ parent.postMessage({{type:'analysis-planner-chart-height',height}}, '*'); }} catch (e) {{}}
}}
window.addEventListener('resize', render);
render();
setTimeout(postChartHeight,80);
setTimeout(postChartHeight,300);
</script>
{(Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8")}
</body>
</html>""", payload)

def _default_payload(title: str | None = None) -> dict[str, Any]:
    return {
        "type": COMPONENT_TYPE,
        "title": title or "饼图",
        "props": {
            "items": [
                {"label": "待补充", "value": 1, "displayValue": "待补充"},
            ],
        },
    }


def _load_payload(path: str | None, data_json: str | None, data: str | None, title: str | None) -> dict[str, Any]:
    if path:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    elif data_json:
        payload = json.loads(data_json)
    elif data:
        payload = {"type": COMPONENT_TYPE, "title": title or "", "props": {"items": json.loads(data)}}
    else:
        payload = _default_payload(title)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if isinstance(payload.get("chartPayload"), dict):
        chart_payload = dict(payload["chartPayload"])
        for key in ("title", "name"):
            if key in payload and key not in chart_payload:
                chart_payload[key] = payload[key]
        payload = chart_payload
    if title:
        payload["title"] = title
    return payload


def _write_payload_output(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the donut pie component.")
    parser.add_argument("--code")
    parser.add_argument("--title")
    parser.add_argument("--payload", help="Path to component JSON payload.")
    parser.add_argument("--data")
    parser.add_argument("--data-json")
    parser.add_argument("--style-json")
    parser.add_argument("--output", help="Output HTML path.")
    parser.add_argument("--payload-output")
    parser.add_argument("--schema", action="store_true", help="Print component schema.")
    args, _ = parser.parse_known_args()
    if args.schema:
        print(json.dumps(component_schema(), ensure_ascii=False, indent=2))
        return 0
    if not args.output:
        raise SystemExit("--output is required.")
    payload = _load_payload(args.payload, args.data_json, args.data, args.title)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_document(payload), encoding="utf-8")
    _write_payload_output(args.payload_output, payload)
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
