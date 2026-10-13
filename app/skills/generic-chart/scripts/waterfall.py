#!/usr/bin/env python3
"""Standalone waterfall component."""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


COMPONENT_TYPE = "waterfall"

VISUAL_CHANNEL_MAPPINGS = [
    {
        "semantic": "横轴步骤",
        "field": "items[].label",
        "aliases": ["category", "dimension", "name"],
        "visualChannel": "xAxis.category",
        "required": True,
    },
    {
        "semantic": "瀑布值",
        "field": "items[].value",
        "aliases": ["amount", "delta"],
        "visualChannel": "waterfall.bar.height",
        "required": True,
    },
    {
        "semantic": "柱类型",
        "field": "items[].type",
        "aliases": ["barType"],
        "visualChannel": "waterfall.bar.baseline",
        "default": "delta",
        "supportedValues": ["delta", "total"],
    },
    {
        "semantic": "堆叠到上一柱",
        "field": "items[].stackWithPrevious",
        "aliases": ["stack", "stacked"],
        "visualChannel": "waterfall.bar.stack",
        "default": False,
    },
    {
        "semantic": "颜色",
        "field": "items[].color",
        "aliases": ["fill"],
        "visualChannel": "waterfall.bar.color",
    },
]

DATA_CONTRACT = [
    {"field": "items[].label", "type": "string", "channel": "legend.label"},
    {"field": "items[].value", "type": "number", "channel": "waterfall.bar.height"},
    {"field": "items[].displayValue", "type": "string", "channel": "legend.value"},
    {"field": "items[].type", "type": "delta|total", "channel": "waterfall.bar.baseline"},
    {"field": "items[].stackWithPrevious", "type": "boolean", "channel": "waterfall.bar.stack"},
    {"field": "items[].color", "type": "string", "channel": "waterfall.bar.color"},
    {"field": "compactItems[]", "type": "array", "channel": "responsive.mobileItems"},
    {"field": "showLegend", "type": "boolean", "channel": "legend.visibility"},
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
        "name": "waterfall",
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
    raise ValueError("payload must contain a waterfall component")


def _format_number(value: float, unit: str) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f} T{unit}"
    return f"{value:.2f} B{unit}"


