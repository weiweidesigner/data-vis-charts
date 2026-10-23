#!/usr/bin/env python3
"""Standalone bar chart component."""

from __future__ import annotations

import argparse
import json

import html
import json
import re
from pathlib import Path
from typing import Any


PALETTE = ["#4387f5", "#4bc3d5", "#f9730c", "#8b5cf6", "#10b981", "#ef4444"]


def _financial_market(component: dict[str, Any], props: dict[str, Any], data: list[Any], x_field: str) -> str:
    """Return an explicit or safely inferred market color convention."""
    requested = str(
        props.get("financialMarket")
        or component.get("financialMarket")
        or props.get("market")
        or component.get("market")
        or ""
    ).strip().upper()
    aliases = {
        "CN": "CN", "A": "CN", "ASHARE": "CN", "A-SHARE": "CN", "A股": "CN",
        "HK": "HK", "HONGKONG": "HK", "HONG KONG": "HK", "港股": "HK",
        "US": "US", "USA": "US", "U.S.": "US", "美股": "US",
    }
    if requested in aliases:
        return aliases[requested]
    if requested:
        raise ValueError("Unsupported financialMarket; use CN, HK or US from the source market")
    labels = " ".join(str(row.get(x_field) or "") for row in data if isinstance(row, dict))
    semantic_text = " ".join(
        [
            str(component.get("title") or props.get("title") or ""),
            str(component.get("subtitle") or props.get("subtitle") or ""),
            labels,
        ]
    )
    cn = bool(re.search(r"A\s*股|北交所|沪市|深市|创业板|創業板|科创板|科創板|\b\d{6}\.(?:SH|SZ|BJ)\b", semantic_text, re.I))
    hk = bool(re.search(r"港股|恒生指数|\b\d{4,5}\.HK\b|Hong\s*Kong", semantic_text, re.I))
    us = bool(re.search(r"美股|US\s*stocks?|U\.S\.\s*stocks?|NASDAQ|NYSE|S&P\s*500", semantic_text, re.I))
    detected = [market for market, matched in (("CN", cn), ("HK", hk), ("US", us)) if matched]
    if len(detected) == 1:
        return detected[0]
    if re.search(r"涨跌幅|漲跌幅|个股|個股|stock.{0,20}(?:return|change|distribution)", semantic_text, re.I):
        raise ValueError("Financial direction chart requires explicit financialMarket (CN/HK/US) from the question or data source; do not infer it from language or bin signs")
    return ""


def extract_component(payload: dict[str, Any], component_type: str) -> dict[str, Any]:
    chart_payload = payload.get("chartPayload")
    if isinstance(chart_payload, dict):
        return chart_payload
    if payload.get("type") == component_type:
        return payload
    root = payload.get("root")
    if isinstance(root, dict) and root.get("type") == "component" and isinstance(root.get("component"), dict):
        return root["component"]
    component = payload.get("component")
    if isinstance(component, dict):
        return component
    return payload


def load_payload(path: str | None, data_json: str | None, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if path:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    elif data_json:
        payload = json.loads(data_json)
    else:
        if default is None:
            raise ValueError("bar data must be provided via --payload or --data-json")
        payload = default
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def write_outputs(html_text: str, normalized: dict[str, Any], output: str, payload_output: str | None = None) -> None:
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    if payload_output:
        payload_path = Path(payload_output).expanduser().resolve()
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output_path)}, ensure_ascii=False))


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _visual_style(component: dict[str, Any], props: dict[str, Any], style_json: str | None) -> dict[str, Any]:
    style: dict[str, Any] = {}
    for candidate in (props.get("visualStyle"), component.get("visualStyle")):
        if isinstance(candidate, dict):
            style.update(candidate)
    if style_json:
        try:
            parsed = json.loads(style_json)
            if isinstance(parsed, dict):
                style.update(parsed)
        except json.JSONDecodeError:
            pass
    return style


def _matches_color_condition(value: float, condition: Any) -> bool:
    match = re.fullmatch(r"\s*(<=|>=|==|=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*", str(condition or ""))
    if not match:
        return False
    operator, raw_threshold = match.groups()
    threshold = float(raw_threshold)
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
        "=": value == threshold,
        "==": value == threshold,
    }[operator]


def _apply_color_rules(data: list[Any], series: list[dict[str, Any]], style: dict[str, Any]) -> None:
    rules = style.get("colorRules")
    if not isinstance(rules, list):
        return
    for row in data:
        if not isinstance(row, dict):
            continue
        for item in series:
            field = str(item.get("field") or "")
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rule_field = str(rule.get("field") or "").strip()
                color = str(rule.get("color") or "").strip()
                if color and (not rule_field or rule_field == field) and _matches_color_condition(value, rule.get("condition")):
                    row.setdefault("__markColors", {})[field] = color
                    break


