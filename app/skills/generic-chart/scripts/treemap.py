#!/usr/bin/env python3
"""Standalone treemap component."""

import argparse
import html
import json
from pathlib import Path
from typing import Any


COMPONENT_TYPE = "treemap"
TEXT_COLOR = "#ffffff"
INK_COLOR = "#202633"
MIN_BACKGROUND_LUMINANCE = 0.14
MAX_BACKGROUND_LUMINANCE = 0.66

VISUAL_CHANNEL_MAPPINGS = [
    {
        "semantic": "矩形列表",
        "field": "items",
        "aliases": ["data", "nodes", "segments"],
        "visualChannel": "treemap.rect.area",
        "required": True,
    },
    {
        "semantic": "分类名称",
        "field": "items[].label",
        "aliases": ["name", "category"],
        "visualChannel": "treemap.rect.label",
        "required": True,
    },
    {
        "semantic": "面积数值",
        "field": "items[].value",
        "aliases": ["size", "amount"],
        "visualChannel": "treemap.rect.area",
        "required": True,
    },
    {
        "semantic": "展示值",
        "field": "items[].displayValue",
        "aliases": ["formattedValue"],
        "visualChannel": "treemap.rect.valueLabel",
    },
    {
        "semantic": "矩形颜色",
        "field": "items[].color",
        "aliases": ["fill"],
        "visualChannel": "treemap.rect.color",
    },
    {
        "semantic": "子节点",
        "field": "items[].children",
        "aliases": ["children", "items"],
        "visualChannel": "treemap.hierarchy.children",
    },
    {
        "semantic": "标题",
        "field": "title",
        "aliases": ["name"],
        "visualChannel": "text.title",
    },
    {
        "semantic": "下标题",
        "field": "subtitle",
        "aliases": ["subTitle", "caption"],
        "visualChannel": "text.subtitle",
    },
    {
        "semantic": "图例显示",
        "field": "showLegend",
        "visualChannel": "legend.visibility",
        "default": True,
    },
]

DATA_CONTRACT = [
    {"field": "items[].label", "type": "string", "channel": "treemap.rect.label"},
    {"field": "items[].value", "type": "number", "channel": "treemap.rect.area"},
    {"field": "items[].displayValue", "type": "string", "channel": "treemap.rect.valueLabel"},
    {"field": "items[].color", "type": "string", "channel": "treemap.rect.color"},
    {"field": "items[].children", "type": "array", "channel": "treemap.hierarchy.children"},
    {"field": "title", "type": "string", "channel": "text.title"},
    {"field": "subtitle", "type": "string", "channel": "text.subtitle"},
    {"field": "height", "type": "number", "channel": "layout.height"},
    {"field": "showLegend", "type": "boolean", "channel": "legend.visibility"},
]


def component_schema() -> dict[str, Any]:
    return {
        "type": COMPONENT_TYPE,
        "name": "treemap",
        "visualChannelMappings": VISUAL_CHANNEL_MAPPINGS,
        "dataContract": DATA_CONTRACT,
        "builtInDataSources": [],
    }


def _extract_component(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("chartPayload"), dict):
        chart_payload = dict(payload["chartPayload"])
        for key in ("title", "name", "subtitle"):
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
    raise ValueError("payload must contain a treemap component")