def _normalize_component(component: dict[str, Any]) -> dict[str, Any]:
    nested_props = component.get("props") if isinstance(component.get("props"), dict) else {}
    props = {**component, **nested_props}
    views = props.get("views")
    default_view = str(props.get("defaultView") or "")
    view_configs = {}
    if isinstance(views, dict) and views:
        for key, view in views.items():
            if not isinstance(view, dict):
                continue
            view_items = view.get("items") or view.get("data") or []
            if view_items:
                view_configs[str(key)] = {
                    "label": str(view.get("label") or key),
                    "items": view_items,
                    "compactItems": view.get("compactItems") or view.get("mobileItems") or [],
                }
        if not default_view or default_view not in view_configs:
            default_view = next(iter(view_configs), "")
    items = props.get("items") or props.get("data") or (view_configs.get(default_view, {}).get("items") if view_configs else [])
    if not isinstance(items, list) or not items:
        raise ValueError("waterfall items must be a non-empty array")
    palette = {
        "positive": "#2ab7a1",
        "negative": "#ff3d7f",
        "total": "#3477ed",
        "accent": "#ffad2f",
    }
    unit = str(props.get("unit") or "")
    def normalize_items(raw_items: list[Any]) -> list[dict[str, Any]]:
        normalized_items = []
        running = 0.0
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                raw = {"label": str(index + 1), "value": raw}
            value = float(raw.get("value") or 0)
            bar_type = str(raw.get("type") or "delta").lower()
            if bar_type not in {"delta", "total"}:
                bar_type = "delta"
            start = 0.0 if bar_type == "total" else running
            end = value if bar_type == "total" else running + value
            running = end
            color = str(raw.get("color") or "")
            if not color:
                color = palette["total"] if bar_type == "total" else palette["positive"] if value >= 0 else palette["negative"]
            display_value = str(raw.get("displayValue") or _format_number(value, unit))
            normalized_items.append(
                {
                    "label": str(raw.get("label") or raw.get("name") or index + 1),
                    "value": value,
                    "start": start,
                    "end": end,
                    "type": bar_type,
                    "stackWithPrevious": bool(raw.get("stackWithPrevious") or raw.get("stack") or raw.get("stacked")),
                    "displayValue": display_value,
                    "tooltipValue": str(raw.get("tooltipValue") or f"{display_value}{unit}"),
                    "color": color,
                    "legendColor": str(raw.get("legendColor") or color),
                }
            )
        return normalized_items

    normalized = normalize_items(items)
    normalized_views = {}
    for key, view in view_configs.items():
        normalized_views[key] = {
            "label": view["label"],
            "items": normalize_items(view["items"]),
            "compactItems": normalize_items(view["compactItems"]) if view.get("compactItems") else [],
        }
    return {
        "title": str(component.get("title") or props.get("title") or ""),
        "items": normalized,
        "compactItems": normalize_items(props.get("compactItems") or props.get("mobileItems") or [])
        if props.get("compactItems") or props.get("mobileItems")
        else [],
        "views": normalized_views,
        "defaultView": default_view,
        "height": int(props.get("height") or 320),
        "unit": unit,
        "showLegend": bool(props.get("showLegend", True)),
        "showXAxis": bool(props.get("showXAxis", False)),
        "gridCount": int(props.get("gridCount") or 5),
        "connectorColor": str(props.get("connectorColor") or "#6f6f6f"),
    }