def _distribution_bin_sign(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return 1 if value > 0 else -1 if value < 0 else 0
    text = str(value or "").strip().lower().translate(str.maketrans({"−": "-", "–": "-", "—": "-", "＋": "+"}))
    if not text:
        return None
    if any(term in text for term in ("持平", "平盘", "平盤", "零", "neutral", "flat")):
        return 0
    if text.startswith(("跌", "降", "亏", "虧")) or any(term in text for term in ("下跌", "负收益", "負收益", "negative", "loss")):
        return -1
    if text.startswith(("涨", "漲", "升", "盈")) or any(term in text for term in ("上涨", "上漲", "正收益", "positive", "gain")):
        return 1
    comparator = re.match(r"^\s*(<=|>=|<|>|≤|≥)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if comparator:
        operator, raw_value = comparator.groups()
        threshold = float(raw_value)
        if operator in {"<", "<=", "≤"} and threshold <= 0:
            return -1
        if operator in {">", ">=", "≥"} and threshold >= 0:
            return 1
        return None
    numbers = [float(item) for item in re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return 1 if numbers[0] > 0 else -1 if numbers[0] < 0 else 0
    low, high = min(numbers), max(numbers)
    return -1 if high <= 0 and low < 0 else 1 if low >= 0 and high > 0 else 0


def _apply_distribution_colors(
    data: list[Any], series: list[dict[str, Any]], x_field: str, style: dict[str, Any]
) -> None:
    config = style.get("distributionColor")
    if not isinstance(config, dict):
        return
    preserve_series_colors = bool(config.get("preserveSeriesColors")) or (
        len(series) > 1 and bool(config.get("autoDetected"))
    )
    colors = {
        -1: str(config.get("negative") or "var(--sv-price-down)"),
        0: str(config.get("neutral") or "#94a3b8"),
        1: str(config.get("positive") or "var(--sv-price-up)"),
    }
    for row in data:
        if not isinstance(row, dict):
            continue
        sign = _distribution_bin_sign(row.get(x_field))
        if sign is None:
            continue
        row["__distributionSign"] = sign
        if preserve_series_colors:
            continue
        mark_colors = row.setdefault("__markColors", {})
        for item in series:
            field = str(item.get("field") or "")
            if field:
                mark_colors.setdefault(field, colors[sign])


def _ensure_distribution_style(
    component: dict[str, Any], props: dict[str, Any], data: list[Any], x_field: str,
    series: list[dict[str, Any]], style: dict[str, Any]
) -> None:
    if isinstance(style.get("distributionColor"), dict) or style.get("colorRules"):
        return
    labels = [str(row.get(x_field) or "") for row in data if isinstance(row, dict)]
    signs = [_distribution_bin_sign(label) for label in labels]
    if -1 not in signs or 1 not in signs:
        return
    semantic_text = " ".join(
        [str(component.get("title") or props.get("title") or ""), str(x_field), *labels]
    ).lower()
    has_distribution_semantics = any(
        term in semantic_text
        for term in (
            "分布", "频次", "頻次", "频率", "頻率", "直方图", "直方圖", "区间", "區間",
            "distribution", "histogram", "frequency", "bucket", "bin",
        )
    )
    has_explicit_direction_labels = any(
        label.strip().startswith(("跌", "降", "亏", "虧")) for label in labels
    ) and any(label.strip().startswith(("涨", "漲", "升", "盈")) for label in labels)
    if not has_distribution_semantics and not has_explicit_direction_labels:
        return
    style.setdefault("markStrategy", "distribution-polarity")
    style["distributionColor"] = {
        "source": "x",
        "negative": "var(--sv-price-down)",
        "positive": "var(--sv-price-up)",
        "neutral": "#94a3b8",
        "zero": 0,
        "autoDetected": True,
        "preserveSeriesColors": len(series) > 1,
    }


def _ensure_signed_direction_style(
    component: dict[str, Any],
    props: dict[str, Any],
    data: list[Any],
    series: list[dict[str, Any]],
    style: dict[str, Any],
) -> None:
    """Compile obvious signed measures into executable per-value color rules."""
    if len(series) > 1:
        return
    if isinstance(style.get("distributionColor"), dict) or style.get("colorRules"):
        return
    if style.get("markStrategy") not in {None, "", "no-mark", "signed-direction"}:
        return
    raw_series = props.get("series") or component.get("series")
    if isinstance(raw_series, list) and any(
        isinstance(item, dict) and str(item.get("color") or "").strip() for item in raw_series
    ):
        return
    axis = next(
        (
            candidate
            for candidate in (
                props.get("axis"), component.get("axis"), component.get("rightAxis"), component.get("yAxis")
            )
            if isinstance(candidate, dict)
        ),
        {},
    )
    semantic_text = " ".join(
        [
            str(component.get("title") or props.get("title") or ""),
            str(component.get("subtitle") or props.get("subtitle") or ""),
            str(axis.get("label") or axis.get("title") or ""),
            *[
                " ".join(
                    str(item.get(key) or "") for key in ("field", "label", "suffix", "unit")
                )
                for item in series
            ],
        ]
    ).lower()
    signed_terms = (
        "涨跌", "漲跌", "涨幅", "漲幅", "跌幅", "收益率", "回报率", "回報率",
        "增速", "增长率", "增長率", "变化", "變化", "变动", "變動", "盈亏", "盈虧",
        "return", "change", "growth", "delta", "p&l", "profit/loss", "gain", "loss",
    )
    if not any(term in semantic_text for term in signed_terms):
        return
    has_numeric_value = any(
        isinstance(row, dict)
        and any(isinstance(row.get(str(item.get("field") or "")), (int, float)) for item in series)
        for row in data
    )
    if not has_numeric_value:
        return
    style["markStrategy"] = "signed-direction"
    style["autoDetected"] = True
    style["colorRules"] = [
        {"condition": ">0", "color": "var(--sv-price-up)", "semantic": "positive"},
        {"condition": "<0", "color": "var(--sv-price-down)", "semantic": "negative"},
        {"condition": "=0", "color": "#94a3b8", "semantic": "neutral"},
    ]


def normalize_xy_series(component: dict[str, Any], component_type: str, default_title: str, default_series_type: str, style_json: str | None = None) -> dict[str, Any]:
    props = component.get("props") if isinstance(component.get("props"), dict) else {}
    data = component.get("data") or props.get("data") or []
    if not isinstance(data, list) or not data:
        raise ValueError(f"{component_type} data must be a non-empty array")
    x_field = str(props.get("xField") or component.get("xField") or "period")
    raw_series = props.get("series") or component.get("series")
    if isinstance(raw_series, list) and raw_series:
        series = raw_series
    else:
        first = next((row for row in data if isinstance(row, dict)), {})
        field = str(component.get("yField") or props.get("yField") or "")
        if not field:
            field = next((key for key, value in first.items() if key != x_field and isinstance(value, (int, float))), "value")
        label = component.get("yLabel") or props.get("yLabel") or component.get("measureLabel") or props.get("measureLabel")
        if not label and str(field).lower() not in {"value", "val", "amount"}:
            label = str(field).replace("_", " ").title()
        series = [
            {
                "field": field,
                "label": str(label or ""),
                "color": PALETTE[0],
                "type": default_series_type,
                "inferred": True,
            }
        ]
    normalized_series = []
    for index, item in enumerate(series):
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or item.get("key") or "")
        if not field:
            continue
        label = str(item.get("label") or item.get("name") or field)
        if field.lower() in {"value", "val", "amount"} and label.strip().lower() in {"value", "val", "amount"}:
            label = ""
        normalized_series.append(
            {
                "field": field,
                "label": label,
                "color": str(item.get("color") or PALETTE[index % len(PALETTE)]),
                "type": default_series_type,
                "prefix": str(item.get("prefix") or ""),
                "suffix": str(item.get("suffix") or item.get("unit") or ""),
                "unit": str(item.get("unit") or item.get("suffix") or ""),
                "digits": item.get("digits"),
                "inferred": bool(item.get("inferred")),
            }
        )
    if not normalized_series:
        raise ValueError(f"{component_type} series must contain at least one field")
    visual_style = _visual_style(component, props, style_json)
    _ensure_distribution_style(component, props, data, x_field, normalized_series, visual_style)
    _ensure_signed_direction_style(component, props, data, normalized_series, visual_style)
    _apply_distribution_colors(data, normalized_series, x_field, visual_style)
    _apply_color_rules(data, normalized_series, visual_style)
    legend = dict(
        props.get("legend")
        if isinstance(props.get("legend"), dict)
        else component.get("legend")
        if isinstance(component.get("legend"), dict)
        else {}
    )
    legend.setdefault("visible", len(normalized_series) > 1)
    return {
        "type": component_type,
        "financialMarket": _financial_market(component, props, data, x_field),
        "themeMode": str(
            props.get("themeMode") or props.get("theme") or component.get("themeMode") or component.get("theme") or "light"
        ).lower(),
        "title": str(component.get("title") or props.get("title") or default_title),
        "xField": x_field,
        "height": int(props.get("height") or component.get("height") or 360),
        "gridCount": int(props.get("gridCount") or 5),
        "axis": (
            props.get("axis")
            if isinstance(props.get("axis"), dict)
            else component.get("axis")
            if isinstance(component.get("axis"), dict)
            else component.get("rightAxis")
            if isinstance(component.get("rightAxis"), dict)
            else component.get("yAxis")
            if isinstance(component.get("yAxis"), dict)
            else {"digits": 2, "suffix": "", "position": "right"}
        ),
        "legend": legend,
        "series": normalized_series,
        "data": data,
        "visualStyle": visual_style,
    }


def render_svg_chart(config: dict[str, Any], chart_kind: str) -> str:
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(config["title"])
    theme_mode = "dark" if config.get("themeMode") == "dark" else "light"
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="{theme_mode}"{f' data-financial-market="{html.escape(str(config.get("financialMarket") or ""))}"' if config.get("financialMarket") else ''}>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script>(() => {{ const theme = new URLSearchParams(location.search).get('theme'); if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme; }})();</script>
<style>
*{{box-sizing:border-box}}
:root{{--chart-text-primary:#171b22;--chart-text-secondary:#5f6876;--chart-text-muted:#8b94a2;--chart-border-subtle:#edf0f4;--chart-border-default:#a3a8b0;--chart-point-fill:#fff;--chart-highlight:#8a8a8a;--chart-tooltip-bg:rgba(59,59,59,.96);--sv-gain:#08745f;--sv-loss:#c43244;--sv-price-up:var(--sv-gain);--sv-price-down:var(--sv-loss)}}
:root[data-theme="dark"]{{color-scheme:dark;--chart-text-primary:#f1f5f9;--chart-text-secondary:#c1cad7;--chart-text-muted:#93a0b3;--chart-border-subtle:#2b3544;--chart-border-default:#334052;--chart-point-fill:#181e28;--chart-highlight:#c1cad7;--chart-tooltip-bg:#202733;--sv-gain:#3ddc97;--sv-loss:#ff6b6b}}
:root[data-financial-market="CN"],:root[data-financial-market="HK"]{{--sv-price-up:var(--sv-loss);--sv-price-down:var(--sv-gain)}}
:root[data-financial-market="US"]{{--sv-price-up:var(--sv-gain);--sv-price-down:var(--sv-loss)}}
html,body{{width:100%;height:100%;margin:0;background:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;background:transparent;color:var(--chart-text-primary)}}
.chart-component{{position:relative;width:100%;container-type:inline-size;height:clamp(320px,calc(100cqw * .42),{config["height"]}px);padding:0;background:transparent;overflow:visible}}
.chart-title{{min-height:22px;max-height:42px;margin:0;font-size:16px;font-weight:800;line-height:1.25;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
.chart-stage{{width:100%;height:calc(100% - 50px);margin-top:8px;overflow:visible}}
svg{{display:block;width:100%;height:100%;overflow:visible}}
.grid-line{{stroke:var(--chart-border-subtle);stroke-width:1}}
.axis-line{{stroke:var(--chart-border-default);stroke-width:1}}
.axis-label{{fill:var(--chart-text-secondary);font-size:10px;font-weight:400}}
.x-label{{fill:var(--chart-text-secondary);font-size:10px;font-weight:400;text-anchor:middle}}
.bar{{rx:0;cursor:crosshair}}
.line-path{{fill:none;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}}
.point{{fill:var(--chart-point-fill);stroke-width:2;cursor:crosshair}}
.hover-zone{{fill:transparent;cursor:crosshair}}
.highlight{{fill:var(--chart-highlight);pointer-events:none}}
.chart-legend{{position:absolute;left:8px;right:8px;bottom:4px;display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:10px 18px;color:var(--chart-text-secondary);font-size:10px;line-height:1.2;text-align:center;pointer-events:none}}
.legend-item{{display:flex;align-items:center;gap:7px;white-space:nowrap}}
.legend-dot{{width:8px;height:8px;border-radius:50%;flex:none}}
.chart-tooltip{{position:fixed;z-index:2147483647;display:inline-grid;min-width:180px;width:max-content;max-width:min(220px,calc(100vw - 24px));padding:8px 10px;background:var(--chart-tooltip-bg);color:#fff;border-radius:6px;font-size:10px;line-height:1.35;pointer-events:none;opacity:0;visibility:hidden;transition:opacity .08s ease;box-shadow:none;filter:none;white-space:normal}}
.chart-tooltip::after{{content:"";position:absolute;left:var(--arrow-left,50%);bottom:-5px;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid var(--chart-tooltip-bg)}}
.chart-tooltip.active{{opacity:1;visibility:visible}}
.tooltip-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;min-height:17px;white-space:normal}}
.tooltip-row b{{white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}}
.tooltip-label{{display:grid;grid-template-columns:7px minmax(0,1fr);align-items:start;gap:5px;color:#f5f5f5;min-width:0;overflow-wrap:anywhere}}
.tooltip-dot{{width:7px;height:7px;margin-top:.325em;border-radius:50%;flex:none}}
@media(max-width:680px){{.chart-component{{height:clamp(248px,calc(100cqw * .72),320px);padding:0}}.chart-title{{min-height:18px;max-height:38px;font-size:14px;line-height:1.28;padding:0}}.chart-stage{{height:calc(100% - 50px);margin-top:6px}}.axis-label,.x-label{{font-size:10px}}.chart-legend{{left:0;right:0;bottom:0;gap:8px 12px;min-height:30px;font-size:10px;align-content:center}}.legend-item{{gap:5px;max-width:42%;overflow:hidden;text-overflow:ellipsis}}.legend-dot{{width:8px;height:8px}}.chart-tooltip{{min-width:0;max-width:220px;font-size:10px;padding:6px 8px;white-space:normal}}}}
</style>
</head>
<body>
<section class="chart-component">
  <h2 class="chart-title">{title}</h2>
  <div class="chart-stage"><svg role="img" aria-label="{title}"></svg></div>
  <div class="chart-legend"></div>
  <div class="chart-tooltip"></div>
</section>
<script>
const config = {config_json};
const chartKind = {json.dumps(chart_kind)};
const root = document.querySelector('.chart-component');
const svg = root.querySelector('svg');
const legend = root.querySelector('.chart-legend');
const tooltip = root.querySelector('.chart-tooltip');
const NS = 'http://www.w3.org/2000/svg';
const GENERIC_SERIES_LABELS = new Set(['', 'value', 'val', 'amount']);
const DARK_COLOR_ALIASES = {{'#4387f5':'#8294ff','#4bc3d5':'#34d3ad','#f9730c':'#f6ad55','#8b5cf6':'#d19dff','#10b981':'#34d3ad','#ef4444':'#ff7188','#00b899':'#34d3ad','#ff2f57':'#ff7188','#94a3b8':'#93a0b3'}};
const chartColorCache = new Map();
const chartColor = color => {{
  const raw = String(color || '');
  const themed = document.documentElement.dataset.theme === 'dark' ? (DARK_COLOR_ALIASES[raw.toLowerCase()] || raw) : raw;
  const cacheKey = `${{document.documentElement.dataset.theme || 'light'}}:${{config.financialMarket || ''}}:${{themed}}`;
  if (chartColorCache.has(cacheKey)) return chartColorCache.get(cacheKey);
  if (!themed.includes('var(')) {{ chartColorCache.set(cacheKey, themed); return themed; }}
  const probe = document.createElement('span');
  probe.style.color = themed;
  probe.style.display = 'none';
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color || themed;
  probe.remove();
  chartColorCache.set(cacheKey, resolved);
  return resolved;
}};
let tooltipPortalAckUntil = 0;
const node = (name, attrs = {{}}, text = '') => {{
  const el = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value));
  if (text !== '') el.textContent = text;
  return el;
}};
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
function hasExplicitDigits(value) {{
  return value !== undefined && value !== null && value !== '' && Number.isFinite(Number(value));
}}
function normalizeDigits(value, fallback = 2) {{
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(0, Math.min(6, Math.round(numeric)));
}}
function compactNumber(value, digits = 2) {{
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '';
  const localeText = [
    config.locale,
    config.language,
    config.title,
    config.subtitle,
    config.yLabel,
    config.measureLabel,
    ...(config.series || []).map(item => item.label || item.name || item.field || '')
  ].filter(Boolean).join(' ');
  const locale = /[\u4e00-\u9fff]/.test(localeText) ? 'zh-CN'
    : /[\u3040-\u30ff]/.test(localeText) ? 'ja-JP'
    : /[\uac00-\ud7af]/.test(localeText) ? 'ko-KR'
    : 'en-US';
  const cjkUnits = locale === 'ja-JP'
    ? [['兆', 1e12], ['億', 1e8], ['万', 1e4]]
    : locale === 'ko-KR'
      ? [['조', 1e12], ['억', 1e8], ['만', 1e4]]
      : locale === 'zh-CN'
        ? [['万亿', 1e12], ['亿', 1e8], ['万', 1e4]]
        : null;
  const abs = Math.abs(numeric);
  let scaled = numeric;
  let unit = '';
  if (cjkUnits) {{
    const matched = cjkUnits.find(([, threshold]) => abs >= threshold);
    if (matched) {{ unit = matched[0]; scaled = numeric / matched[1]; }}
  }} else if (abs >= 1e4) {{
    if (abs >= 1e12) {{ scaled = numeric / 1e12; unit = 'T'; }}
    else if (abs >= 1e9) {{ scaled = numeric / 1e9; unit = 'B'; }}
    else if (abs >= 1e6) {{ scaled = numeric / 1e6; unit = 'M'; }}
    else {{ scaled = numeric / 1e3; unit = 'K'; }}
  }}
  return scaled.toLocaleString(locale, {{ minimumFractionDigits: digits, maximumFractionDigits: digits }}) + unit;
}}
function formatAxisValue(value) {{
  const digits = Math.max(2, normalizeDigits(config.axis?.digits, 2));
  return compactNumber(value, digits);
}}
const seriesLabel = series => String(series.label || '').trim();
function inferMeasureLabel() {{
  const explicit = config.legend?.label || config.yLabel || config.measureLabel || config.axis?.label || config.axis?.name;
  if (explicit) return String(explicit).trim();
  const title = String(config.title || '').trim();
  const titleHints = ['员工人数', '雇员人数', '员工数', '雇员数', '人数', '营收', '收入', '利润', '净利润', '销量', '成交量', '市值', '股价', '价格', '收益率', '占比', '比例'];
  const matched = titleHints.find(item => title.includes(item));
  if (matched) return matched;
  return /[\\u3400-\\u9fff]/.test(title) ? '数值' : 'Value';
}}
function inferValueUnit(series = {{}}) {{
  const explicit = series.suffix || series.unit || config.axis?.suffix || config.axis?.unit || config.unit || config.valueUnit;
  if (explicit) return String(explicit);
  const label = `${{displaySeriesLabel(series)}} ${{config.title || ''}}`;
  const unitHints = [
    [/(员工人数|雇员人数|员工数|雇员数|人数|employees?|headcount)/i, '人'],
    [/(营收|收入|revenue|sales)/i, ''],
    [/(利润|净利润|profit|income)/i, ''],
    [/(市值|market\\s*cap)/i, ''],
    [/(股价|价格|price)/i, ''],
    [/(收益率|占比|比例|rate|ratio|percent|percentage)/i, '%'],
    [/(成交量|销量|volume|sales\\s*volume)/i, ''],
  ];
  const matched = unitHints.find(([pattern]) => pattern.test(label));
  return matched ? matched[1] : '';
}}
function formatTooltipValue(value, series = {{}}) {{
  const digits = hasExplicitDigits(series.digits) ? normalizeDigits(series.digits, 2) : 2;
  return compactNumber(value, digits);
}}
function axisLegendText(axis = {{}}) {{
  return String(axis.description || axis.label || axis.title || axis.name || axis.axisLabel || '').trim();
}}
const displaySeriesLabel = series => {{
  const label = seriesLabel(series);
  if (label) return label;
  if (GENERIC_SERIES_LABELS.has(String(series.field || '').trim().toLowerCase())) return inferMeasureLabel();
  return String(series.field || '').replace(/_/g, ' ').replace(/\\b\\w/g, char => char.toUpperCase());
}};
const shouldShowLegend = () => {{
  if (config.legend?.visible === true) return true;
  if (config.legend?.visible === false) return false;
  return config.series.length > 1;
}};
const niceStep = (range, count = 4) => {{
  const rough = Math.max(range / count, 0.0001);
  const power = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / power;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * power;
}};
function range(values, gridCount) {{
  let min = Math.min(0, ...values);
  let max = Math.max(0, ...values);
  if (min === max) {{ min -= 1; max += 1; }}
  const step = niceStep(max - min, Math.max(1, gridCount - 1));
  min = Math.floor(min / step) * step;
  max = Math.ceil(max / step) * step;
  const ticks = [];
  for (let value = max; value >= min - step / 2; value -= step) {{
    ticks.push(Number(value.toFixed(10)));
  }}
  return {{min, max, step, ticks}};
}}
function tooltipHtml(rows, xLabel) {{
  return `<strong>${{xLabel}}</strong>` + rows.map(row => {{
    const label = String(row.label || '').trim();
    const labelHtml = `<span class="tooltip-label"><i class="tooltip-dot" style="background:${{row.color}}"></i>${{label}}</span>`;
    return `<div class="tooltip-row">${{labelHtml}}<b>${{formatTooltipValue(row.value, row.series)}}</b></div>`;
  }}).join('');
}}
function tooltipBounds(anchorX, tooltipWidth, viewportLeft = 0, viewportRight = window.innerWidth, safeDistance = 0) {{
  const minLeft = viewportLeft + safeDistance;
  const maxLeft = viewportRight - tooltipWidth - safeDistance;
  const left = maxLeft >= minLeft ? Math.min(maxLeft, Math.max(minLeft, anchorX - tooltipWidth / 2)) : minLeft;
  const arrowLeft = Math.min(tooltipWidth - 14, Math.max(14, anchorX - left));
  return {{left, arrowLeft}};
}}
function titleRectInContext(ctx) {{
  const title = root.querySelector('.chart-title');
  if (!title) return null;
  const range = document.createRange();
  range.selectNodeContents(title);
  const rect = range.getBoundingClientRect();
  return {{ left: ctx.offsetLeft + rect.left, right: ctx.offsetLeft + rect.right, top: ctx.offsetTop + rect.top, bottom: ctx.offsetTop + rect.bottom }};
}}
function avoidTitleOverlap(bounds, tooltipWidth, tooltipHeight, top, titleRect, anchorX, viewportLeft, viewportRight, safeDistance = 0) {{
  if (!titleRect) return bounds;
  const tooltipRect = {{ left: bounds.left, right: bounds.left + tooltipWidth, top, bottom: top + tooltipHeight }};
  const overlaps = tooltipRect.left < titleRect.right && tooltipRect.right > titleRect.left && tooltipRect.top < titleRect.bottom && tooltipRect.bottom > titleRect.top;
  if (!overlaps) return bounds;
  const aboveTitleTop = titleRect.top - tooltipHeight - safeDistance;
  if (aboveTitleTop >= safeDistance) {{
    return {{...bounds, top: aboveTitleTop, arrowLeft: Math.min(tooltipWidth - 14, Math.max(14, anchorX - bounds.left))}};
  }}
  const minLeft = viewportLeft + safeDistance;
  const maxLeft = viewportRight - tooltipWidth - safeDistance;
  const candidates = [titleRect.right + safeDistance, titleRect.left - tooltipWidth - safeDistance].filter(value => (
    value >= minLeft &&
    value <= maxLeft &&
    anchorX >= value + 14 &&
    anchorX <= value + tooltipWidth - 14
  ));
  if (!candidates.length) return bounds;
  const left = candidates.reduce((best, value) => Math.abs(value - bounds.left) < Math.abs(best - bounds.left) ? value : best, candidates[0]);
  return {{...bounds, left, arrowLeft: Math.min(tooltipWidth - 14, Math.max(14, anchorX - left))}};
}}
function parentTooltipContext() {{
  try {{
    if (!window.frameElement || !window.parent?.document) {{
      return {{doc: document, win: window, offsetLeft: 0, offsetTop: 0, frameRect: {{left: 0, top: 0}}}};
    }}
    let currentWindow = window;
    let targetWindow = window.parent;
    let offsetLeft = 0;
    let offsetTop = 0;
    let depth = 0;
    while (currentWindow.frameElement && targetWindow?.document && depth < 8) {{
      const frameRect = currentWindow.frameElement.getBoundingClientRect();
      offsetLeft += frameRect.left;
      offsetTop += frameRect.top;
      currentWindow = targetWindow;
      if (!currentWindow.frameElement || !currentWindow.parent || currentWindow.parent === currentWindow) break;
      targetWindow = currentWindow.parent;
      depth += 1;
    }}
    return {{doc: currentWindow.document, win: currentWindow, offsetLeft, offsetTop, frameRect: {{left: offsetLeft, top: offsetTop}}}};
  }} catch (error) {{
    return null;
  }}
}}
function chartEmbedKey() {{
  try {{
    const frame = window.frameElement;
    if (!frame) {{
      if (!root.dataset.chartEmbed) root.dataset.chartEmbed = `chart-${{Math.random().toString(36).slice(2, 10)}}`;
      return root.dataset.chartEmbed;
    }}
    if (!frame.dataset.chartEmbed) frame.dataset.chartEmbed = `chart-${{Math.random().toString(36).slice(2, 10)}}`;
    return frame.dataset.chartEmbed;
  }} catch (error) {{
    return 'active';
  }}
}}
function ensureParentTooltipStyle(doc) {{
  if (doc.getElementById('bar-chart-tooltip-portal-style')) return;
  const style = doc.createElement('style');
  style.id = 'bar-chart-tooltip-portal-style';
  style.textContent = `
    .bar-chart-tooltip-portal{{position:fixed;z-index:2147483647;display:inline-grid;min-width:180px;width:max-content;max-width:min(220px,calc(100vw - 24px));padding:8px 10px;background:rgba(59,59,59,.96);color:#fff;border-radius:6px;font:10px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;pointer-events:none;opacity:0;visibility:hidden;box-shadow:none;filter:none;white-space:normal;transition:opacity .08s ease}}
    .bar-chart-tooltip-portal.active{{opacity:1;visibility:visible}}
    .bar-chart-tooltip-portal .tooltip-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;min-height:17px;white-space:normal}}
    .bar-chart-tooltip-portal .tooltip-row b{{white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}}
    .bar-chart-tooltip-portal .tooltip-label{{display:grid;grid-template-columns:7px minmax(0,1fr);align-items:start;gap:5px;color:#f5f5f5;min-width:0;overflow-wrap:anywhere}}
    .bar-chart-tooltip-portal .tooltip-dot{{width:7px;height:7px;margin-top:.325em;border-radius:50%;flex:none}}
    .bar-chart-tooltip-portal::after{{content:"";position:absolute;left:var(--arrow-left,50%);bottom:-5px;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid rgba(59,59,59,.96)}}
  `;
  doc.head.appendChild(style);
}}
function parentTooltipElement(ctx) {{
  ensureParentTooltipStyle(ctx.doc);
  const id = 'bar-chart-tooltip-portal-' + chartEmbedKey();
  let element = ctx.doc.getElementById(id);
  if (!element) {{
    element = ctx.doc.createElement('div');
    element.id = id;
    element.className = 'bar-chart-tooltip-portal';
    ctx.doc.body.appendChild(element);
  }}
  return element;
}}
function postTooltipPortal(action, payload = {{}}) {{
  try {{
    if (!window.parent || window.parent === window) return false;
    window.parent.postMessage({{
      type: 'bar-chart-tooltip-portal',
      action,
      chartEmbed: chartEmbedKey(),
      ...payload
    }}, '*');
    return true;
  }} catch (error) {{
    return false;
  }}
}}
window.addEventListener('message', event => {{
  if (event.data?.type !== 'bar-chart-tooltip-portal-ack') return;
  tooltipPortalAckUntil = Date.now() + 250;
  if (event.data.action === 'show') tooltip.classList.remove('active');
}});
function showTooltip(anchorX, rows, xLabel, gridTop) {{
  const html = tooltipHtml(rows, xLabel);
  const stage = root.querySelector('.chart-stage');
  const stageRect = stage.getBoundingClientRect();
  const rootRect = root.getBoundingClientRect();
  const tooltipGap = 10;
  const ctx = parentTooltipContext();
  if (ctx) {{
    const portal = parentTooltipElement(ctx);
    portal.innerHTML = html;
    portal.classList.add('active');
    const absoluteAnchorX = ctx.offsetLeft + stageRect.left + anchorX;
    const top = ctx.offsetTop + stageRect.top + gridTop - portal.offsetHeight - tooltipGap;
    let bounds = tooltipBounds(absoluteAnchorX, portal.offsetWidth, ctx.offsetLeft + rootRect.left, ctx.offsetLeft + rootRect.right, 0);
    portal.style.left = `${{bounds.left}}px`;
    portal.style.top = `${{bounds.top ?? top}}px`;
    portal.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
    tooltip.classList.remove('active');
    return;
  }}
  if (window.parent && window.parent !== window) {{
    tooltip.classList.remove('active');
    postTooltipPortal('show', {{
      html,
      anchorX,
      stageLeft: stageRect.left,
      stageTop: stageRect.top,
      rootLeft: rootRect.left,
      rootRight: rootRect.right,
      gridTop,
      gap: tooltipGap,
      offsetY: 0,
      maxWidth: 220,
      background: 'rgba(59,59,59,.96)',
      color: '#fff',
      borderRadius: 6,
      padding: '6px 8px',
      fontSize: 10,
    }});
    const fallbackTime = Date.now();
    setTimeout(() => {{
      if (tooltipPortalAckUntil >= fallbackTime) return;
      tooltip.innerHTML = html;
      tooltip.classList.add('active');
      const absoluteAnchorX = stageRect.left + anchorX;
      const bounds = tooltipBounds(absoluteAnchorX, tooltip.offsetWidth, rootRect.left, rootRect.right, 0);
      tooltip.style.left = `${{bounds.left}}px`;
      tooltip.style.top = `${{stageRect.top + gridTop - tooltip.offsetHeight - tooltipGap}}px`;
      tooltip.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
    }}, 60);
    return;
  }}
  tooltip.innerHTML = html;
  tooltip.classList.add('active');
  const absoluteAnchorX = stageRect.left + anchorX;
  const bounds = tooltipBounds(absoluteAnchorX, tooltip.offsetWidth, rootRect.left, rootRect.right, 0);
  tooltip.style.left = `${{bounds.left}}px`;
  tooltip.style.top = `${{stageRect.top + gridTop - tooltip.offsetHeight - tooltipGap}}px`;
  tooltip.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
}}
function hideTooltip() {{
  tooltip.classList.remove('active');
  const ctx = parentTooltipContext();
  if (ctx) parentTooltipElement(ctx).classList.remove('active');
  postTooltipPortal('hide');
}}
function postChartHeight() {{
  const rect = root.getBoundingClientRect();
  const height = Math.ceil(Math.max(180, rect.height || 0));
  try {{ parent.postMessage({{type:'analysis-planner-report-height', height}}, '*'); }} catch (e) {{}}
}}
function setHighlight(index) {{
  svg.querySelectorAll('[data-highlight-index]').forEach(item => item.setAttribute('opacity', Number(item.dataset.highlightIndex) === index ? '.08' : '0'));
}}
function clearHighlight() {{
  svg.querySelectorAll('[data-highlight-index]').forEach(item => item.setAttribute('opacity', '0'));
}}
function estimateAxisWidth(labels) {{
  const widthFor = label => Array.from(String(label || '')).reduce((total, char) => {{
    if (/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(char)) return total + 11;
    if (/[A-Z]/.test(char)) return total + 7;
    if (/[-0-9.%,+]/.test(char)) return total + 6;
    return total + 6.5;
  }}, 4);
  return Math.max(28, Math.min(78, Math.ceil(Math.max(...labels.map(widthFor), 0)) + 1));
}}
function measureAxisWidth(labels, fontSize = 10, fontWeight = 400) {{
  try {{
    const canvas = measureAxisWidth.canvas || (measureAxisWidth.canvas = document.createElement('canvas'));
    const ctx = canvas.getContext('2d');
    ctx.font = `${{fontWeight || 400}} ${{fontSize || 10}}px -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif`;
    const widths = labels.map(label => ctx.measureText(String(label || '')).width);
    return Math.max(0, Math.ceil(Math.max(...widths, 0)));
  }} catch (error) {{
    return estimateAxisWidth(labels);
  }}
}}
function sampledXAxisIndexes(labels, slot, fontSize = 10, fontWeight = 400) {{
  const count = labels.length;
  if (count <= 0) return new Set();
  const gap = 8;
  const widths = labels.map(label => measureAxisWidth([label], fontSize, fontWeight) + gap);
  const centers = labels.map((_, index) => slot * index + slot / 2);
  const overlaps = (leftIndex, rightIndex) => (
    centers[rightIndex] - widths[rightIndex] / 2 < centers[leftIndex] + widths[leftIndex] / 2 + gap
  );
  let canShowAll = true;
  for (let index = 1; index < count; index += 1) {{
    if (overlaps(index - 1, index)) {{
      canShowAll = false;
      break;
    }}
  }}
  if (canShowAll) return new Set(Array.from({{length: count}}, (_, index) => index));
  const selected = [0];
  for (let index = 1; index < count - 1; index += 1) {{
    const previous = selected[selected.length - 1];
    if (!overlaps(previous, index)) selected.push(index);
  }}
  if (count > 1) {{
    const last = count - 1;
    while (selected.length > 1 && overlaps(selected[selected.length - 1], last)) selected.pop();
    if (!overlaps(selected[selected.length - 1], last)) selected.push(last);
  }}
  return new Set(selected);
}}
function render() {{
  svg.innerHTML = '';
  legend.innerHTML = '';
  const width = svg.clientWidth || 900;
  const height = svg.clientHeight || 270;
  const values = [];
  config.data.forEach(row => config.series.forEach(series => values.push(number(row[series.field]))));
  const gridCount = Math.max(2, config.gridCount || 5);
  const yRange = range(values, gridCount);
  const tickLabels = yRange.ticks.map(value => formatAxisValue(value));
  const axisLegend = axisLegendText(config.axis);
  const rightAxisGap = width >= 820 ? 10 : 8;
  const axisFontSize = 10;
  const rightTickWidth = measureAxisWidth(tickLabels, 10, 400);
  const margin = {{
    top: axisLegend ? 30 : 14,
    right: rightTickWidth + rightAxisGap,
    bottom: 38,
    left: 0
  }};
  const plotW = Math.max(120, width - margin.left - margin.right);
  const plotH = Math.max(100, height - margin.top - margin.bottom);
  const rightAxisX = margin.left + plotW + rightAxisGap + rightTickWidth;
  const y = value => margin.top + plotH - (number(value) - yRange.min) / (yRange.max - yRange.min) * plotH;
  yRange.ticks.forEach((value, index) => {{
    const gy = y(value);
    svg.appendChild(node('line', {{x1:margin.left,y1:gy,x2:margin.left+plotW,y2:gy,class:'grid-line'}}));
    svg.appendChild(node('text', {{x:rightAxisX,y:gy+4,class:'axis-label','text-anchor':'end'}}, tickLabels[index] ?? formatAxisValue(value)));
  }});
  svg.appendChild(node('line', {{x1:margin.left,y1:y(0),x2:margin.left+plotW,y2:y(0),class:'axis-line'}}));
  if (axisLegend) {{
    svg.appendChild(node('text', {{
      x: rightAxisX,
      y: margin.top - axisFontSize - 6,
      class: 'axis-label y-axis-legend',
      'text-anchor': 'end'
    }}, axisLegend));
  }}
  const rowCount = config.data.length;
  const slot = plotW / Math.max(rowCount, 1);
  const xCenter = index => margin.left + slot * index + slot / 2;
  const xLabels = config.data.map(row => row[config.xField]);
  const visibleXLabels = sampledXAxisIndexes(xLabels, slot, 10, 400);
  config.data.forEach((row, index) => {{
    if (visibleXLabels.has(index)) {{
      svg.appendChild(node('text', {{x:xCenter(index),y:margin.top+plotH+20,class:'x-label'}}, row[config.xField]));
    }}
  }});
  if (chartKind === 'line') {{
    config.series.forEach(series => {{
      const points = config.data.map((row, index) => [xCenter(index), y(row[series.field]), number(row[series.field])]);
      svg.appendChild(node('path', {{d:points.map((p,i)=>(i?'L':'M')+p[0]+' '+p[1]).join(' '),class:'line-path',stroke:chartColor(series.color)}}));
      points.forEach((p, index) => {{
        const point = node('circle', {{cx:p[0],cy:p[1],r:3.5,class:'point',stroke:chartColor(series.color)}});
        point.addEventListener('mouseenter', () => showTooltip(p[0], [{{label:series.label,color:chartColor(series.color),value:p[2]}}], config.data[index][config.xField], margin.top));
        point.addEventListener('mousemove', () => showTooltip(p[0], [{{label:series.label,color:chartColor(series.color),value:p[2]}}], config.data[index][config.xField], margin.top));
        point.addEventListener('mouseleave', hideTooltip);
        svg.appendChild(point);
      }});
    }});
  }} else {{
    const groupW = Math.min(Number(config.barMaxWidth || config.maxBarWidth || 72), slot * .72);
    const barGap = chartKind === 'grouped-bar' ? 4 : 0;
    const barW = Math.max(4, (groupW - barGap * (config.series.length - 1)) / config.series.length);
    config.data.forEach((row, rowIndex) => {{
      const groupX = xCenter(rowIndex) - groupW / 2;
      const tooltipRows = config.series.map(series => ({{label:displaySeriesLabel(series),color:chartColor(row.__markColors?.[series.field] || series.color),value:number(row[series.field]),series}}));
      const highlight = node('rect', {{
        x:margin.left + slot * rowIndex,
        y:margin.top,
        width:slot,
        height:plotH,
        class:'highlight',
        opacity:0,
        'data-highlight-index':rowIndex
      }});
      highlight.style.pointerEvents = 'none';
      svg.insertBefore(highlight, svg.firstChild);
      config.series.forEach((series, seriesIndex) => {{
        const value = number(row[series.field]);
        const y0 = y(0);
        const y1 = y(value);
        const rect = node('rect', {{x:groupX + seriesIndex * (barW + barGap),y:Math.min(y0,y1),width:barW,height:Math.max(1,Math.abs(y0-y1)),fill:chartColor(row.__markColors?.[series.field] || series.color),class:'bar'}});
        svg.appendChild(rect);
      }});
      const hit = node('rect', {{
        x:margin.left + slot * rowIndex,
        y:margin.top,
        width:slot,
        height:plotH,
        class:'hover-zone',
        'data-hover-index':rowIndex
      }});
      hit.addEventListener('mouseenter', () => {{ setHighlight(rowIndex); showTooltip(xCenter(rowIndex), tooltipRows, row[config.xField], margin.top); }});
      hit.addEventListener('mousemove', () => {{ setHighlight(rowIndex); showTooltip(xCenter(rowIndex), tooltipRows, row[config.xField], margin.top); }});
      hit.addEventListener('mouseleave', () => {{ clearHighlight(); hideTooltip(); }});
      svg.appendChild(hit);
    }});
  }}
  if (!shouldShowLegend()) {{
    legend.style.display = 'none';
    return;
  }}
  legend.style.display = '';
  config.series.forEach(series => {{
    const label = displaySeriesLabel(series);
    if (!label) return;
    const item = document.createElement('span');
    item.className = 'legend-item';
    item.innerHTML = `<i class="legend-dot" style="background:${{chartColor(series.color)}}"></i>${{label}}`;
    legend.appendChild(item);
  }});
}}
new ResizeObserver(() => {{ render(); postChartHeight(); }}).observe(svg);
render();
postChartHeight();
setTimeout(postChartHeight, 80);
setTimeout(postChartHeight, 300);
</script>
{(Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8")}
</body>
</html>"""



COMPONENT_TYPE = "bar"


def component_schema() -> dict:
    return {
        "type": COMPONENT_TYPE,
        "name": "柱状图",
        "visualChannelMappings": [
            {"semantic": "横轴维度", "field": "xField", "visualChannel": "xAxis.category", "required": True},
            {"semantic": "柱系列", "field": "series[].field", "visualChannel": "bar.height", "required": True},
        ],
        "dataContract": [
            {"field": "data[]", "type": "array", "required": True},
            {"field": "series[].field", "type": "number", "required": True},
        ],
        "builtInDataSources": [],
    }


def default_payload() -> dict:
    return {
        "type": COMPONENT_TYPE,
        "title": "柱状图",
        "props": {
            "xField": "period",
            "axis": {"label": "数值", "digits": 2, "position": "right"},
            "series": [{"field": "value", "label": "Value", "color": "#4387f5"}],
        },
        "data": [
            {"period": "Q1", "value": 32},
            {"period": "Q2", "value": 46},
            {"period": "Q3", "value": 41},
            {"period": "Q4", "value": 58},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a standalone bar chart.")
    parser.add_argument("--code")
    parser.add_argument("--payload")
    parser.add_argument("--data")
    parser.add_argument("--data-json")
    parser.add_argument("--title")
    parser.add_argument("--style-json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Render the built-in demo payload.")
    args, _ = parser.parse_known_args()
    if args.schema:
        print(json.dumps(component_schema(), ensure_ascii=False, indent=2))
        return 0
    payload = load_payload(args.payload, args.data_json or args.data, default_payload() if args.demo else None)
    if args.title:
        payload["title"] = args.title
    normalized = normalize_xy_series(extract_component(payload, COMPONENT_TYPE), COMPONENT_TYPE, "柱状图", "bar", args.style_json)
    write_outputs(render_svg_chart(normalized, "bar"), normalized, args.output, args.payload_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