def _format_number(value: float, unit: str) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B{unit}"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M{unit}"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K{unit}"
    return f"{value:,.2f}{unit}"


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
    clean = color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(part * 2 for part in clean)
    if len(clean) != 6:
        return None
    try:
        value = int(clean, 16)
    except ValueError:
        return None
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        scaled = value / 255
        return scaled / 12.92 if scaled <= 0.03928 else ((scaled + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(value) for value in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    lighter = max(_relative_luminance(a), _relative_luminance(b))
    darker = min(_relative_luminance(a), _relative_luminance(b))
    return (lighter + 0.05) / (darker + 0.05)


def _mix_with_white(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(value + (255 - value) * amount) for value in rgb)  # type: ignore[return-value]


def _mix_with_black(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(value * (1 - amount)) for value in rgb)  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _chart_color(color: str) -> str:
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return "#6c7ff2"
    luminance = _relative_luminance(rgb)
    if luminance < MIN_BACKGROUND_LUMINANCE:
        rgb = _mix_with_white(rgb, 0.16)
    elif luminance > MAX_BACKGROUND_LUMINANCE:
        rgb = _mix_with_black(rgb, 0.12)
    return _rgb_to_hex(rgb)


def _readable_text_color(color: str) -> str:
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return TEXT_COLOR
    white = (255, 255, 255)
    ink = _hex_to_rgb(INK_COLOR) or (32, 38, 51)
    return TEXT_COLOR if _contrast_ratio(rgb, white) >= _contrast_ratio(rgb, ink) else INK_COLOR


def _soft_text_shadow(color: str) -> str:
    return "0 1px 2px rgba(15,23,42,.22)" if _readable_text_color(color) == TEXT_COLOR else "none"


def _soften_gradient_end(color: str) -> str:
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return "#5c6fe8"
    adjusted = rgb
    if _relative_luminance(rgb) < 0.32:
        adjusted = _mix_with_white(rgb, 0.10)
    else:
        adjusted = _mix_with_black(rgb, 0.08)
    return _rgb_to_hex(adjusted)


def _normalize_component(component: dict[str, Any]) -> dict[str, Any]:
    props = component.get("props", {})
    raw_items = props.get("items") or component.get("items") or component.get("data") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("treemap items must be a non-empty array")

    palette = [
        "#5b6cff",
        "#e85b85",
        "#19b59f",
        "#ee9b24",
        "#74a82b",
        "#24b7d4",
        "#ef7040",
        "#66758a",
        "#cf5fe2",
        "#22a693",
        "#a47bff",
    ]
    palette_orders = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [3, 2, 1, 5, 6, 8, 7, 0, 9, 4],
        [5, 1, 3, 9, 4, 6, 0, 2, 8, 7],
    ]
    unit = str(props.get("unit") or "")

    def normalize_items(
        items: list[Any],
        depth: int = 0,
        path: str = "",
        parent_color: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized = []
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                raw = {"label": str(index + 1), "value": raw}
            item_id = f"{path}.{index}" if path else str(index)
            children_raw = raw.get("children") or []
            explicit_value = raw.get("value")
            raw_color = raw.get("color")
            if raw_color:
                color = _chart_color(str(raw_color))
            else:
                order = palette_orders[min(depth, len(palette_orders) - 1)]
                palette_index = order[index % len(order)]
                color = _chart_color(palette[palette_index])
            children = normalize_items(children_raw, depth + 1, item_id, color) if isinstance(children_raw, list) else []
            value = float(explicit_value) if explicit_value is not None else sum(child["value"] for child in children)
            value = max(0.0, value)
            display_value = str(raw.get("displayValue") or raw.get("formattedValue") or _format_number(value, unit))
            normalized.append(
                {
                    "_id": item_id,
                    "label": str(raw.get("label") or raw.get("name") or raw.get("category") or index + 1),
                    "value": value,
                    "displayValue": display_value,
                    "color": color,
                    "colorEnd": _soften_gradient_end(color),
                    "textColor": _readable_text_color(color),
                    "textShadow": _soft_text_shadow(color),
                    "children": children,
                }
            )
        return [item for item in normalized if item["value"] > 0]

    items = normalize_items(raw_items)
    if not items:
        raise ValueError("treemap items must include at least one positive value")
    return {
        "items": items,
        "title": str(props.get("title") or component.get("title") or component.get("name") or ""),
        "subtitle": str(props.get("subtitle") or props.get("subTitle") or props.get("caption") or ""),
        "height": int(props.get("height") or 360),
        "unit": unit,
        "showLegend": bool(props.get("showLegend", True)),
        "showValues": bool(props.get("showValues", True)),
        "minLabelArea": float(props.get("minLabelArea") or 2600),
    }


def render_document(payload: dict[str, Any]) -> str:
    config = _normalize_component(_extract_component(payload))
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(config["title"] or "矩形图")
    contract = html.escape(json.dumps(component_schema(), ensure_ascii=False), quote=True)
    props = payload.get("props") if isinstance(payload.get("props"), dict) else {}
    theme_mode = "dark" if (payload.get("theme") or payload.get("themeMode") or props.get("theme") or props.get("themeMode")) == "dark" else "light"
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="{theme_mode}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script>(() => {{ const theme = new URLSearchParams(location.search).get('theme'); if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme; }})();</script>
<style>
*{{box-sizing:border-box}}
:root{{--chart-text-primary:#171b22;--chart-text-secondary:#5f6876;--chart-tooltip-bg:#303030}}
:root[data-theme="dark"]{{color-scheme:dark;--chart-text-primary:#f1f5f9;--chart-text-secondary:#c1cad7;--chart-tooltip-bg:#202733}}
html,body{{width:100%;height:100%;margin:0;background:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;color:var(--chart-text-primary)}}
.treemap-component{{position:relative;width:100%;min-height:{config["height"]}px;padding:18px 22px 16px;background:transparent;overflow:visible}}
.treemap-title{{min-height:22px;margin:0;color:var(--chart-text-primary);font-size:16px;font-weight:800;line-height:1.25}}
.treemap-subtitle{{margin:2px 0 6px;color:var(--chart-text-secondary);font-size:13px;line-height:1.35}}
.treemap-subtitle:empty{{display:none}}
.treemap-stage{{position:relative;width:100%;height:{max(180, config["height"] - 86)}px;border:0;border-radius:0;overflow:hidden;background:transparent}}
.treemap-cell{{position:absolute;display:flex;flex-direction:column;justify-content:flex-start;gap:5px;padding:12px;border:0;border-radius:0;overflow:hidden;color:var(--treemap-text-color,{TEXT_COLOR});text-shadow:var(--treemap-text-shadow,none);cursor:crosshair;box-shadow:none;transition:filter .14s ease,box-shadow .14s ease}}
.treemap-cell:hover{{filter:brightness(1.03);z-index:5;box-shadow:0 8px 18px rgba(15,23,42,.12)}}
.treemap-label{{font-size:13px;font-weight:800;line-height:1.18;white-space:normal;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:break-word;word-break:normal}}
.treemap-value{{font-size:12px;font-weight:650;line-height:1.18;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.94}}
.treemap-cell.has-children{{justify-content:flex-start;padding:11px 12px 9px}}
.treemap-cell.has-children:hover{{z-index:auto;transform:none;box-shadow:none;filter:brightness(1.04)}}
.treemap-cell.has-children .treemap-value{{display:none}}
.treemap-cell.is-child-dimmed{{opacity:.42;filter:saturate(.8)}}
.treemap-cell.is-small{{padding:5px;border-radius:0}}
.treemap-cell.is-small .treemap-label,.treemap-cell.is-small .treemap-value{{display:none}}
.treemap-cell.label-compact{{gap:3px;padding:8px}}
.treemap-cell.label-compact .treemap-label{{font-size:12px;-webkit-line-clamp:1;line-height:1.12}}
.treemap-cell.label-compact .treemap-value{{font-size:11px;line-height:1.12}}
.treemap-cell.label-value-only{{padding:5px}}
.treemap-cell.label-value-only .treemap-label{{display:none}}
.treemap-cell.label-value-only .treemap-value{{font-size:10px;line-height:1.1}}
.treemap-cell.label-name-only .treemap-value{{display:none}}
.treemap-cell.label-name-only .treemap-label{{-webkit-line-clamp:2}}
.treemap-tooltip{{position:absolute;z-index:10;min-width:176px;padding:9px 11px;background:var(--chart-tooltip-bg);color:{TEXT_COLOR};border:0;border-radius:6px;font-size:13px;line-height:1.45;pointer-events:none;opacity:0;visibility:hidden;box-shadow:0 10px 24px rgba(15,23,42,.18)}}
.treemap-tooltip.active{{opacity:1;visibility:visible}}
.tooltip-title{{display:flex;align-items:center;gap:8px;font-weight:700;white-space:nowrap}}
.tooltip-dot,.legend-dot{{width:9px;height:9px;border-radius:2px;flex:none}}
.tooltip-value{{padding-left:17px;white-space:nowrap}}
.treemap-legend{{display:flex;align-items:center;gap:10px 18px;flex-wrap:wrap;margin-top:13px;padding-top:1px;color:var(--chart-text-secondary);font-size:13px;line-height:1.2}}
.legend-item{{display:flex;align-items:center;gap:7px;min-width:0}}
.legend-label{{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.treemap-component.hide-legend .treemap-legend{{display:none}}
@media(max-width:640px){{.treemap-component{{min-height:0;padding:12px 14px 10px}}.treemap-title{{min-height:18px;font-size:14px;line-height:1.2}}.treemap-subtitle{{margin:2px 0 6px;font-size:12px;line-height:1.3}}.treemap-stage{{height:auto;min-height:0;aspect-ratio:900/700}}.treemap-cell{{padding:9px;border-radius:0}}.treemap-legend{{gap:8px 12px;margin-top:8px;font-size:12px}}.treemap-label,.treemap-tooltip{{font-size:12px}}}}
</style>
</head>
<body>
<section class="treemap-component" data-component-contract="{contract}">
  <h2 class="treemap-title">{title}</h2>
  <div class="treemap-subtitle">{html.escape(config["subtitle"])}</div>
  <div class="treemap-stage" role="img" aria-label="{title}"></div>
  <div class="treemap-legend"></div>
  <div class="treemap-tooltip"></div>
</section>
<script>
const config = {config_json};
const root = document.querySelector('.treemap-component');
const stage = root.querySelector('.treemap-stage');
const legend = root.querySelector('.treemap-legend');
const tooltip = root.querySelector('.treemap-tooltip');
root.classList.toggle('hide-legend', !config.showLegend);

const totalValue = items => items.reduce((sum, item) => sum + Number(item.value || 0), 0);
const groupSplit = items => {{
  const sorted = [...items].sort((a,b) => Number(b.value || 0) - Number(a.value || 0));
  const total = totalValue(sorted);
  const a = [];
  const b = [];
  let aSum = 0;
  sorted.forEach(item => {{
    if (aSum <= total / 2 || b.length === 0) {{
      a.push(item);
      aSum += Number(item.value || 0);
    }} else {{
      b.push(item);
    }}
  }});
  return [a, b.length ? b : a.splice(Math.ceil(a.length / 2))];
}};
const layoutItems = (items, x, y, w, h, depth = 0, parentId = '') => {{
  if (!items.length || w <= 0 || h <= 0) return [];
  if (items.length === 1) {{
    const item = items[0];
    const rect = {{item, x, y, w, h, depth, parentId}};
    if (item.children && item.children.length && w * h > config.minLabelArea * 2.4 && h > 86) {{
      const inset = 0;
      const headerH = Math.min(34, Math.max(30, h * .13));
      return [
        rect,
        ...layoutItems(
          item.children,
          x + inset,
          y + headerH,
          Math.max(0, w - inset * 2),
          Math.max(0, h - headerH - inset),
          depth + 1,
          item._id || ''
        ),
      ];
    }}
    return [rect];
  }}
  const [left, right] = groupSplit(items);
  const leftSum = totalValue(left);
  const rightSum = totalValue(right);
  const ratio = leftSum / Math.max(leftSum + rightSum, 1);
  if (w >= h) {{
    const leftW = Math.round(w * ratio);
    return [
      ...layoutItems(left, x, y, leftW, h, depth, parentId),
      ...layoutItems(right, x + leftW, y, w - leftW, h, depth, parentId),
    ];
  }}
  const topH = Math.round(h * ratio);
  return [
    ...layoutItems(left, x, y, w, topH, depth, parentId),
    ...layoutItems(right, x, y + topH, w, h - topH, depth, parentId),
  ];
}};
function setChildDim(parentId, active) {{
  if (!parentId) return;
  stage.querySelectorAll('.treemap-cell').forEach(cell => {{
    if (cell.dataset.parentId === parentId) cell.classList.toggle('is-child-dimmed', active);
  }});
}}
function render() {{
  stage.innerHTML = '';
  legend.innerHTML = '';
  const width = stage.clientWidth || 640;
  const height = stage.clientHeight || 280;
  const stagePad = 0;
  const gap = 0;
  layoutItems(config.items, stagePad, stagePad, width - stagePad * 2, height - stagePad * 2).forEach(rect => {{
    const item = rect.item;
    const cell = document.createElement('div');
    const area = rect.w * rect.h;
    const inset = 0;
    const hasChildren = item.children && item.children.length;
    const renderedW = Math.max(0, rect.w - inset);
    const renderedH = Math.max(0, rect.h - inset);
    const labelMode = getLabelMode(renderedW, renderedH, area, hasChildren);
    cell.className = `treemap-cell ${{hasChildren ? 'has-children' : ''}} ${{labelMode}}`;
    cell.dataset.itemId = item._id || '';
    cell.dataset.parentId = rect.parentId || '';
    cell.style.left = `${{rect.x + inset / 2}}px`;
    cell.style.top = `${{rect.y + inset / 2}}px`;
    cell.style.width = `${{renderedW}}px`;
    cell.style.height = `${{renderedH}}px`;
    cell.style.background = `linear-gradient(135deg, ${{item.color}} 0%, ${{item.colorEnd || item.color}} 100%)`;
    cell.style.setProperty('--treemap-text-color', item.textColor || '#fff');
    cell.style.setProperty('--treemap-text-shadow', item.textShadow || 'none');
    cell.innerHTML = `<div class="treemap-label">${{item.label}}</div>${{config.showValues ? `<div class="treemap-value">${{item.displayValue}}</div>` : ''}}`;
    cell.addEventListener('mouseenter', event => {{
      if (hasChildren) setChildDim(item._id, true);
      showTooltip(event, item);
    }});
    cell.addEventListener('mousemove', event => showTooltip(event, item));
    cell.addEventListener('mouseleave', () => {{
      if (hasChildren) setChildDim(item._id, false);
      hideTooltip();
    }});
    stage.appendChild(cell);
  }});
  if (config.showLegend) {{
    config.items.forEach(item => {{
      const node = document.createElement('div');
      node.className = 'legend-item';
      node.innerHTML = `<i class="legend-dot" style="background:${{item.color}}"></i><span class="legend-label">${{item.label}}</span>`;
      legend.appendChild(node);
    }});
  }}
}}
function getLabelMode(width, height, area, hasChildren) {{
  if (area < config.minLabelArea || width < 42 || height < 24) return 'is-small';
  if (hasChildren) {{
    if (width < 74 || height < 30) return 'is-small';
    if (width < 112 || height < 42) return 'label-compact label-name-only';
    return 'label-name-only';
  }}
  if (height < 38 || width < 70) return config.showValues ? 'label-compact label-value-only' : 'is-small';
  if (height < 54 || width < 112) return 'label-compact label-name-only';
  if (height < 66 || width < 136) return 'label-compact';
  return '';
}}
function showTooltip(event, item) {{
  tooltip.innerHTML = `<div class="tooltip-title"><i class="tooltip-dot" style="background:${{item.color}}"></i>${{item.label}}</div><div class="tooltip-value">${{item.displayValue}}</div>`;
  tooltip.classList.add('active');
  const rootRect = root.getBoundingClientRect();
  const x = event.clientX - rootRect.left + 14;
  const y = event.clientY - rootRect.top + 14;
  const left = Math.min(root.clientWidth - tooltip.offsetWidth - 8, Math.max(8, x));
  const top = Math.min(root.clientHeight - tooltip.offsetHeight - 8, Math.max(8, y));
  tooltip.style.left = `${{left}}px`;
  tooltip.style.top = `${{top}}px`;
}}
function hideTooltip() {{
  tooltip.classList.remove('active');
}}
window.addEventListener('resize', render);
render();
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the treemap component.")
    parser.add_argument("--payload", help="Path to component JSON payload.")
    parser.add_argument("--data-json", help="Inline JSON payload or item array.")
    parser.add_argument("--title", help="Optional title override.")
    parser.add_argument("--output", help="Output HTML path.")
    parser.add_argument("--payload-output", help="Optional output path for the rendered payload.")
    parser.add_argument("--schema", action="store_true", help="Print component schema.")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(component_schema(), ensure_ascii=False, indent=2))
        return 0
    if not (args.payload or args.data_json) or not args.output:
        raise SystemExit("--payload or --data-json, and --output are required.")
    if args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    else:
        parsed = json.loads(args.data_json)
        payload = {"type": COMPONENT_TYPE, "props": {"items": parsed}} if isinstance(parsed, list) else parsed
    if args.title and isinstance(payload, dict):
        props = payload.setdefault("props", {})
        if isinstance(props, dict):
            props["title"] = args.title
        elif not payload.get("title"):
            payload["title"] = args.title
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_document(payload), encoding="utf-8")
    if args.payload_output:
        payload_output = Path(args.payload_output).expanduser().resolve()
        payload_output.parent.mkdir(parents=True, exist_ok=True)
        payload_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
