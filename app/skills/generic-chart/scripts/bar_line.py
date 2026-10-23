#!/usr/bin/env python3
"""Standalone dual-axis bar-line chart component."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


COLUMN_PALETTE = ["#2863f4", "#4bc3d5", "#2ab7a1", "#8b5cf6", "#ff3d7f"]
LINE_PALETTE = ["#ff6845", "#8b5cf6", "#2ab7a1", "#ff3d7f", "#4bc3d5"]


def _financial_market(component: dict[str, Any], props: dict[str, Any], rows: list[dict[str, Any]], x_field: str) -> str:
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
    labels = " ".join(str(row.get(x_field) or "") for row in rows)
    semantic_text = " ".join(
        [str(component.get("title") or props.get("title") or ""), str(component.get("subtitle") or props.get("subtitle") or ""), labels]
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


def load_payload(path: str | None, data_json: str | None, default: dict[str, Any]) -> dict[str, Any]:
    if path:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    elif data_json:
        payload = json.loads(data_json)
    else:
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


def extract_component(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("chartPayload"), dict):
        return payload["chartPayload"]
    root = payload.get("root")
    if isinstance(root, dict) and isinstance(root.get("component"), dict):
        return root["component"]
    if isinstance(payload.get("component"), dict):
        return payload["component"]
    return payload


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def number_from_style(value: Any, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        match = __import__("re").search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return default


def color_luminance(color: str) -> float | None:
    value = color.strip()
    named = {"black": "#000000", "white": "#ffffff", "dark": "#111827", "light": "#ffffff"}
    value = named.get(value.lower(), value)
    if not value.startswith("#"):
        return None
    hex_value = value[1:]
    if len(hex_value) == 3:
        hex_value = "".join(ch * 2 for ch in hex_value)
    if len(hex_value) != 6:
        return None
    try:
        red = int(hex_value[0:2], 16) / 255
        green = int(hex_value[2:4], 16) / 255
        blue = int(hex_value[4:6], 16) / 255
    except ValueError:
        return None
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def default_suffix_for_metric(field: Any, label: Any = "") -> str:
    text = f"{field or ''} {label or ''}".lower()
    rate_words = ("rate", "ratio", "pct", "percent", "growth", "margin", "return", "增速", "增长", "收益率", "利润率", "率", "%")
    return "%" if any(word in text for word in rate_words) else ""


def style_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def style_color(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def style_match_key(value: Any) -> str:
    return str(value or "").strip().lower()


def apply_series_style(series: list[dict[str, Any]], visual_style: dict[str, Any]) -> None:
    raw_styles = visual_style.get("seriesStyle")
    if not isinstance(raw_styles, list):
        return
    for style_item in raw_styles:
        if not isinstance(style_item, dict):
            continue
        key = style_match_key(style_item.get("field") or style_item.get("series") or style_item.get("name") or style_item.get("label"))
        if not key:
            continue
        for item in series:
            field = style_match_key(item.get("field"))
            label = style_match_key(item.get("label"))
            if key != field and key != label and key not in field and key not in label:
                continue
            if isinstance(style_item.get("color"), str) and style_item["color"].strip():
                item["color"] = style_item["color"].strip()
            if isinstance(style_item.get("opacity"), (int, float)):
                item["opacity"] = float(style_item["opacity"])
            if isinstance(style_item.get("strokeWidth"), (int, float)):
                item["strokeWidth"] = float(style_item["strokeWidth"])


def render_style(visual_style: dict[str, Any], theme_mode: str, explicit_style: bool) -> dict[str, Any]:
    dark = theme_mode == "dark"
    if not explicit_style and not dark:
        visual_style = {}
    container = style_dict(visual_style.get("container"))
    title = style_dict(style_dict(visual_style.get("title")).get("style"))
    x_axis = style_dict(visual_style.get("xAxis"))
    y_axis = style_dict(visual_style.get("yAxis"))
    grid = style_dict(visual_style.get("grid"))
    hover = style_dict(visual_style.get("hover"))
    margin = style_dict(visual_style.get("margin"))
    background = style_color(container.get("background"), "#181e28" if dark else "#ffffff") if explicit_style or dark else "#ffffff"
    grid_color = style_color(grid.get("color") or y_axis.get("gridColor"), "#2b3544" if dark else "#e8e8e8")
    axis_color = style_color(x_axis.get("color") or y_axis.get("color"), "#c1cad7" if dark else "#777")
    return {
        "background": background,
        "bodyBackground": background,
        "titleColor": style_color(title.get("color"), "#f1f5f9" if dark else "#16181c"),
        "titleSize": number_from_style(title.get("fontSize"), 16),
        "gridColor": grid_color,
        "axisColor": axis_color,
        "xAxisColor": style_color(x_axis.get("color"), "#c1cad7" if dark else "#666"),
        "hoverColor": style_color(hover.get("bandColor"), "#c1cad7" if dark else "#8a8a8a"),
        "hoverOpacity": number_from_style(hover.get("bandOpacity"), 0.08),
        "gridCount": int(number_from_style(grid.get("count"), 5)),
        "margin": {key: number_from_style(value, 0) for key, value in margin.items() if key in {"top", "right", "bottom", "left"}},
    }


def first_data(component: dict[str, Any], props: dict[str, Any]) -> list[dict[str, Any]]:
    raw = component.get("data") or component.get("rows") or props.get("data") or props.get("rows") or []
    if not isinstance(raw, list):
        raise ValueError("bar-line data must be an array")
    rows = [row for row in raw if isinstance(row, dict)]
    if not rows:
        raise ValueError("bar-line data must contain object rows")
    return rows


def infer_x_field(rows: list[dict[str, Any]], configured: Any = None) -> str:
    first = rows[0]
    candidate = str(configured or "").strip()
    if candidate and candidate in first:
        return candidate
    for field in ("period", "date", "year", "quarter", "month", "label", "name", "x"):
        if field in first:
            return field
    return next((key for key, value in first.items() if numeric(value) is None), next(iter(first)))


def series_from_spec(raw: Any, rows: list[dict[str, Any]], x_field: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or item.get("key") or "").strip()
            if not field or field == x_field or all(numeric(row.get(field)) is None for row in rows):
                continue
            series_type = str(item.get("type") or item.get("mark") or "").lower()
            axis = str(item.get("axis") or "").lower()
            target = lines if series_type == "line" or axis == "left" else columns
            target.append(
                {
                    "field": field,
                    "label": str(item.get("label") or item.get("name") or field),
                    "color": str(item.get("color") or ""),
                    "axis": "left" if target is lines else "right",
                    "suffix": str(item.get("suffix") or item.get("unit") or ""),
                }
            )
    return columns, lines


def infer_series(component: dict[str, Any], props: dict[str, Any], rows: list[dict[str, Any]], x_field: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_columns = component.get("columnSeries") or props.get("columnSeries")
    raw_lines = component.get("lineSeries") or props.get("lineSeries")
    columns: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for target, raw, palette, axis in ((columns, raw_columns, COLUMN_PALETTE, "right"), (lines, raw_lines, LINE_PALETTE, "left")):
        if not isinstance(raw, list):
            continue
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or item.get("key") or "").strip()
            if not field or field == x_field or all(numeric(row.get(field)) is None for row in rows):
                continue
            target.append(
                {
                    "field": field,
                    "label": str(item.get("label") or item.get("name") or field),
                    "color": str(item.get("color") or palette[index % len(palette)]),
                    "axis": axis,
                    "suffix": str(item.get("suffix") or item.get("unit") or ""),
                }
            )
    if columns and lines:
        return columns, lines

    spec_columns, spec_lines = series_from_spec(component.get("series") or props.get("series"), rows, x_field)
    columns = columns or spec_columns
    lines = lines or spec_lines
    if columns and lines:
        for index, item in enumerate(columns):
            item["color"] = item.get("color") or COLUMN_PALETTE[index % len(COLUMN_PALETTE)]
        for index, item in enumerate(lines):
            item["color"] = item.get("color") or LINE_PALETTE[index % len(LINE_PALETTE)]
        return columns, lines

    first = rows[0]
    numeric_fields = [key for key, value in first.items() if key != x_field and numeric(value) is not None]
    if not numeric_fields:
        raise ValueError("bar-line requires at least one numeric field")
    rate_words = ("rate", "ratio", "pct", "percent", "growth", "margin", "return", "增速", "增长", "率", "%")
    line_fields = [field for field in numeric_fields if any(word in field.lower() or word in field for word in rate_words)]
    if not line_fields:
        line_fields = [numeric_fields[-1]]
    column_fields = [field for field in numeric_fields if field not in line_fields] or numeric_fields[:1]
    if len(numeric_fields) == 1:
        field = numeric_fields[0]
        label = field.replace("_", " ")
        columns = [{"field": field, "label": label, "color": COLUMN_PALETTE[0], "axis": "right", "suffix": default_suffix_for_metric(field, label)}]
        lines = [{"field": field, "label": label, "color": LINE_PALETTE[0], "axis": "left", "suffix": default_suffix_for_metric(field, label)}]
        return columns, lines
    columns = [
        {
            "field": field,
            "label": field.replace("_", " "),
            "color": COLUMN_PALETTE[index % len(COLUMN_PALETTE)],
            "axis": "right",
            "suffix": default_suffix_for_metric(field),
        }
        for index, field in enumerate(column_fields)
    ]
    lines = [
        {
            "field": field,
            "label": field.replace("_", " "),
            "color": LINE_PALETTE[index % len(LINE_PALETTE)],
            "axis": "left",
            "suffix": default_suffix_for_metric(field),
        }
        for index, field in enumerate(line_fields)
    ]
    return columns, lines


def normalize_payload(payload: dict[str, Any], title_override: str | None = None, style_json: str | None = None) -> dict[str, Any]:
    component = extract_component(payload)
    props = component.get("props") if isinstance(component.get("props"), dict) else {}
    style = {}
    if isinstance(component.get("visualStyle"), dict):
        style.update(component["visualStyle"])
    explicit_style = bool(style_json and style_json.strip())
    if style_json:
        try:
            parsed = json.loads(style_json)
            if isinstance(parsed, dict):
                style.update(parsed)
        except json.JSONDecodeError:
            pass
    rows = first_data(component, props)
    x_field = infer_x_field(rows, props.get("xField") or component.get("xField"))
    columns, lines = infer_series(component, props, rows, x_field)
    apply_series_style(columns + lines, style)
    chart_style = style_dict(style.get("chart"))
    configured_theme = str(
        component.get("themeMode") or component.get("theme") or props.get("themeMode") or props.get("theme")
        or payload.get("themeMode") or payload.get("theme") or ""
    ).lower()
    theme_mode = configured_theme if configured_theme in {"light", "dark"} else ""
    if explicit_style:
        background = str(style_dict(style.get("container")).get("background") or "")
        luminance = color_luminance(background)
        if luminance is not None and luminance < 0.45:
            theme_mode = "dark"
    if theme_mode not in {"light", "dark"}:
        theme_mode = "light"
    height = int(number_from_style(chart_style.get("height"), number_from_style(component.get("height") or props.get("height"), 420)))
    return {
        "type": "bar-line",
        "financialMarket": _financial_market(component, props, rows, x_field),
        "title": str(title_override or component.get("title") or props.get("title") or "柱折图"),
        "xField": x_field,
        "data": rows,
        "views": component.get("views") if isinstance(component.get("views"), dict) else {},
        "defaultView": str(component.get("defaultView") or props.get("defaultView") or ""),
        "columnSeries": columns,
        "lineSeries": lines,
        "leftAxis": component.get("leftAxis") or props.get("leftAxis") or {"suffix": lines[0].get("suffix") or default_suffix_for_metric(lines[0].get("field"), lines[0].get("label")), "digits": 2},
        "rightAxis": component.get("rightAxis") or props.get("rightAxis") or {"suffix": columns[0].get("suffix") or default_suffix_for_metric(columns[0].get("field"), columns[0].get("label")), "digits": 2},
        "height": height,
        "aspectRatio": float(component.get("aspectRatio") or props.get("aspectRatio") or 2.8),
        "themeMode": theme_mode,
        "visualStyle": style,
        "renderStyle": render_style(style, theme_mode, explicit_style),
    }


def render_html(config: dict[str, Any]) -> str:
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(config["title"])
    body_class = "theme-dark" if config.get("themeMode") == "dark" else "theme-light"
    style = config.get("renderStyle") if isinstance(config.get("renderStyle"), dict) else {}
    background = html.escape(str(style.get("background") or "#ffffff"))
    body_background = html.escape(str(style.get("bodyBackground") or background))
    title_color = html.escape(str(style.get("titleColor") or "#16181c"))
    title_size = float(style.get("titleSize") or 16)
    grid_color = html.escape(str(style.get("gridColor") or "#ececec"))
    axis_color = html.escape(str(style.get("axisColor") or "#747474"))
    x_axis_color = html.escape(str(style.get("xAxisColor") or axis_color))
    hover_color = html.escape(str(style.get("hoverColor") or "#f7f7f7"))
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="{config.get('themeMode', 'light')}"{f' data-financial-market="{html.escape(str(config.get("financialMarket") or ""))}"' if config.get("financialMarket") else ''}>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script>(() => {{ const theme = new URLSearchParams(location.search).get('theme'); if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme; }})();</script>
<style>
*{{box-sizing:border-box}}
:root{{--sv-gain:#08745f;--sv-loss:#c43244;--sv-price-up:var(--sv-gain);--sv-price-down:var(--sv-loss)}}
:root[data-theme="dark"]{{--sv-gain:#3ddc97;--sv-loss:#ff6b6b}}
:root[data-financial-market="CN"],:root[data-financial-market="HK"]{{--sv-price-up:var(--sv-loss);--sv-price-down:var(--sv-gain)}}
:root[data-financial-market="US"]{{--sv-price-up:var(--sv-gain);--sv-price-down:var(--sv-loss)}}
html,body{{width:100%;height:100%;margin:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0;background:transparent;color:#171717}}
:root[data-theme="dark"] body,body.theme-dark{{background:transparent;color:#f1f5f9}}
.chart-component{{position:relative;width:100%;container-type:inline-size;height:clamp(340px,calc(100cqw / {config["aspectRatio"]}),{config["height"]}px);padding:0;background:transparent;overflow:visible}}
.chart-title{{min-height:22px;max-height:42px;margin:0;font-size:{title_size:g}px;font-weight:800;line-height:1.25;color:{title_color};overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
.chart-tabs{{position:absolute;z-index:3;top:8px;right:18px;display:flex;align-items:center;gap:4px}}
.chart-tab{{appearance:none;border:0;background:transparent;color:#404040;height:36px;min-width:58px;padding:0 13px;border-radius:10px;font:inherit;font-size:14px;cursor:pointer}}
.chart-tab[aria-selected="true"]{{background:#f1f1f1;color:#171717;font-weight:700}}
:root[data-theme="dark"] .chart-tab,body.theme-dark .chart-tab{{color:#c1cad7}}
:root[data-theme="dark"] .chart-tab[aria-selected="true"],body.theme-dark .chart-tab[aria-selected="true"]{{background:#202733;color:#f1f5f9}}
.chart-stage{{position:relative;width:100%;height:calc(100% - 50px);margin-top:8px;overflow:visible}}
.chart-component.has-range .chart-stage{{height:calc(100% - 90px)}}
svg{{display:block;width:100%;height:100%;overflow:visible}}
.grid-line{{stroke:{grid_color};stroke-width:1}}
.axis-line{{stroke:#a3a8b0;stroke-width:1}}
.axis-label{{fill:{axis_color};font-size:10px;font-weight:400}}
.x-label{{fill:{x_axis_color};font-size:10px;font-weight:400;text-anchor:middle}}
.bar{{rx:0;cursor:crosshair}}
.bar-label{{fill:#2863f4;font-size:11px;font-weight:700;text-anchor:middle}}
.line-path{{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}
.point{{fill:#fff;stroke-width:2;cursor:crosshair}}
:root[data-theme="dark"] .point,body.theme-dark .point{{fill:#181e28}}
.hover-zone{{fill:transparent;cursor:crosshair}}
.highlight{{fill:{hover_color};pointer-events:none}}
.chart-legend{{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:10px 18px;position:absolute;left:8px;right:8px;bottom:4px;min-height:24px;color:#858585;font-size:10px;line-height:1.2;text-align:center;pointer-events:none}}
:root[data-theme="dark"] .chart-legend,body.theme-dark .chart-legend{{color:#c1cad7}}
.legend-item{{display:flex;align-items:center;gap:7px;white-space:nowrap}}
.legend-dot{{width:8px;height:8px;border-radius:50%;flex:none}}
.chart-tooltip{{position:fixed;z-index:2147483647;display:inline-grid;min-width:0;width:fit-content;max-width:220px;padding:6px 8px;background:rgba(59,59,59,.96);color:#fff;border-radius:6px;font-size:10px;line-height:1.35;pointer-events:none;opacity:0;visibility:hidden;box-shadow:none;filter:none;white-space:nowrap;transition:opacity .08s ease}}
.chart-tooltip::after{{content:"";display:var(--tooltip-arrow-display,block);position:absolute;left:var(--arrow-left,50%);bottom:-5px;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid var(--tooltip-bg,rgba(59,59,59,.96))}}
.chart-tooltip.active{{opacity:1;visibility:visible}}
.tooltip-title{{color:#d8d8d8;margin-bottom:3px;font-size:9px;font-weight:400;line-height:1.2}}
.tooltip-row{{display:flex;align-items:center;gap:8px;min-height:17px}}
.tooltip-label{{display:flex;align-items:center;gap:5px;color:#f5f5f5;min-width:0}}
.tooltip-dot{{width:7px;height:7px;border-radius:50%;flex:none}}
.tooltip-value{{margin-left:auto;color:#fff;font-weight:650;font-variant-numeric:tabular-nums}}
.range-shell{{display:none;--handle-size:32px;height:var(--handle-size);margin:6px 0 0;padding:0 calc(var(--handle-size) / 2);position:relative;touch-action:pan-y}}
.chart-component.has-range .range-shell{{display:block}}
.range-shell[hidden]{{display:none}}
.range-track{{position:relative;width:100%;height:var(--handle-size)}}
.range-track::before{{content:"";position:absolute;left:0;right:0;top:calc(var(--handle-size) / 2);height:3px;background:#f1f1f1;border-radius:999px;transform:translateY(-50%)}}
.range-selection{{position:absolute;top:calc(var(--handle-size) / 2);height:3px;background:#5f5f5f;border-radius:999px;transform:translateY(-50%)}}
.range-handle{{appearance:none;position:absolute;top:calc(var(--handle-size) / 2);width:var(--handle-size);height:var(--handle-size);border-radius:50%;border:1px solid #d5d5d5;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.18);transform:translate(-50%,-50%);display:flex;align-items:center;justify-content:center;cursor:grab;z-index:2;padding:0;user-select:none}}
.range-handle:active{{cursor:grabbing}}
.range-handle::before{{content:"";width:2px;height:13px;border-radius:999px;background:#8a8a8a;box-shadow:-5px 0 0 #8a8a8a,5px 0 0 #8a8a8a;opacity:.9}}
:root[data-theme="dark"] .range-track::before,body.theme-dark .range-track::before{{background:#2b3544}}
:root[data-theme="dark"] .range-selection,body.theme-dark .range-selection{{background:#93a0b3}}
:root[data-theme="dark"] .range-handle,body.theme-dark .range-handle{{border-color:#334052;background:#181e28;box-shadow:0 1px 5px rgba(0,0,0,.35)}}
:root[data-theme="dark"] .range-handle::before,body.theme-dark .range-handle::before{{background:#c1cad7;box-shadow:-5px 0 0 #c1cad7,5px 0 0 #c1cad7}}
@media(min-width:1200px){{.chart-component{{height:{config["height"]}px}}}}
@media(max-width:680px){{.chart-component{{height:clamp(248px,calc(100cqw / {config["aspectRatio"]}),320px);padding:0}}.chart-component.has-range{{height:clamp(286px,calc((100cqw / {config["aspectRatio"]}) + 38px),358px)}}.chart-title{{min-height:18px;max-height:38px;font-size:14px;line-height:1.28;padding:0}}.chart-tabs{{top:4px;right:0;gap:2px}}.chart-tab{{height:30px;min-width:44px;padding:0 8px;border-radius:8px;font-size:12px}}.chart-stage{{height:calc(100% - 50px);margin-top:6px}}.chart-component.has-range .chart-stage{{height:calc(100% - 88px)}}.axis-label,.x-label{{font-size:10px}}.bar-label{{display:none}}.chart-legend{{left:0;right:0;bottom:0;gap:8px 12px;min-height:30px;font-size:10px;align-content:center}}.legend-item{{gap:5px;max-width:42%;overflow:hidden;text-overflow:ellipsis}}.legend-dot{{width:8px;height:8px}}.chart-tooltip{{min-width:0;max-width:220px;font-size:10px;padding:6px 8px;white-space:normal}}.tooltip-label{{min-width:0}}.range-shell{{--handle-size:24px;margin-top:4px;padding:0 calc(var(--handle-size) / 2)}}.range-handle::before{{height:11px;box-shadow:-4px 0 0 #8a8a8a,4px 0 0 #8a8a8a}}}}
.chart-component{{display:flex;flex-direction:column}}.chart-title{{flex:none}}.chart-stage,.chart-component.has-range .chart-stage{{flex:1;min-height:0;height:auto!important}}.range-shell{{flex:none;order:2;margin-top:10px}}.chart-legend{{position:static;flex:none;order:3;margin-top:12px;padding:0 4px 4px;min-height:24px}}.legend-item{{white-space:normal;max-width:100%!important;overflow:visible;line-height:1.4}}
</style>
</head>
<body class="{body_class}">
<section class="chart-component">
  <h2 class="chart-title">{title}</h2>
  <div class="chart-tabs" role="tablist"></div>
  <div class="chart-stage"><svg role="img" aria-label="{title}"></svg></div>
  <div class="chart-legend"></div>
  <div class="range-shell" hidden aria-label="Time range filter"><div class="range-track"><div class="range-selection"></div><button class="range-handle" type="button" data-range-handle="left" aria-label="range start"></button><button class="range-handle" type="button" data-range-handle="right" aria-label="range end"></button></div></div>
  <div class="chart-tooltip"></div>
</section>
<script>
const config = {config_json};
const root = document.querySelector('.chart-component');
const svg = root.querySelector('svg');
const legend = root.querySelector('.chart-legend');
const tooltip = root.querySelector('.chart-tooltip');
const tabs = root.querySelector('.chart-tabs');
const rangeShell = root.querySelector('.range-shell');
const rangeTrack = root.querySelector('.range-track');
const rangeSelection = root.querySelector('.range-selection');
const leftHandle = root.querySelector('[data-range-handle="left"]');
const rightHandle = root.querySelector('[data-range-handle="right"]');
const NS = 'http://www.w3.org/2000/svg';
const COLUMN_PALETTE = {json.dumps(COLUMN_PALETTE)};
const LINE_PALETTE = {json.dumps(LINE_PALETTE)};
let activeView = config.defaultView;
let rangeStart = null;
let rangeEnd = null;
let draggingRangeHandle = null;
let tooltipPortalAckUntil = 0;
const isObject = value => value && typeof value === 'object' && !Array.isArray(value);
const deepMerge = (base, patch) => {{
  const result = {{...(base || {{}})}};
  Object.entries(patch || {{}}).forEach(([key, value]) => {{
    result[key] = isObject(value) && isObject(result[key]) ? deepMerge(result[key], value) : value;
  }});
  return result;
}};
const toNumber = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const DEFAULT_STYLE = {{
  margin: {{top: 28, right: 0, bottom: 46, left: 0}},
  grid: {{visible: true, count: 5, color: '#e8e8e8', width: 1, dasharray: '', opacity: 1}},
  xAxis: {{visible: true, color: '#666', fontSize: 10, fontWeight: 400, lineColor: '#a3a8b0', lineWidth: 1}},
  yAxis: {{position: 'both', labelPlacement: 'reserved', paddingRatio: 0.08, color: '#747474', fontSize: 10, fontWeight: 400, lineColor: '#a3a8b0', lineWidth: 1, digits: 0}},
  bar: {{borderRadius: 0, opacity: 1, maxWidth: 42, gap: 10, showLabels: true}},
  line: {{showPoints: 'auto', strokeWidth: 2, opacity: 1, strokeLinecap: 'round', strokeLinejoin: 'round'}},
  point: {{visible: true, radius: 3.2, outerRadius: 0, fill: 'background', strokeWidth: 1.6}},
  legend: {{visible: true, gap: 18, color: '#858585', fontSize: 10, markerSize: 8, markerShape: 'circle'}},
  tooltip: {{visible: true, placement: 'aboveFirstGrid', offsetY: 0, gap: 8, background: 'rgba(59,59,59,.96)', color: '#fff', borderRadius: 6, padding: '6px 8px', fontSize: 10, maxWidth: 220, arrow: true}},
  hover: {{bandColor: '#8a8a8a', bandOpacity: 0.08}},
  range: {{threshold: 10, count: 10}},
  seriesStyle: [],
}};
const DARK_STYLE = {{
  grid: {{color: '#2b3544', opacity: 1}},
  xAxis: {{color: '#c1cad7', lineColor: '#334052'}},
  yAxis: {{color: '#c1cad7', lineColor: '#334052'}},
  legend: {{color: '#c1cad7'}},
  tooltip: {{background: '#202733', color: '#f1f5f9'}},
  hover: {{bandColor: '#c1cad7', bandOpacity: 0.08}},
}};
const isDark = document.documentElement.dataset.theme === 'dark' || config.themeMode === 'dark';
const visual = deepMerge(deepMerge(DEFAULT_STYLE, isDark ? DARK_STYLE : {{}}), config.visualStyle || {{}});
const DARK_COLOR_ALIASES = {{'#2863f4':'#8294ff','#4bc3d5':'#34d3ad','#2ab7a1':'#34d3ad','#8b5cf6':'#d19dff','#ff3d7f':'#ff7188','#ff6845':'#ff9592','#00b899':'#34d3ad','#ff2f57':'#ff7188','#94a3b8':'#93a0b3'}};
const chartColorCache = new Map();
const chartColor = color => {{
  const raw = String(color || '');
  const themed = isDark ? (DARK_COLOR_ALIASES[raw.toLowerCase()] || raw) : raw;
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
(config.columnSeries || []).forEach(series => {{ series.color = chartColor(series.color); }});
(config.lineSeries || []).forEach(series => {{ series.color = chartColor(series.color); }});
function matchesColorRule(value, condition) {{
  const match = String(condition || '').trim().match(/^(<=|>=|==|=|<|>)\\s*(-?(?:\\d+(?:\\.\\d*)?|\\.\\d+))$/);
  if (!match || !Number.isFinite(Number(value))) return false;
  const threshold = Number(match[2]);
  return match[1] === '<' ? value < threshold
    : match[1] === '<=' ? value <= threshold
    : match[1] === '>' ? value > threshold
    : match[1] === '>=' ? value >= threshold
    : value === threshold;
}}
function barMarkColor(row, series, value) {{
  const explicit = row?.__markColors?.[series.field];
  if (explicit) return chartColor(explicit);
  const rules = Array.isArray(visual.colorRules) ? visual.colorRules : [];
  const matched = rules.find(rule => (!rule?.field || String(rule.field) === String(series.field)) && matchesColorRule(value, rule?.condition));
  return chartColor(matched?.color || series.color);
}}
if (visual.customCss || visual.css) {{
  const style = document.createElement('style');
  style.dataset.visualStyle = 'bar-line';
  style.textContent = String(visual.customCss || visual.css);
  document.head.appendChild(style);
}}
tooltip.style.background = visual.tooltip.background;
tooltip.style.color = visual.tooltip.color;
tooltip.style.borderRadius = `${{toNumber(visual.tooltip.borderRadius, 6)}}px`;
tooltip.style.padding = visual.tooltip.padding || '6px 8px';
tooltip.style.fontSize = `${{toNumber(visual.tooltip.fontSize, 10)}}px`;
tooltip.style.maxWidth = `${{toNumber(visual.tooltip.maxWidth, 220)}}px`;
tooltip.style.setProperty('--tooltip-arrow-display', visual.tooltip.arrow === false ? 'none' : 'block');
tooltip.style.setProperty('--tooltip-bg', visual.tooltip.background);
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
    return {{doc: currentWindow.document, win: currentWindow, offsetLeft, offsetTop}};
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
  if (doc.getElementById('bar-line-tooltip-portal-style')) return;
  const style = doc.createElement('style');
  style.id = 'bar-line-tooltip-portal-style';
  style.textContent = `
    .bar-line-tooltip-portal{{position:fixed;z-index:2147483647;display:inline-grid;min-width:0;width:fit-content;max-width:220px;padding:6px 8px;background:rgba(59,59,59,.96);color:#fff;border-radius:6px;font:10px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;pointer-events:none;opacity:0;visibility:hidden;box-shadow:none;filter:none;white-space:normal;transition:opacity .08s ease}}
    .bar-line-tooltip-portal.active{{opacity:1;visibility:visible}}
    .bar-line-tooltip-portal .tooltip-title{{color:#d8d8d8;margin-bottom:3px;font-size:9px;font-weight:400;line-height:1.2}}
    .bar-line-tooltip-portal .tooltip-row{{display:flex;align-items:center;gap:8px;min-height:17px}}
    .bar-line-tooltip-portal .tooltip-label{{display:flex;align-items:center;gap:5px;color:#f5f5f5;min-width:0}}
    .bar-line-tooltip-portal .tooltip-dot{{width:7px;height:7px;border-radius:50%;flex:none}}
    .bar-line-tooltip-portal .tooltip-value{{margin-left:auto;color:#fff;font-weight:650;font-variant-numeric:tabular-nums}}
    .bar-line-tooltip-portal .tooltip-arrow{{position:absolute;left:var(--arrow-left,50%);bottom:-5px;transform:translateX(-50%);width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid var(--tooltip-bg,rgba(59,59,59,.96))}}
  `;
  doc.head.appendChild(style);
}}
function parentTooltipElement(ctx) {{
  ensureParentTooltipStyle(ctx.doc);
  const id = 'bar-line-tooltip-portal-' + chartEmbedKey();
  let element = ctx.doc.getElementById(id);
  if (!element) {{
    element = ctx.doc.createElement('div');
    element.id = id;
    element.className = 'bar-line-tooltip-portal';
    ctx.doc.body.appendChild(element);
  }}
  element.style.background = visual.tooltip.background;
  element.style.color = visual.tooltip.color;
  element.style.borderRadius = `${{toNumber(visual.tooltip.borderRadius, 6)}}px`;
  element.style.padding = visual.tooltip.padding || '6px 8px';
  element.style.fontSize = `${{toNumber(visual.tooltip.fontSize, 10)}}px`;
  element.style.maxWidth = `${{toNumber(visual.tooltip.maxWidth, 220)}}px`;
  element.style.setProperty('--tooltip-bg', visual.tooltip.background);
  return element;
}}
function postTooltipPortal(action, payload = {{}}) {{
  try {{
    if (!window.parent || window.parent === window) return false;
    window.parent.postMessage({{
      type: 'bar-line-tooltip-portal',
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
  if (event.data?.type !== 'bar-line-tooltip-portal-ack') return;
  tooltipPortalAckUntil = Date.now() + 250;
  if (event.data.action === 'show') tooltip.classList.remove('active');
}});
const node = (name, attrs = {{}}, text = '') => {{
  const el = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value));
  if (text !== '') el.textContent = text;
  return el;
}};
const asNumber = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const asFiniteNumber = value => Number.isFinite(Number(value)) ? Number(value) : null;
function applyView(viewKey) {{
  if (!config.views?.[viewKey]) return;
  activeView = viewKey;
  const view = config.views[viewKey];
  config.data = view.data || config.data;
  config.leftAxis = view.leftAxis || config.leftAxis;
  config.rightAxis = view.rightAxis || config.rightAxis;
  tabs.querySelectorAll('.chart-tab').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.value === viewKey)));
  rangeStart = null;
  rangeEnd = null;
  hideTooltip();
  render();
}}
Object.entries(config.views || {{}}).forEach(([key, view]) => {{
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'chart-tab';
  button.role = 'tab';
  button.dataset.value = key;
  button.textContent = view.label || key;
  button.setAttribute('aria-selected', String(key === activeView));
  button.addEventListener('click', () => applyView(key));
  tabs.appendChild(button);
}});
if (activeView && config.views?.[activeView]) {{
  const view = config.views[activeView];
  config.data = view.data || config.data;
  config.leftAxis = view.leftAxis || config.leftAxis;
  config.rightAxis = view.rightAxis || config.rightAxis;
}}
const rangeThreshold = () => Math.max(10, Math.round(toNumber(visual.range?.threshold, 10)));
const visibleCount = total => Math.min(total, Math.max(10, Math.round(toNumber(visual.range?.count, 10))));
const fullRows = () => Array.isArray(config.data) ? config.data : [];
function ensureRangeState() {{
  const rows = fullRows();
  const count = visibleCount(rows.length);
  if (rows.length < rangeThreshold()) {{
    rangeStart = 0;
    rangeEnd = Math.max(0, rows.length - 1);
    return;
  }}
  if (rangeStart == null || rangeEnd == null) {{
    rangeEnd = Math.max(0, rows.length - 1);
    rangeStart = Math.max(0, rangeEnd - count + 1);
  }}
  rangeStart = Math.max(0, Math.min(rows.length - 1, Number(rangeStart) || 0));
  rangeEnd = Math.max(rangeStart, Math.min(rows.length - 1, Number(rangeEnd) || rangeStart));
}}
const visibleRows = () => {{
  const rows = fullRows();
  if (rows.length < rangeThreshold()) return rows;
  ensureRangeState();
  return rows.slice(rangeStart, rangeEnd + 1);
}};
function syncRangeControls() {{
  const rows = fullRows();
  const enabled = rows.length >= rangeThreshold();
  root.classList.toggle('has-range', enabled);
  rangeShell.hidden = !enabled;
  if (!enabled) return;
  ensureRangeState();
  const denominator = Math.max(1, rows.length - 1);
  const left = rangeStart / denominator * 100;
  const right = rangeEnd / denominator * 100;
  rangeSelection.style.left = `${{left}}%`;
  rangeSelection.style.width = `${{Math.max(0, right - left)}}%`;
  leftHandle.style.left = `${{left}}%`;
  rightHandle.style.left = `${{right}}%`;
  leftHandle.setAttribute('aria-label', `Start period ${{rows[rangeStart]?.[config.xField] ?? ''}}`);
  rightHandle.setAttribute('aria-label', `End period ${{rows[rangeEnd]?.[config.xField] ?? ''}}`);
}}
function rangeIndexFromClientX(clientX, count) {{
  const rect = rangeTrack.getBoundingClientRect();
  const ratio = rect.width <= 0 ? 0 : Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  return Math.round(ratio * Math.max(0, count - 1));
}}
function updateRangeByIndex(index) {{
  if (draggingRangeHandle === 'left') rangeStart = Math.min(index, rangeEnd ?? index);
  if (draggingRangeHandle === 'right') rangeEnd = Math.max(index, rangeStart ?? index);
  hideTooltip();
  render();
}}
function setupRangeDrag() {{
  let origin = null;
  const rememberTouch = event => {{ origin = event.pointerType === 'touch' ? {{x:event.clientX,y:event.clientY}} : null; }};
  const startDrag = handle => event => {{
    rememberTouch(event);
    draggingRangeHandle = handle;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    if (event.pointerType !== 'touch') event.preventDefault();
  }};
  leftHandle.addEventListener('pointerdown', startDrag('left'));
  rightHandle.addEventListener('pointerdown', startDrag('right'));
  rangeTrack.addEventListener('pointerdown', event => {{
    if (event.target.closest('.range-handle')) return;
    rememberTouch(event);
    const rows = fullRows();
    if (rows.length < rangeThreshold()) return;
    ensureRangeState();
    const index = rangeIndexFromClientX(event.clientX, rows.length);
    draggingRangeHandle = Math.abs(index - rangeStart) <= Math.abs(index - rangeEnd) ? 'left' : 'right';
    if (!origin) updateRangeByIndex(index);
    if (event.pointerType !== 'touch') event.preventDefault();
  }});
  window.addEventListener('pointermove', event => {{
    if (!draggingRangeHandle) return;
    if (origin) {{
      const dx=Math.abs(event.clientX-origin.x),dy=Math.abs(event.clientY-origin.y);
      if(dy>6&&dy>dx){{draggingRangeHandle=null;return;}}
      if(dx<6)return;
    }}
    const rows = fullRows();
    if (rows.length < rangeThreshold()) return;
    updateRangeByIndex(rangeIndexFromClientX(event.clientX, rows.length));
  }});
  window.addEventListener('pointerup', event => {{ if(draggingRangeHandle&&origin)updateRangeByIndex(rangeIndexFromClientX(event.clientX,fullRows().length));draggingRangeHandle=null;origin=null; }});
  window.addEventListener('pointercancel', () => {{draggingRangeHandle=null;origin=null;}});
}}
setupRangeDrag();
function fmt(value, axis) {{
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value ?? '');
  const suffix = axis?.suffix || '';
  if (numeric === 0) return '0.00' + suffix;
  const useCompact = axis?.compact !== false && !suffix.includes('%');
  const localeText = [
    config.locale,
    config.language,
    config.title,
    ...(config.columnSeries || []).map(item => item.label || item.name || item.field || ''),
    ...(config.lineSeries || []).map(item => item.label || item.name || item.field || '')
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
  if (useCompact) {{
    if (cjkUnits) {{
      const matched = cjkUnits.find(([, threshold]) => abs >= threshold);
      if (matched) {{ unit = matched[0]; scaled = numeric / matched[1]; }}
    }} else if (abs >= 1e4) {{
      if (abs >= 1e12) {{ scaled = numeric / 1e12; unit = 'T'; }}
      else if (abs >= 1e9) {{ scaled = numeric / 1e9; unit = 'B'; }}
      else if (abs >= 1e6) {{ scaled = numeric / 1e6; unit = 'M'; }}
      else {{ scaled = numeric / 1e3; unit = 'K'; }}
    }}
  }}
  const explicitDigits = Number(axis?.digits);
  const digits = Number.isFinite(explicitDigits) ? Math.max(2, explicitDigits) : 2;
  const formatted = scaled.toLocaleString(locale, {{minimumFractionDigits:digits,maximumFractionDigits:digits}});
  return formatted + unit + suffix;
}}
function uniqueFormattedTicks(ticks, axis) {{
  const formatted = ticks.map(value => fmt(value, axis));
  if (new Set(formatted).size === formatted.length) return formatted;
  const expandedAxis = {{...(axis || {{}})}};
  for (let digits = 2; digits <= 4; digits += 1) {{
    expandedAxis.digits = digits;
    const retry = ticks.map(value => fmt(value, expandedAxis));
    if (new Set(retry).size === retry.length) return retry;
  }}
  return ticks.map(value => String(Number(value).toPrecision(4)) + (axis?.suffix || ''));
}}
function estimateAxisWidth(labels) {{
  const widthFor = label => Array.from(String(label || '')).reduce((total, char) => {{
    if (/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(char)) return total + 11;
    if (/[A-Z]/.test(char)) return total + 7;
    if (/[-0-9.%,+]/.test(char)) return total + 6;
    return total + 6.5;
  }}, 4);
  return Math.max(28, Math.min(86, Math.ceil(Math.max(...labels.map(widthFor), 0)) + 1));
}}
function measureAxisWidth(labels, fontSize, fontWeight) {{
  try {{
    const canvas = measureAxisWidth.canvas || (measureAxisWidth.canvas = document.createElement('canvas'));
    const ctx = canvas.getContext('2d');
    ctx.font = `${{fontWeight || 400}} ${{toNumber(fontSize, 10)}}px -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif`;
    const widths = labels.map(label => ctx.measureText(String(label || '')).width);
    return Math.max(0, Math.ceil(Math.max(...widths, 0)));
  }} catch (error) {{
    return estimateAxisWidth(labels);
  }}
}}
function axisLegendText(axis) {{
  const explicit = axis?.description || axis?.label || axis?.title || axis?.name || axis?.axisLabel;
  return explicit ? String(explicit) : '';
}}
function niceStep(range, count = 4) {{
  const rough = Math.max(range / count, 0.0001);
  const power = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / power;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * power;
}}
function makeRange(values, count = 5) {{
  const positive = values.filter(value => Number.isFinite(Number(value))).map(Number);
  let min = Math.min(0, ...positive);
  let max = Math.max(0, ...positive);
  if (min === max) {{ min -= 1; max += 1; }}
  const maxStep = niceStep(Math.abs(max) / Math.max(1, count - 1), count - 1);
  const minStep = niceStep(Math.abs(min) / Math.max(1, count - 1), count - 1);
  max = Math.ceil(max / maxStep) * maxStep;
  min = Math.floor(min / minStep) * minStep;
  if (min >= 0) min = 0;
  const step = (max - min) / Math.max(1, count - 1);
  const ticks = Array.from({{length: count}}, (_, index) => Number((max - step * index).toFixed(10)));
  return {{min, max, ticks}};
}}
function zeroRatio(range) {{
  if (range.min >= 0) return 1;
  if (range.max <= 0) return 0;
  return range.max / (range.max - range.min);
}}
function snapZeroTarget(ratio) {{
  if (ratio <= 0.125) return 0;
  if (ratio >= 0.875) return 1;
  return Math.max(0.25, Math.min(0.75, Math.round(ratio * 4) / 4));
}}
function niceCeil(value) {{
  const step = niceStep(Math.max(Math.abs(value), 0.0001), 4);
  return Math.max(step, Math.ceil(Math.abs(value) / step) * step);
}}
function alignedTicks(min, max, count) {{
  return Array.from({{length: count}}, (_, index) => Number((max - (max - min) * index / Math.max(1, count - 1)).toFixed(10)));
}}
function alignRangeToZero(range, targetRatio, count = 5) {{
  if (targetRatio <= 0) {{
    const span = niceCeil(Math.max(Math.abs(range.min), 1));
    return {{min:-span,max:0,ticks:alignedTicks(-span, 0, count)}};
  }}
  if (targetRatio >= 1) {{
    const span = niceCeil(Math.max(Math.abs(range.max), 1));
    return {{min:0,max:span,ticks:alignedTicks(0, span, count)}};
  }}
  const positive = Math.max(0, range.max);
  const negative = Math.max(0, -range.min);
  const span = Math.max(positive / targetRatio, negative / (1 - targetRatio), 1);
  const min = -span * (1 - targetRatio);
  const max = span * targetRatio;
  return {{min,max,ticks:alignedTicks(min, max, count)}};
}}
function alignZeroRanges(left, right, count = 5) {{
  const leftMixed = left.min < 0 && left.max > 0;
  const rightMixed = right.min < 0 && right.max > 0;
  const leftPositive = left.min >= 0;
  const rightPositive = right.min >= 0;
  const leftNegative = left.max <= 0;
  const rightNegative = right.max <= 0;
  let target = 0.5;
  if (leftPositive && rightPositive) target = 1;
  else if (leftNegative && rightNegative) target = 0;
  else if (leftMixed && rightMixed) target = (zeroRatio(left) + zeroRatio(right)) / 2;
  else if (leftMixed) target = zeroRatio(left);
  else if (rightMixed) target = zeroRatio(right);
  if (target > 0 && target < 1) target = snapZeroTarget(target);
  return {{left: alignRangeToZero(left, target, count), right: alignRangeToZero(right, target, count)}};
}}
function scale(range, top, height) {{
  return value => top + height - (asNumber(value) - range.min) / (range.max - range.min) * height;
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
function tooltipPosition(anchorX, preferredTop, tooltipWidth, tooltipHeight, viewport = {{}}) {{
  const viewportLeft = Number.isFinite(Number(viewport.left)) ? Number(viewport.left) : 0;
  const viewportTop = Number.isFinite(Number(viewport.top)) ? Number(viewport.top) : 0;
  const viewportRight = Number.isFinite(Number(viewport.right)) ? Number(viewport.right) : window.innerWidth;
  const viewportBottom = Number.isFinite(Number(viewport.bottom)) ? Number(viewport.bottom) : window.innerHeight;
  const minLeft = viewportLeft;
  const maxLeft = viewportRight - tooltipWidth;
  const left = maxLeft >= minLeft ? Math.min(maxLeft, Math.max(minLeft, anchorX - tooltipWidth / 2)) : minLeft;
  const top = preferredTop;
  const arrowLeft = Math.min(tooltipWidth - 14, Math.max(14, anchorX - left));
  return {{ left, top, arrowLeft }};
}}
function titleRectInContext(ctx) {{
  const title = root.querySelector('.chart-title');
  if (!title) return null;
  const range = document.createRange();
  range.selectNodeContents(title);
  const rect = range.getBoundingClientRect();
  return {{ left: ctx.offsetLeft + rect.left, right: ctx.offsetLeft + rect.right, top: ctx.offsetTop + rect.top, bottom: ctx.offsetTop + rect.bottom }};
}}
function avoidTitleOverlap(bounds, tooltipWidth, tooltipHeight, titleRect, anchorX, viewportLeft, viewportRight, safeDistance = 0) {{
  if (!titleRect) return bounds;
  const tooltipRect = {{ left: bounds.left, right: bounds.left + tooltipWidth, top: bounds.top, bottom: bounds.top + tooltipHeight }};
  const overlaps = tooltipRect.left < titleRect.right && tooltipRect.right > titleRect.left && tooltipRect.top < titleRect.bottom && tooltipRect.bottom > titleRect.top;
  if (!overlaps) return bounds;
  const aboveTitleTop = titleRect.top - tooltipHeight - safeDistance;
  if (aboveTitleTop >= safeDistance) {{
    return {{ ...bounds, top: aboveTitleTop, arrowLeft: Math.min(tooltipWidth - 14, Math.max(14, anchorX - bounds.left)) }};
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
  return {{ ...bounds, left, arrowLeft: Math.min(tooltipWidth - 14, Math.max(14, anchorX - left)) }};
}}
function showTooltip(anchorX, rows, xLabel, gridTop) {{
  if (visual.tooltip.visible === false) return;
  const tooltipHtml = `<div class="tooltip-title">${{xLabel}}</div>` + rows.map(row => `<div class="tooltip-row"><span class="tooltip-label"><i class="tooltip-dot" style="background:${{row.color}}"></i>${{row.label}}</span><span class="tooltip-value">${{row.text}}</span></div>`).join('');
  const stage = root.querySelector('.chart-stage');
  const stageRect = stage.getBoundingClientRect();
  const rootRect = root.getBoundingClientRect();
  const ctx = parentTooltipContext();
  const tooltipGap = toNumber(visual.tooltip.gap, 12);
  const offsetY = toNumber(visual.tooltip.offsetY, 0);

  if (ctx) {{
    tooltip.classList.remove('active');
    const portal = parentTooltipElement(ctx);
    portal.innerHTML = tooltipHtml + (visual.tooltip.arrow === false ? '' : '<span class="tooltip-arrow"></span>');
    const parentWidth = ctx.win?.innerWidth || ctx.doc.defaultView?.innerWidth || ctx.doc.documentElement.clientWidth || 0;
    const parentHeight = ctx.win?.innerHeight || ctx.doc.defaultView?.innerHeight || ctx.doc.documentElement.clientHeight || 0;
    const absoluteAnchorX = ctx.offsetLeft + stageRect.left + anchorX;
    const absoluteRootLeft = ctx.offsetLeft + rootRect.left;
    const absoluteRootRight = ctx.offsetLeft + rootRect.right;
    const availableRootWidth = Math.max(0, absoluteRootRight - absoluteRootLeft);
    portal.style.minWidth = '0';
    portal.style.maxWidth = `${{Math.min(toNumber(visual.tooltip.maxWidth, 220), availableRootWidth)}}px`;
    const firstGridTop = ctx.offsetTop + stageRect.top + gridTop;
    const preferredTop = firstGridTop - portal.offsetHeight - tooltipGap + offsetY;
    let bounds = tooltipPosition(
      absoluteAnchorX,
      preferredTop,
      portal.offsetWidth,
      portal.offsetHeight,
      {{
        left: absoluteRootLeft,
        top: 0,
        right: absoluteRootRight,
        bottom: parentHeight,
      }}
    );
    if (portal.offsetWidth > 0 && parentWidth > 0) {{
      portal.style.left = `${{bounds.left}}px`;
      portal.style.top = `${{bounds.top}}px`;
      portal.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
      portal.classList.add('active');
      postChartHeight();
      return;
    }}
  }}

  if (window.parent && window.parent !== window) {{
    tooltip.classList.remove('active');
    postTooltipPortal('show', {{
      html: tooltipHtml + (visual.tooltip.arrow === false ? '' : '<span class="tooltip-arrow"></span>'),
      anchorX,
      stageLeft: stageRect.left,
      stageTop: stageRect.top,
      rootLeft: rootRect.left,
      rootRight: rootRect.right,
      gridTop,
      gap: tooltipGap,
      offsetY,
      maxWidth: toNumber(visual.tooltip.maxWidth, 220),
      background: visual.tooltip.background,
      color: visual.tooltip.color,
      borderRadius: toNumber(visual.tooltip.borderRadius, 6),
      padding: visual.tooltip.padding || '6px 8px',
      fontSize: toNumber(visual.tooltip.fontSize, 10),
    }});
    const fallbackTime = Date.now();
    setTimeout(() => {{
      if (tooltipPortalAckUntil >= fallbackTime) return;
      tooltip.innerHTML = tooltipHtml;
      tooltip.classList.add('active');
      const absoluteAnchorX = stageRect.left + anchorX;
      const availableRootWidth = Math.max(0, rootRect.right - rootRect.left);
      tooltip.style.minWidth = '0';
      tooltip.style.maxWidth = `${{Math.min(toNumber(visual.tooltip.maxWidth, 220), availableRootWidth)}}px`;
      const preferredTop = stageRect.top + gridTop - tooltip.offsetHeight - tooltipGap + offsetY;
      const bounds = tooltipPosition(
        absoluteAnchorX,
        preferredTop,
        tooltip.offsetWidth,
        tooltip.offsetHeight,
        {{
          left: rootRect.left,
          top: 0,
          right: rootRect.right,
          bottom: window.innerHeight,
        }}
      );
      tooltip.style.left = `${{bounds.left}}px`;
      tooltip.style.top = `${{bounds.top}}px`;
      tooltip.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
      postChartHeight();
    }}, 60);
    postChartHeight();
    return;
  }}

  tooltip.innerHTML = tooltipHtml;
  tooltip.classList.add('active');
  const absoluteAnchorX = stageRect.left + anchorX;
  const availableRootWidth = Math.max(0, rootRect.right - rootRect.left);
  tooltip.style.minWidth = '0';
  tooltip.style.maxWidth = `${{Math.min(toNumber(visual.tooltip.maxWidth, 220), availableRootWidth)}}px`;
  const preferredTop = stageRect.top + gridTop - tooltip.offsetHeight - tooltipGap + offsetY;
  const bounds = tooltipPosition(
    absoluteAnchorX,
    preferredTop,
    tooltip.offsetWidth,
    tooltip.offsetHeight,
    {{
      left: rootRect.left,
      top: 0,
      right: rootRect.right,
      bottom: window.innerHeight,
    }}
  );
  tooltip.style.left = `${{bounds.left}}px`;
  tooltip.style.top = `${{bounds.top}}px`;
  tooltip.style.setProperty('--arrow-left', `${{bounds.arrowLeft}}px`);
  postChartHeight();
}}
function hideTooltip() {{
  tooltip.classList.remove('active');
  const ctx = parentTooltipContext();
  const portal = ctx ? parentTooltipElement(ctx) : null;
  if (portal) portal.classList.remove('active');
  postTooltipPortal('hide');
  postChartHeight();
}}
function postChartHeight() {{
  const nodes = [root.querySelector('.chart-stage'), svg, root].filter(Boolean);
  const height = Math.ceil(Math.max(80, ...nodes.map(node => node.getBoundingClientRect().bottom || 0)));
  try {{
    if (window.frameElement) {{
      window.frameElement.style.height = `${{height}}px`;
      window.frameElement.style.minHeight = '0';
    }}
  }} catch (e) {{}}
  try {{ parent.postMessage({{type:'analysis-planner-chart-height', height}}, '*'); }} catch (e) {{}}
}}
function setHighlight(index) {{
  svg.querySelectorAll('[data-highlight-index]').forEach(item => item.setAttribute('opacity', Number(item.dataset.highlightIndex) === index ? String(visual.hover.bandOpacity) : '0'));
}}
function clearHighlight() {{ svg.querySelectorAll('[data-highlight-index]').forEach(item => item.setAttribute('opacity', '0')); }}
function render() {{
  svg.innerHTML = '';
  legend.innerHTML = '';
  syncRangeControls();
  const width = svg.clientWidth || 900;
  const height = svg.clientHeight || 300;
  const isMobile = width < 680;
  const rows = visibleRows();
  const columnSeries = config.columnSeries || [];
  const lineSeries = config.lineSeries || [];
  const margin = {{...(width >= 1200 ? {{top:28,right:0,bottom:46,left:0}} : isMobile ? {{top:18,right:0,bottom:30,left:0}} : visual.margin)}};
  const customMargin = config.renderStyle?.margin || {{}};
  ['top','right','bottom','left'].forEach(key => {{
    if (Number.isFinite(Number(customMargin[key])) && Number(customMargin[key]) > 0) margin[key] = Number(customMargin[key]);
  }});
  ['top','right','bottom','left'].forEach(key => margin[key] = Math.max(0, Number(margin[key]) || 0));
  const gridCount = Math.max(2, Number(visual.grid?.count || config.renderStyle?.gridCount || 5));
  let leftRange = makeRange(rows.flatMap(row => lineSeries.map(series => asFiniteNumber(row[series.field]))), gridCount);
  let rightRange = makeRange(rows.flatMap(row => columnSeries.map(series => asNumber(row[series.field]))), gridCount);
  const aligned = alignZeroRanges(leftRange, rightRange, gridCount);
  leftRange = aligned.left;
  rightRange = aligned.right;
  const leftTickLabels = uniqueFormattedTicks(leftRange.ticks, config.leftAxis);
  const rightTickLabels = uniqueFormattedTicks(rightRange.ticks, config.rightAxis);
  const leftAxisLegend = axisLegendText(config.leftAxis);
  const rightAxisLegend = axisLegendText(config.rightAxis);
  const rightAxisGap = isMobile ? 8 : 10;
  const leftAxisGap = isMobile ? 8 : 12;
  const leftTickWidth = measureAxisWidth(leftTickLabels, visual.yAxis.fontSize, visual.yAxis.fontWeight);
  const rightTickWidth = measureAxisWidth(rightTickLabels, visual.yAxis.fontSize, visual.yAxis.fontWeight);
  margin.left = Math.max(margin.left, leftTickWidth + leftAxisGap + 2);
  margin.right = Math.max(0, rightTickWidth + rightAxisGap);
  if (leftAxisLegend || rightAxisLegend) {{
    const axisFontSize = toNumber(visual.yAxis.fontSize, 10);
    margin.top = Math.max(margin.top, axisFontSize * 2 + 12);
  }}
  const plotW = Math.max(isMobile ? 96 : 140, width - margin.left - margin.right);
  const plotH = Math.max(isMobile ? 96 : 110, height - margin.top - margin.bottom);
  const rightAxisX = margin.left + plotW + rightAxisGap + rightTickWidth;
  const yLeft = scale(leftRange, margin.top, plotH);
  const yRight = scale(rightRange, margin.top, plotH);
  leftRange.ticks.forEach((value, index) => {{
    const gy = yLeft(value);
    if (visual.grid.visible !== false) svg.appendChild(node('line', {{x1:margin.left,y1:gy,x2:margin.left+plotW,y2:gy,class:'grid-line',stroke:visual.grid.color,'stroke-width':visual.grid.width,'stroke-dasharray':visual.grid.dasharray || '',opacity:visual.grid.opacity}}));
    svg.appendChild(node('text', {{x:margin.left-leftAxisGap,y:gy+4,class:'axis-label','text-anchor':'end'}}, leftTickLabels[index] ?? fmt(value, config.leftAxis)));
    const rightValue = rightRange.ticks[index] ?? '';
    if (rightValue !== '') svg.appendChild(node('text', {{x:rightAxisX,y:gy+4,class:'axis-label','text-anchor':'end'}}, rightTickLabels[index] ?? fmt(rightValue, config.rightAxis)));
  }});
  if (leftAxisLegend) {{
    const axisFontSize = toNumber(visual.yAxis.fontSize, 10);
    const leftLegendX = Math.max(0, margin.left - leftAxisGap - leftTickWidth);
    svg.appendChild(node('text', {{x:leftLegendX,y:margin.top-axisFontSize-6,class:'axis-label y-axis-legend','text-anchor':'start'}}, leftAxisLegend));
  }}
  if (rightAxisLegend) {{
    const axisFontSize = toNumber(visual.yAxis.fontSize, 10);
    svg.appendChild(node('text', {{x:rightAxisX,y:margin.top-axisFontSize-6,class:'axis-label y-axis-legend','text-anchor':'end'}}, rightAxisLegend));
  }}
  svg.appendChild(node('line', {{x1:margin.left,y1:yLeft(0),x2:margin.left+plotW,y2:yLeft(0),class:'axis-line'}}));
  const rowCount = rows.length;
  const slot = plotW / Math.max(rowCount, 1);
  const xCenter = index => margin.left + slot * index + slot / 2;
  const xLabels = rows.map(row => row[config.xField]);
  const xLabelIndexes = sampledXAxisIndexes(xLabels, slot, visual.xAxis.fontSize, visual.xAxis.fontWeight);
  rows.forEach((row, index) => {{
    if (xLabelIndexes.has(index)) {{
      svg.appendChild(node('text', {{x:xCenter(index),y:margin.top+plotH+20,class:'x-label'}}, row[config.xField]));
    }}
  }});
  const barCount = Math.max(1, columnSeries.length);
  const barGap = barCount > 1 ? 1 : 0;
  const maxBarW = Math.max(12, toNumber(visual.bar.maxWidth, isMobile ? 28 : 42));
  const minBarW = isMobile ? 3 : 5;
  const targetGroupW = Math.max(minBarW * barCount + barGap * Math.max(0, barCount - 1), slot * 2 / 3);
  let barW = (targetGroupW - barGap * Math.max(0, barCount - 1)) / barCount;
  barW = Math.max(minBarW, Math.min(maxBarW, barW));
  const groupW = barW * barCount + barGap * Math.max(0, barCount - 1);
  const bandW = Math.min(slot, Math.max(groupW + (isMobile ? 16 : 28), 44));
  rows.forEach((row, rowIndex) => {{
    const groupX = xCenter(rowIndex) - groupW / 2;
    const highlight = node('rect', {{x:xCenter(rowIndex) - bandW / 2,y:margin.top,width:bandW,height:plotH,class:'highlight',opacity:0,'data-highlight-index':rowIndex}});
    svg.insertBefore(highlight, svg.firstChild);
    columnSeries.forEach((series, seriesIndex) => {{
      const value = asNumber(row[series.field]);
      const y0 = yRight(0);
      const y1 = yRight(value);
      const bar = node('rect', {{x:groupX + seriesIndex * (barW + barGap),y:Math.min(y0,y1),width:barW,height:Math.max(1,Math.abs(y0-y1)),fill:barMarkColor(row, series, value),opacity:series.opacity ?? visual.bar.opacity,class:'bar',rx:toNumber(visual.bar.borderRadius, 0)}});
      svg.appendChild(bar);
      const canShowBarValue = visual.bar.showLabels !== false && columnSeries.length === 1 && slot >= 48 && barW >= 16;
      if (canShowBarValue) {{
        const labelY = value >= 0 ? Math.max(12, Math.min(y0,y1) - 7) : Math.min(margin.top + plotH - 4, Math.max(y0,y1) + 14);
        svg.appendChild(node('text', {{x:groupX + seriesIndex * (barW + barGap) + barW / 2,y:labelY,class:'bar-label'}}, fmt(value, config.rightAxis)));
      }}
    }});
  }});
  lineSeries.forEach(series => {{
    const points = rows.map((row, index) => {{
      const value = asFiniteNumber(row[series.field]);
      return value === null ? null : [xCenter(index), yLeft(value), value];
    }});
    const pathData = points.map((point, index) => {{
      if (!point) return '';
      const previousPoint = points.slice(0, index).reverse().find(Boolean);
      return `${{previousPoint ? 'L' : 'M'}}${{point[0]}} ${{point[1]}}`;
    }}).filter(Boolean).join(' ');
    if (pathData) svg.appendChild(node('path', {{d:pathData,class:'line-path',stroke:series.color,'stroke-width':series.strokeWidth || visual.line.strokeWidth,opacity:series.opacity ?? visual.line.opacity}}));
    const canShowDots = slot >= 18;
    if (visual.point.visible !== false && (visual.line.showPoints === true || (visual.line.showPoints !== false && canShowDots))) {{
      points.forEach(point => {{
        if (!point) return;
        const fill = visual.point.fill === 'transparent' ? 'transparent' : (visual.point.fill === 'background' || visual.point.fill === 'series' ? '{background}' : (visual.point.fill || '{background}'));
        svg.appendChild(node('circle', {{cx:point[0],cy:point[1],r:toNumber(visual.point.radius, 3.2),class:'point',fill,stroke:series.color,'stroke-width':toNumber(visual.point.strokeWidth, 1.6)}}));
      }});
    }}
  }});
  rows.forEach((row, rowIndex) => {{
    const rows = [
      ...columnSeries.map(series => {{ const value = asNumber(row[series.field]); return {{label:series.label,color:barMarkColor(row, series, value),text:fmt(value, config.rightAxis)}}; }}),
      ...lineSeries.map(series => {{
        const value = asFiniteNumber(row[series.field]);
        return {{label:series.label,color:series.color,text:value === null ? (row.yoy_note || '缺少基期') : fmt(value, config.leftAxis)}};
      }})
    ];
    const hit = node('rect', {{x:margin.left + slot * rowIndex,y:margin.top,width:slot,height:plotH,class:'hover-zone'}});
    hit.addEventListener('mouseenter', () => {{ setHighlight(rowIndex); showTooltip(xCenter(rowIndex), rows, row[config.xField], margin.top); }});
    hit.addEventListener('mousemove', () => {{ setHighlight(rowIndex); showTooltip(xCenter(rowIndex), rows, row[config.xField], margin.top); }});
    hit.addEventListener('mouseleave', () => {{ clearHighlight(); hideTooltip(); }});
    svg.appendChild(hit);
  }});
  [...columnSeries, ...lineSeries].forEach(series => {{
    const item = document.createElement('span');
    item.className = 'legend-item';
    item.innerHTML = `<i class="legend-dot" style="width:${{visual.legend.markerSize}}px;height:${{visual.legend.markerSize}}px;border-radius:${{visual.legend.markerShape === 'square' ? 2 : 999}}px;background:${{series.color}}"></i>${{series.label}}`;
    item.style.color = visual.legend.color;
    item.style.fontSize = `${{visual.legend.fontSize}}px`;
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


def component_schema() -> dict[str, Any]:
    return {
        "type": "bar-line",
        "name": "柱折图",
        "visualChannelMappings": [
            {"semantic": "横轴维度", "field": "xField", "visualChannel": "xAxis.category", "required": True},
            {"semantic": "柱系列", "field": "columnSeries[].field", "visualChannel": "bar.height", "required": True},
            {"semantic": "折线系列", "field": "lineSeries[].field", "visualChannel": "line.y", "required": True},
        ],
        "dataContract": [
            {"field": "data[]", "type": "array", "required": True},
            {"field": "columnSeries[].field", "type": "number", "required": True},
            {"field": "lineSeries[].field", "type": "number", "required": True},
        ],
    }


def default_payload() -> dict[str, Any]:
    return {
        "type": "bar-line",
        "title": "美国GDP、人口与失业率",
        "xField": "year",
        "columnSeries": [
            {"field": "gdp_index", "label": "GDP指数（2020=100）", "color": "#2863f4"},
            {"field": "population_index", "label": "人口指数（2020=100）", "color": "#4bc3d5"},
        ],
        "lineSeries": [{"field": "unemployment_rate", "label": "失业率（%）", "color": "#ff6845"}],
        "leftAxis": {"label": "失业率", "suffix": "%", "digits": 0},
        "rightAxis": {"label": "指数", "digits": 0},
        "data": [
            {"year": "2020", "gdp_index": 100, "population_index": 100, "unemployment_rate": 8.1},
            {"year": "2021", "gdp_index": 110, "population_index": 100.2, "unemployment_rate": 5.4},
            {"year": "2022", "gdp_index": 120, "population_index": 100.5, "unemployment_rate": 3.6},
            {"year": "2023", "gdp_index": 127, "population_index": 100.8, "unemployment_rate": 3.6},
            {"year": "2024", "gdp_index": 137, "population_index": 101.6, "unemployment_rate": 4.0},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a standalone dual-axis bar-line chart.")
    parser.add_argument("--code")
    parser.add_argument("--payload")
    parser.add_argument("--data")
    parser.add_argument("--data-json")
    parser.add_argument("--title")
    parser.add_argument("--style-json")
    parser.add_argument("--style-code")
    parser.add_argument("--style-file")
    parser.add_argument("--output")
    parser.add_argument("--payload-output")
    parser.add_argument("--schema", action="store_true")
    args, _ = parser.parse_known_args()
    if args.schema:
        print(json.dumps(component_schema(), ensure_ascii=False, indent=2))
        return 0
    if not args.output:
        parser.error("--output is required unless --schema is used")
    style_json = args.style_json
    if args.style_file:
        style_json = Path(args.style_file).expanduser().read_text(encoding="utf-8")
    payload = load_payload(args.payload, args.data_json or args.data, default_payload())
    normalized = normalize_payload(payload, args.title, style_json)
    write_outputs(render_html(normalized), normalized, args.output, args.payload_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