def render_document(payload: dict[str, Any]) -> str:
    config = _normalize_component(_extract_component(payload))
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(config["title"] or "瀑布图")
    contract = html.escape(json.dumps(component_schema(), ensure_ascii=False), quote=True)
    return _finalize_document_theme(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light;--business-bg-fff:#fff;--business-text-171717:#171717;--business-text-1a1a1a:#1a1a1a;--business-text-secondary:#5f6876;--business-bg-f1f1f1:#f1f1f1;--business-border-ececec:#ececec;--business-border-606060:#606060;--business-text-f7f7f7:#f7f7f7;--business-bg-3a3a3a:#3a3a3a;--business-text-fff:#fff;--business-bg-e8e8e8:#e8e8e8;--business-border-3a3a3a:#3a3a3a;}}
:root[data-theme="dark"]{{color-scheme:dark;--business-bg-fff:#181e28;--business-text-171717:#f1f5f9;--business-text-1a1a1a:#f1f5f9;--business-text-secondary:#c1cad7;--business-bg-f1f1f1:#202733;--business-border-ececec:#2b3544;--business-border-606060:#334052;--business-text-f7f7f7:#f1f5f9;--business-bg-3a3a3a:#202733;--business-text-fff:#f1f5f9;--business-bg-e8e8e8:#2b3544;--business-border-3a3a3a:#334052;}}

*{{box-sizing:border-box}}
html,body{{width:100%;height:100%;margin:0;background:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;color:var(--business-text-171717)}}
.waterfall-component{{position:relative;width:100%;min-height:{config["height"]}px;padding:14px 28px 14px;background:transparent;overflow:visible}}
.waterfall-title{{height:24px;margin:0 0 6px;font-size:16px;font-weight:800;line-height:1.2}}
.waterfall-tabs{{position:absolute;z-index:4;top:8px;right:28px;display:flex;gap:10px;align-items:center;font-size:15px}}
.waterfall-tab{{appearance:none;border:0;background:transparent;padding:8px 12px;border-radius:8px;color:var(--business-text-1a1a1a);font:inherit;font-weight:500;line-height:1;cursor:pointer}}
.waterfall-tab.active{{background:var(--business-bg-f1f1f1);font-weight:800}}
.waterfall-layout{{display:grid;grid-template-columns:1fr;align-items:center;gap:0;width:100%}}
.waterfall-stage{{position:relative;width:100%;height:180px;margin-top:6px}}
svg{{display:block;width:100%;height:100%;overflow:visible}}
.grid-line{{stroke:var(--business-border-ececec);stroke-width:1}}
.axis-line{{stroke:var(--business-border-606060);stroke-width:1}}
.connector{{stroke-dasharray:5 5;stroke-width:1.2;fill:none}}
.bar{{cursor:crosshair}}
.hit-area{{cursor:crosshair}}
.highlight{{fill:var(--business-text-f7f7f7);pointer-events:none}}
.waterfall-tooltip{{position:absolute;z-index:5;min-width:160px;padding:7px 10px;background:var(--business-bg-3a3a3a);color:var(--business-text-fff);border-radius:5px;font-size:13px;line-height:1.5;pointer-events:none;opacity:0;visibility:hidden}}
.waterfall-tooltip::after{{content:"";position:absolute;left:var(--arrow-left,50%);bottom:-8px;transform:translateX(-50%);border-left:9px solid transparent;border-right:9px solid transparent;border-top:9px solid var(--business-border-3a3a3a)}}
.waterfall-tooltip.active{{opacity:1;visibility:visible}}
.tooltip-row{{display:flex;justify-content:space-between;align-items:center;gap:18px;white-space:nowrap}}
.tooltip-label{{display:flex;align-items:center;gap:7px;color:var(--business-text-fff)}}
.tooltip-dot,.legend-dot{{width:9px;height:9px;border-radius:50%;flex:none}}
.waterfall-legend{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 20px;margin-top:18px;padding-bottom:8px;color:var(--business-text-secondary);font-size:14px;line-height:1.2}}
.waterfall-component.hide-legend .waterfall-layout{{grid-template-columns:1fr}}
.waterfall-component.hide-legend .waterfall-legend{{display:none}}
.legend-separator{{grid-column:1/-1;height:1px;background:var(--business-bg-e8e8e8);margin:-2px 0 0}}
.legend-label{{display:flex;align-items:center;gap:12px;min-width:0}}
.legend-label span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.legend-value{{font-weight:800;text-align:right;white-space:nowrap}}
.legend-label.is-total,.legend-value.is-total{{font-weight:800}}
@media(min-width:900px){{.waterfall-component{{max-width:1040px;padding-left:36px;padding-right:36px}}.waterfall-layout{{grid-template-columns:minmax(520px,640px) 360px;justify-content:start;gap:18px}}.waterfall-stage{{height:180px}}.waterfall-legend{{width:100%;max-width:340px;margin-top:14px}}}}
@media(max-width:640px){{.waterfall-component{{padding:12px 16px 12px}}.waterfall-stage{{height:168px}}.waterfall-tooltip,.waterfall-legend{{font-size:13px}}.waterfall-legend{{gap:9px 12px;margin-top:14px}}}}
</style>
</head>
<body>
<section class="waterfall-component" data-component-contract="{contract}">
  <h2 class="waterfall-title">{title}</h2>
  <div class="waterfall-tabs"></div>
  <div class="waterfall-layout">
    <div class="waterfall-stage">
      <svg role="img" aria-label="{title}"></svg>
      <div class="waterfall-tooltip"></div>
    </div>
    <div class="waterfall-legend"></div>
  </div>
</section>
<script>
const config = {config_json};
const root = document.querySelector('.waterfall-component');
const stage = root.querySelector('.waterfall-stage');
const svg = root.querySelector('svg');
const legend = root.querySelector('.waterfall-legend');
const tooltip = root.querySelector('.waterfall-tooltip');
const tabs = root.querySelector('.waterfall-tabs');
const NS = 'http://www.w3.org/2000/svg';
let activeView = config.defaultView || Object.keys(config.views || {{}})[0] || '';

const node = (name, attrs = {{}}, text = '') => {{
  const el = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value));
  if (text !== '') el.textContent = text;
  return el;
}};
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const format = value => value;
const niceStep = (range, count = 4) => {{
  const rough = Math.max(range / count, 0.0001);
  const power = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / power;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * power;
}};
const currentConfig = () => {{
  if (activeView && config.views && config.views[activeView]) {{
    const view = config.views[activeView];
    const useCompact = window.matchMedia('(max-width: 640px)').matches && view.compactItems && view.compactItems.length;
    return {{...config, items: useCompact ? view.compactItems : view.items}};
  }}
  const useCompact = window.matchMedia('(max-width: 640px)').matches && config.compactItems && config.compactItems.length;
  if (useCompact) return {{...config, items: config.compactItems}};
  return config;
}};
const axisRange = (items) => {{
  const values = items.flatMap(item => [number(item.start), number(item.end)]);
  let min = Math.min(0, ...values);
  let max = Math.max(0, ...values);
  if (min === max) {{ min -= 1; max += 1; }}
  const allNonNegative = values.every(value => value >= 0);
  const pad = (max - min) * .035;
  min = allNonNegative ? 0 : min - pad;
  max += pad;
  if (allNonNegative) return {{min:0, max}};
  const step = niceStep(max - min, config.gridCount - 1);
  return {{min:Math.floor(min / step) * step, max:Math.ceil(max / step) * step}};
}};
const visualGroups = () => {{
  const current = currentConfig();
  const groups = [];
  current.items.forEach((item) => {{
    const previous = groups[groups.length - 1];
    if (item.stackWithPrevious && previous) {{
      previous.items.push(item);
      previous.end = item.end;
      previous.value += item.value;
    }} else {{
      groups.push({{items:[item], start:item.start, end:item.end, value:item.value, type:item.type}});
    }}
  }});
  return groups;
}};

function render() {{
  svg.innerHTML = '';
  legend.innerHTML = '';
  renderTabs();
  const current = currentConfig();
  root.classList.toggle('hide-legend', !current.showLegend);
  const width = svg.clientWidth || 900;
  const height = svg.clientHeight || 270;
  const margin = {{top:18,right:8,bottom:1,left:0}};
  const plotW = Math.max(180, width - margin.left - margin.right);
  const plotH = Math.max(120, height - margin.top - margin.bottom);
  const rows = current.items;
  const groups = visualGroups();
  const range = axisRange(rows);
  const y = value => margin.top + plotH - (number(value) - range.min) / (range.max - range.min) * plotH;
  const zeroY = y(0);
  const groupW = plotW / Math.max(groups.length, 1);
  const barW = Math.min(82, groupW * .36);
  const gridCount = Math.max(2, current.gridCount || 5);

  for (let index = 0; index < gridCount; index += 1) {{
    const gy = margin.top + plotH * index / (gridCount - 1);
    svg.appendChild(node('line', {{x1:margin.left,y1:gy,x2:margin.left+plotW,y2:gy,class:'grid-line'}}));
  }}
  svg.appendChild(node('line', {{x1:margin.left,y1:zeroY,x2:margin.left+plotW,y2:zeroY,class:'axis-line'}}));

  groups.forEach((group, index) => {{
    const groupX = margin.left + groupW * index;
    const center = groupX + groupW / 2;
    const x = center - barW / 2;
    const highlight = node('rect', {{x:groupX,y:margin.top,width:groupW,height:plotH,class:'highlight','data-highlight-index':index}});
    highlight.style.opacity = '0';
    svg.appendChild(highlight);
    group.items.forEach((item) => {{
      const startY = y(item.start);
      const endY = y(item.end);
      const barY = Math.min(startY, endY);
      const barH = Math.max(3, Math.abs(startY - endY));
      svg.appendChild(node('rect', {{x,y:barY,width:barW,height:barH,rx:0,fill:item.color,class:'bar'}}));
    }});
    if (config.showXAxis) {{
      svg.appendChild(node('text', {{x:center,y:margin.top+plotH+16,'text-anchor':'middle',fill:'var(--business-text-171717)','font-size':'12'}}, group.items.map(item => item.label).join('+')));
    }}
  }});

  groups.slice(0, -1).forEach((group, index) => {{
    const x1 = margin.left + groupW * (index + .5) + barW / 2;
    const x2 = margin.left + groupW * (index + 1.5) - barW / 2;
    const connectorY = y(group.end);
    svg.appendChild(node('line', {{x1,y1:connectorY,x2,y2:connectorY,stroke:current.connectorColor,class:'connector'}}));
  }});

  groups.forEach((group, index) => {{
    const groupX = margin.left + groupW * index;
    const center = groupX + groupW / 2;
    const hit = node('rect', {{x:groupX,y:margin.top,width:groupW,height:plotH,fill:'transparent',class:'hit-area'}});
    hit.addEventListener('mouseenter', () => showTooltip(group, index, center));
    hit.addEventListener('mousemove', () => showTooltip(group, index, center));
    hit.addEventListener('mouseleave', hideTooltip);
    svg.appendChild(hit);
  }});

  if (current.showLegend) {{
    rows.forEach((item, index) => {{
      if (item.type === 'total' && index > 0) {{
        const separator = document.createElement('div');
        separator.className = 'legend-separator';
        legend.appendChild(separator);
      }}
      const label = document.createElement('div');
      label.className = `legend-label ${{item.type === 'total' ? 'is-total' : ''}}`;
      label.innerHTML = `<i class="legend-dot" style="background:${{item.legendColor}}"></i><span>${{item.label}}</span>`;
      const value = document.createElement('div');
      value.className = `legend-value ${{item.type === 'total' ? 'is-total' : ''}}`;
      value.textContent = item.displayValue;
      legend.appendChild(label);
      legend.appendChild(value);
    }});
  }}
}}

function renderTabs() {{
  tabs.innerHTML = '';
  const views = config.views || {{}};
  const keys = Object.keys(views);
  if (keys.length <= 1) return;
  keys.forEach(key => {{
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `waterfall-tab ${{key === activeView ? 'active' : ''}}`;
    button.textContent = views[key].label || key;
    button.addEventListener('click', () => {{
      activeView = key;
      hideTooltip();
      render();
    }});
    tabs.appendChild(button);
  }});
}}

function showTooltip(group, index, centerX) {{
  svg.querySelectorAll('.highlight').forEach(el => el.style.opacity = el.dataset.highlightIndex == index ? '.42' : '0');
  tooltip.innerHTML = group.items.map(item => `<div class="tooltip-row"><span class="tooltip-label"><i class="tooltip-dot" style="background:${{item.legendColor}}"></i>${{item.label}}</span><span>${{item.tooltipValue || item.displayValue}}</span></div>`).join('');
  tooltip.classList.add('active');
  const desiredLeft = centerX - tooltip.offsetWidth / 2;
  const left = Math.min(stage.clientWidth - tooltip.offsetWidth - 8, Math.max(8, desiredLeft));
  tooltip.style.left = `${{left}}px`;
  tooltip.style.top = `${{-(tooltip.offsetHeight + 10)}}px`;
  tooltip.style.setProperty('--arrow-left', `${{Math.min(tooltip.offsetWidth - 14, Math.max(14, centerX - left))}}px`);
}}
function hideTooltip() {{
  tooltip.classList.remove('active');
  svg.querySelectorAll('.highlight').forEach(el => el.style.opacity = '0');
}}
window.addEventListener('resize', render);
render();
</script>
{(Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8")}
</body>
</html>""", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the waterfall component.")
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
