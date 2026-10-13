#!/usr/bin/env python3
"""Render Mermaid journey diagrams with responsive, colorful, mobile-fullscreen output."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_JOURNEY = """journey
  title 用户旅程
  section 发现
    提出问题: 4: 用户
  section 分析
    获取信息: 5: 系统
    形成结论: 5: 系统"""

DEFAULT_TASK_PALETTE = [
    {"fillColor": "#EFF6FF", "strokeColor": "#60A5FA", "textColor": "#172554"},
    {"fillColor": "#ECFDF5", "strokeColor": "#34D399", "textColor": "#064E3B"},
    {"fillColor": "#FFF7ED", "strokeColor": "#FB923C", "textColor": "#431407"},
    {"fillColor": "#F5F3FF", "strokeColor": "#A78BFA", "textColor": "#2E1065"},
    {"fillColor": "#FDF2F8", "strokeColor": "#F472B6", "textColor": "#500724"},
    {"fillColor": "#F0FDFA", "strokeColor": "#2DD4BF", "textColor": "#134E4A"},
]

DEFAULT_SECTION_PALETTE = [
    {"fillColor": "#DBEAFE", "strokeColor": "#93C5FD", "textColor": "#1E3A8A"},
    {"fillColor": "#D1FAE5", "strokeColor": "#6EE7B7", "textColor": "#065F46"},
    {"fillColor": "#FFEDD5", "strokeColor": "#FDBA74", "textColor": "#9A3412"},
    {"fillColor": "#EDE9FE", "strokeColor": "#C4B5FD", "textColor": "#5B21B6"},
    {"fillColor": "#FCE7F3", "strokeColor": "#F9A8D4", "textColor": "#9D174D"},
    {"fillColor": "#CCFBF1", "strokeColor": "#5EEAD4", "textColor": "#115E59"},
]

DEFAULT_STYLE = {
    "fillColor": "#F8FAFC",
    "strokeColor": "#94A3B8",
    "textColor": "#0F172A",
    "strokeWidth": 1.5,
}

VALID_SECURITY_LEVELS = {"strict", "loose", "antiscript", "sandbox"}
VALID_COLOR_MODES = {"byOrder", "bySection", "single"}
MERMAID_PREFIXES = ("journey",)


def parse_json_or_text(value: str) -> Any:
    """Parse JSON when possible; otherwise preserve raw Mermaid text."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def unwrap_chart_payload(payload: dict[str, Any]) -> dict[str, Any]:
    chart_payload = payload.get("chartPayload")
    if not isinstance(chart_payload, dict):
        return payload
    unwrapped = dict(chart_payload)
    for key in ("title", "actors", "visualStyle", "theme", "themeMode"):
        if key in payload and key not in unwrapped:
            unwrapped[key] = payload[key]
    return unwrapped


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Load a payload while allowing CLI values to override file values."""
    if args.payload:
        payload: Any = json.loads(
            Path(args.payload).expanduser().read_text(encoding="utf-8")
        )
    elif args.data_json:
        payload = json.loads(args.data_json)
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {"data": payload}
    payload = unwrap_chart_payload(payload)

    if args.data is not None:
        payload["data"] = parse_json_or_text(args.data)
    remove_stale_code_data(payload, args.code)
    if args.code is not None and looks_like_mermaid(args.code):
        payload["data"] = {"mermaid": args.code}
    if args.title is not None:
        payload["title"] = args.title
    return payload


def looks_like_mermaid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip().lower()
    return any(stripped.startswith(prefix) for prefix in MERMAID_PREFIXES)


def remove_stale_code_data(payload: dict[str, Any], code: str | None) -> None:
    """Drop ticker/domain codes accidentally written into Mermaid payload slots."""
    if not code:
        return
    code_text = str(code).strip()
    if not code_text:
        return

    for key in ("mermaid", "code", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() == code_text and not looks_like_mermaid(value):
            payload.pop(key, None)

    data = payload.get("data")
    if isinstance(data, str) and data.strip() == code_text and not looks_like_mermaid(data):
        payload.pop("data", None)
    elif isinstance(data, dict):
        for key in ("mermaid", "code", "content", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip() == code_text and not looks_like_mermaid(value):
                data.pop(key, None)
        if not data:
            payload.pop("data", None)


def clean_mermaid_label(value: Any, fallback: str) -> str:
    text = str(value if value is not None else fallback).strip()
    text = re.sub(r"[\r\n]+", " ", text)
    text = text.replace(":", "：")
    return text or fallback


def normalize_score(value: Any, fallback: int = 4) -> int:
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return fallback
    return max(1, min(5, score))


def normalize_actors(value: Any) -> str:
    if isinstance(value, list):
        actors = [clean_mermaid_label(item, "") for item in value]
        actors = [item for item in actors if item]
        if actors:
            return ", ".join(actors)
    if isinstance(value, str) and value.strip():
        return clean_mermaid_label(value, "用户")
    return "用户"


def stages_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    payload = unwrap_chart_payload(payload)
    raw = payload.get("stages")
    if raw is None and isinstance(payload.get("data"), dict):
        raw = payload["data"].get("stages")
    return raw if isinstance(raw, list) else []


def stages_to_mermaid(payload: dict[str, Any]) -> str | None:
    stages = stages_from_payload(payload)
    if not stages:
        return None

    title = clean_mermaid_label(payload.get("title"), "用户旅程")
    lines = ["journey", f"  title {title}"]
    wrote_step = False
    for section_index, stage in enumerate(stages, start=1):
        if isinstance(stage, dict):
            section_title = stage.get("title") or stage.get("stage") or stage.get("name")
            items = stage.get("items") or stage.get("steps") or stage.get("tasks")
        else:
            section_title = stage
            items = None

        lines.append(f"  section {clean_mermaid_label(section_title, f'阶段{section_index}')}")
        if isinstance(items, list) and items:
            for item_index, item in enumerate(items, start=1):
                if isinstance(item, dict):
                    label = item.get("detail") or item.get("label") or item.get("title") or item.get("name")
                    score = normalize_score(item.get("score") or item.get("rating"), 4)
                    actors = normalize_actors(item.get("actors") or item.get("actor") or item.get("owner"))
                else:
                    label = item
                    score = 4
                    actors = "用户"
                lines.append(f"    {clean_mermaid_label(label, f'步骤{item_index}')}: {score}: {actors}")
                wrote_step = True
        else:
            lines.append("    梳理关键动作: 4: 用户")
            wrote_step = True

    return "\n".join(lines) if wrote_step else None


def first_non_empty(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def journey_text(payload: dict[str, Any]) -> str:
    """Read Mermaid journey syntax from common payload locations."""
    payload = unwrap_chart_payload(payload)
    direct = first_non_empty(payload, ("mermaid", "code", "content", "text"))
    if direct and looks_like_mermaid(direct):
        return direct

    data = payload.get("data")
    if isinstance(data, str) and data.strip() and looks_like_mermaid(data):
        return data.strip()
    if isinstance(data, dict):
        nested = first_non_empty(data, ("content", "mermaid", "code", "text"))
        if nested and looks_like_mermaid(nested):
            return nested
    staged = stages_to_mermaid(payload)
    if staged:
        return staged
    return DEFAULT_JOURNEY


def extract_inner_title(code: str) -> str | None:
    match = re.search(r"(?im)^\s*title\s+(.+?)\s*$", code)
    return match.group(1).strip() if match else None


def strip_inner_title(code: str) -> str:
    """Remove Mermaid's internal title so the external left title is not duplicated."""
    return re.sub(r"(?im)^\s*title\s+.+?\s*$\n?", "", code, count=1).strip()


def safe_css_color(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", text):
        return text
    if re.fullmatch(r"(?:rgb|rgba|hsl|hsla)\([^;\n\r]+\)", text):
        return text
    if re.fullmatch(r"[A-Za-z]+", text):
        return text
    return fallback


def safe_positive_number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def normalize_style(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "fillColor": safe_css_color(source.get("fillColor"), str(fallback["fillColor"])),
        "strokeColor": safe_css_color(source.get("strokeColor"), str(fallback["strokeColor"])),
        "textColor": safe_css_color(source.get("textColor"), str(fallback["textColor"])),
        "strokeWidth": safe_positive_number(
            source.get("strokeWidth"), float(fallback.get("strokeWidth", 1.5))
        ),
    }


def resolve_palette(payload: dict[str, Any], key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = payload.get(key)
    if raw is None and key == "taskPalette":
        raw = payload.get("palette")

    result: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                result.append(
                    normalize_style(
                        {
                            "fillColor": item,
                            "strokeColor": item,
                            "textColor": DEFAULT_STYLE["textColor"],
                        },
                        DEFAULT_STYLE,
                    )
                )
            elif isinstance(item, dict):
                result.append(normalize_style(item, DEFAULT_STYLE))

    if result:
        return result
    return [normalize_style(item, DEFAULT_STYLE) for item in fallback]


def mermaid_config(payload: dict[str, Any]) -> dict[str, Any]:
    security_level = str(payload.get("securityLevel") or "loose")
    if security_level not in VALID_SECURITY_LEVELS:
        security_level = "loose"

    task_palette = resolve_palette(payload, "taskPalette", DEFAULT_TASK_PALETTE)
    section_palette = resolve_palette(payload, "sectionPalette", DEFAULT_SECTION_PALETTE)
    first_task = task_palette[0]
    first_section = section_palette[0]
    second_section = section_palette[1 % len(section_palette)]

    theme_variables: dict[str, Any] = {
        "fontFamily": '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif',
        "fontSize": "15px",
        "background": "transparent",
        "mainBkg": "transparent",
        "primaryTextColor": "#0F172A",
        "textColor": "#0F172A",
        "lineColor": "#94A3B8",
        "gridColor": "#CBD5E1",
        "sectionBkgColor": first_section["fillColor"],
        "altSectionBkgColor": second_section["fillColor"],
        "sectionBkgColor2": second_section["fillColor"],
        "sectionTextColor": first_section["textColor"],
        "taskBkgColor": first_task["fillColor"],
        "taskBorderColor": first_task["strokeColor"],
        "taskTextColor": first_task["textColor"],
        "taskTextOutsideColor": "#334155",
        "actorBkg": "#FFFFFF",
        "actorBorder": "#CBD5E1",
        "actorTextColor": "#334155",
        "actorLineColor": "#CBD5E1",
        "signalColor": "#64748B",
        "signalTextColor": "#334155",
        "labelBoxBkgColor": "#FFFFFF",
        "labelBoxBorderColor": "#CBD5E1",
        "labelTextColor": "#334155",
    }
    custom = payload.get("themeVariables")
    if isinstance(custom, dict):
        theme_variables.update(custom)

    return {
        "startOnLoad": False,
        "theme": "base",
        "securityLevel": security_level,
        "themeVariables": theme_variables,
    }


def build_html(payload: dict[str, Any]) -> str:
    raw_code = journey_text(payload)
    inner_title = extract_inner_title(raw_code)
    title = str(payload.get("title") or inner_title or "旅程图")
    safe_title = html.escape(title)

    hide_inner_title = payload.get("hideInnerTitle", True) is not False
    render_code = strip_inner_title(raw_code) if hide_inner_title else raw_code
    if not render_code.lower().lstrip().startswith("journey"):
        render_code = "journey\n" + render_code

    color_mode = str(payload.get("colorMode") or "byOrder")
    if color_mode not in VALID_COLOR_MODES:
        color_mode = "byOrder"

    code_json = json.dumps(render_code, ensure_ascii=False)
    config_json = json.dumps(mermaid_config(payload), ensure_ascii=False)
    task_palette_json = json.dumps(
        resolve_palette(payload, "taskPalette", DEFAULT_TASK_PALETTE),
        ensure_ascii=False,
    )
    section_palette_json = json.dumps(
        resolve_palette(payload, "sectionPalette", DEFAULT_SECTION_PALETTE),
        ensure_ascii=False,
    )
    color_mode_json = json.dumps(color_mode)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>{safe_title}</title>
<style>
:root{{--journey-text:#0F172A;--fullscreen-bg:#FFFFFF}}
*{{box-sizing:border-box}}
html,body{{
  margin:0;
  width:100%;
  min-height:0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:transparent!important;
  color:var(--journey-text);
  overflow:hidden;
}}
#wrap{{
  position:relative;
  width:100%;
  min-height:520px;
  height:auto;
  overflow:hidden;
  background:transparent;
}}
#title{{
  position:absolute;
  left:16px;
  right:16px;
  top:14px;
  z-index:20;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  font-size:18px;
  line-height:28px;
  font-weight:720;
  letter-spacing:-.01em;
  text-align:left;
  pointer-events:none;
}}
#viewport{{
  position:relative;
  width:100%;
  min-height:520px;
  overflow:auto;
  background:transparent;
}}
#diagram{{
  display:flex;
  align-items:flex-start;
  justify-content:center;
  min-width:100%;
  min-height:520px;
  padding:60px 28px 26px;
  background:transparent;
}}
#diagram svg{{
  display:block;
  max-width:none!important;
  height:auto!important;
  background:transparent!important;
  overflow:visible;
}}
#diagram svg text{{font-family:inherit!important}}
#fullscreenBtn,#exitFullscreenBtn{{
  position:absolute;
  z-index:30;
  display:none;
  align-items:center;
  justify-content:center;
  width:26px;
  height:26px;
  padding:0;
  border:1px solid rgba(15,23,42,.12);
  border-radius:6px;
  background:rgba(255,255,255,.94);
  color:#334155;
  box-shadow:0 6px 18px rgba(15,23,42,.10);
  cursor:pointer;
  -webkit-tap-highlight-color:transparent;
}}
#fullscreenBtn{{right:12px;top:10px}}
#exitFullscreenBtn{{
  right:max(14px,env(safe-area-inset-right));
  top:max(14px,env(safe-area-inset-top));
}}
#fullscreenBtn svg,#exitFullscreenBtn svg{{
  display:block;
  width:14px;
  height:14px;
  fill:none;
  stroke:currentColor;
  stroke-width:2;
  stroke-linecap:round;
  stroke-linejoin:round;
}}
#fullscreenBtn:hover,#exitFullscreenBtn:hover{{background:#F8FAFC}}
#fullscreenBtn:active,#exitFullscreenBtn:active{{transform:translateY(1px)}}
#error{{
  display:none;
  position:absolute;
  left:20px;
  right:20px;
  bottom:20px;
  z-index:40;
  padding:12px 14px;
  border:1px solid #FCA5A5;
  border-radius:10px;
  background:#FFFFFF;
  color:#991B1B;
  font-size:13px;
  white-space:pre-wrap;
}}
#source{{
  display:none;
  margin:0;
  padding:60px 24px 24px;
  color:#334155;
  background:transparent;
  font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  white-space:pre-wrap;
}}
html.is-fullscreen-root,
html.is-fullscreen-root body,
body.is-fullscreen{{
  width:100vw;
  height:100vh;
  overflow:hidden;
  background:var(--fullscreen-bg)!important;
}}
body.is-fullscreen #wrap{{
  position:fixed;
  inset:0;
  width:100vw;
  height:100vh;
  z-index:9999;
  background:var(--fullscreen-bg)!important;
}}
body.is-fullscreen #viewport,
body.is-fullscreen #diagram{{background:var(--fullscreen-bg)!important}}
body.is-fullscreen #title{{
  top:max(14px,env(safe-area-inset-top));
  left:max(18px,env(safe-area-inset-left));
  right:56px;
  font-size:16px;
}}
body.is-fullscreen #fullscreenBtn{{display:none!important}}
body.is-fullscreen #exitFullscreenBtn{{display:inline-flex}}
body.is-fullscreen #diagram{{padding:58px 28px 20px}}
@media (orientation:portrait){{
  body.is-fullscreen #wrap{{
    width:100vh;
    height:100vw;
    left:50%;
    top:50%;
    right:auto;
    bottom:auto;
    transform:translate(-50%,-50%) rotate(90deg);
    transform-origin:center center;
  }}
}}
body.is-fullscreen.is-forced-landscape #wrap{{
  width:100vh;
  height:100vw;
  left:50%;
  top:50%;
  right:auto;
  bottom:auto;
  transform:translate(-50%,-50%) rotate(90deg);
  transform-origin:center center;
}}
@media (max-width:720px){{
  #title{{left:12px;right:52px;top:10px;font-size:16px}}
  #fullscreenBtn{{display:inline-flex}}
  #wrap,#viewport,#diagram{{min-height:460px}}
  #diagram{{padding:54px 16px 22px}}
  #source{{padding:54px 18px 24px}}
}}
</style>
</head>
<body>
<div id="wrap">
  <div id="title">{safe_title}</div>
  <button id="fullscreenBtn" type="button" aria-label="横屏全屏浏览" title="横屏全屏浏览">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5"></path><path d="M16 3h5v5"></path><path d="M21 16v5h-5"></path><path d="M3 16v5h5"></path></svg>
  </button>
  <button id="exitFullscreenBtn" type="button" aria-label="退出全屏" title="退出全屏">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3v6H3"></path><path d="M15 3v6h6"></path><path d="M21 15h-6v6"></path><path d="M3 15h6v6"></path></svg>
  </button>
  <div id="viewport">
    <div id="diagram"></div>
    <pre id="source"></pre>
    <div id="error"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.4/dist/mermaid.min.js"></script>
<script>
const code = {code_json};
const config = {config_json};
const taskPalette = {task_palette_json};
const sectionPalette = {section_palette_json};
const colorMode = {color_mode_json};
const diagram = document.getElementById("diagram");
const viewport = document.getElementById("viewport");
const errorBox = document.getElementById("error");
const sourceBox = document.getElementById("source");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const exitFullscreenBtn = document.getElementById("exitFullscreenBtn");
let svg = null;
let naturalWidth = 0;
let naturalHeight = 0;

function measuredHeight() {{
  const candidates = [document.getElementById("wrap"), viewport, diagram, svg, errorBox, sourceBox]
    .filter(Boolean)
    .filter((node) => {{
      const style = window.getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden";
    }});
  const bottom = candidates.reduce((max, node) => {{
    const rect = node.getBoundingClientRect();
    return rect.height > 1 ? Math.max(max, rect.bottom) : max;
  }}, 0);
  return Math.max(420, Math.ceil(bottom || document.body.scrollHeight || document.documentElement.scrollHeight || 520));
}}

function postChartHeight() {{
  try {{
    window.parent?.postMessage({{type:"analysis-planner-chart-height",height:measuredHeight()}}, "*");
  }} catch (e) {{}}
}}

function uniqueElements(elements) {{
  return Array.from(new Set(elements));
}}

function setImportantStyle(element, property, value) {{
  if (!element || !value) return;
  element.style.setProperty(property, value, "important");
}}

function paintShape(shape, style) {{
  if (!shape || !style) return;
  setImportantStyle(shape, "fill", style.fillColor);
  setImportantStyle(shape, "stroke", style.strokeColor);
  if (style.strokeWidth) setImportantStyle(shape, "stroke-width", `${{style.strokeWidth}}px`);
}}

function paintText(root, color) {{
  if (!root || !color) return;
  root.querySelectorAll("text,tspan").forEach((node) => setImportantStyle(node, "fill", color));
  root.querySelectorAll("foreignObject div,foreignObject span,foreignObject p").forEach((node) => {{
    setImportantStyle(node, "color", color);
  }});
}}

function styleForIndex(palette, index) {{
  if (!Array.isArray(palette) || !palette.length) return null;
  if (colorMode === "single") return palette[0];
  return palette[index % palette.length];
}}

function findTaskShapes() {{
  if (!svg) return [];
  return uniqueElements([
    ...svg.querySelectorAll("g.task > rect, g.task > path, g.task > polygon"),
    ...svg.querySelectorAll("rect.task, path.task, polygon.task"),
    ...svg.querySelectorAll("rect[id^='task'], path[id^='task'], polygon[id^='task']")
  ]).filter((shape) => !shape.closest("defs"));
}}

function findSectionShapes() {{
  if (!svg) return [];
  return uniqueElements([
    ...svg.querySelectorAll("g.journey-section > rect, g.journey-section > path, g.journey-section > polygon"),
    ...svg.querySelectorAll("rect.journey-section, path.journey-section, polygon.journey-section"),
    ...svg.querySelectorAll("rect[class*='section-type'], path[class*='section-type'], polygon[class*='section-type']")
  ]).filter((shape) => !shape.closest("defs"));
}}

function applyJourneyPalette() {{
  if (!svg) return;

  const sections = findSectionShapes();
  sections.forEach((shape, index) => {{
    const style = styleForIndex(sectionPalette, index);
    paintShape(shape, style);
    const group = shape.closest("g");
    if (group && style) paintText(group, style.textColor);
  }});

  const tasks = findTaskShapes();
  tasks.forEach((shape, index) => {{
    let paletteIndex = index;
    if (colorMode === "bySection") {{
      const group = shape.closest("g");
      const classText = `${{shape.getAttribute("class") || ""}} ${{group?.getAttribute("class") || ""}}`;
      const match = classText.match(/section-type-(\\d+)/i);
      if (match) paletteIndex = Number.parseInt(match[1], 10) || 0;
    }}
    const style = styleForIndex(taskPalette, paletteIndex);
    paintShape(shape, style);
    const group = shape.closest("g");
    if (group && style) paintText(group, style.textColor);
  }});
}}

function fitDiagram() {{
  if (!svg || !naturalWidth || !naturalHeight) return;
  const isFullscreen = document.body.classList.contains("is-fullscreen");
  const compact = window.innerWidth <= 720;
  const horizontalPadding = isFullscreen ? 56 : (compact ? 32 : 56);
  const verticalPadding = isFullscreen ? 80 : (compact ? 76 : 92);
  const availableWidth = Math.max(240, viewport.clientWidth - horizontalPadding);
  const availableHeight = Math.max(180, viewport.clientHeight - verticalPadding);
  const widthScale = availableWidth / naturalWidth;
  const heightScale = availableHeight / naturalHeight;
  const scale = isFullscreen
    ? Math.max(0.1, Math.min(widthScale, heightScale))
    : Math.min(1, widthScale, heightScale);
  svg.style.width = `${{Math.round(naturalWidth * scale)}}px`;
  viewport.scrollTo({{left:0, top:0}});
}}

function updateFullscreenLayout() {{
  const active = document.body.classList.contains("is-fullscreen");
  const needsForcedLandscape = active && window.innerHeight > window.innerWidth;
  document.body.classList.toggle("is-forced-landscape", needsForcedLandscape);
}}

function lockLandscape() {{
  try {{
    const orientation = screen.orientation;
    if (orientation && typeof orientation.lock === "function") {{
      orientation.lock("landscape").catch(() => {{}});
    }}
  }} catch (e) {{}}
}}

function unlockOrientation() {{
  try {{
    const orientation = screen.orientation;
    if (orientation && typeof orientation.unlock === "function") orientation.unlock();
  }} catch (e) {{}}
}}

function refitDiagram() {{
  updateFullscreenLayout();
  requestAnimationFrame(() => {{
    fitDiagram();
    postChartHeight();
  }});
  setTimeout(() => {{ fitDiagram(); postChartHeight(); }}, 80);
  setTimeout(() => {{ fitDiagram(); postChartHeight(); }}, 320);
}}

async function enterFullscreen() {{
  document.documentElement.classList.add("is-fullscreen-root");
  document.body.classList.add("is-fullscreen");
  updateFullscreenLayout();
  const target = document.documentElement || document.body;
  try {{
    if (target.requestFullscreen) await target.requestFullscreen();
    else if (target.webkitRequestFullscreen) target.webkitRequestFullscreen();
  }} catch (e) {{}}
  lockLandscape();
  refitDiagram();
}}

function exitFullscreen() {{
  document.documentElement.classList.remove("is-fullscreen-root");
  document.body.classList.remove("is-fullscreen");
  document.body.classList.remove("is-forced-landscape");
  unlockOrientation();
  try {{
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitFullscreenElement && document.webkitExitFullscreen) document.webkitExitFullscreen();
  }} catch (e) {{}}
  refitDiagram();
}}

fullscreenBtn.addEventListener("click", enterFullscreen);
exitFullscreenBtn.addEventListener("click", exitFullscreen);

document.addEventListener("fullscreenchange", () => {{
  if (!document.fullscreenElement) {{
    document.documentElement.classList.remove("is-fullscreen-root");
    document.body.classList.remove("is-fullscreen");
    document.body.classList.remove("is-forced-landscape");
    unlockOrientation();
    refitDiagram();
  }}
}});

document.addEventListener("webkitfullscreenchange", () => {{
  if (!document.webkitFullscreenElement) {{
    document.documentElement.classList.remove("is-fullscreen-root");
    document.body.classList.remove("is-fullscreen");
    document.body.classList.remove("is-forced-landscape");
    unlockOrientation();
    refitDiagram();
  }}
}});

mermaid.initialize(config);
(async () => {{
  try {{
    await mermaid.parse(code);
    const result = await mermaid.render("journeySvg", code);
    diagram.innerHTML = result.svg;
    if (typeof result.bindFunctions === "function") result.bindFunctions(diagram);

    svg = diagram.querySelector("svg");
    if (!svg) throw new Error("Mermaid did not return an SVG element.");

    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    naturalWidth = viewBox && viewBox.width ? viewBox.width : svg.getBoundingClientRect().width;
    naturalHeight = viewBox && viewBox.height ? viewBox.height : svg.getBoundingClientRect().height;

    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
    applyJourneyPalette();
    refitDiagram();
  }} catch (err) {{
    errorBox.style.display = "block";
    errorBox.textContent = `旅程图渲染失败：${{String(err?.message || err)}}`;
    diagram.style.display = "none";
    sourceBox.style.display = "block";
    sourceBox.textContent = code;
    postChartHeight();
  }}
}})();

if ("ResizeObserver" in window) {{
  new ResizeObserver(postChartHeight).observe(document.getElementById("wrap"));
}}
window.addEventListener("load", postChartHeight);
window.addEventListener("resize", refitDiagram);
window.addEventListener("orientationchange", () => {{
  setTimeout(refitDiagram, 120);
  setTimeout(refitDiagram, 420);
}});
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a responsive Mermaid journey diagram."
    )
    parser.add_argument("--code", help="Raw Mermaid journey syntax.")
    parser.add_argument("--title")
    parser.add_argument("--payload", help="Path to a JSON payload file.")
    parser.add_argument("--data-json", help="Complete payload encoded as JSON.")
    parser.add_argument("--data", help="JSON data or raw Mermaid syntax.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    args, _ = parser.parse_known_args()

    try:
        payload = load_payload(args)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_html(payload), encoding="utf-8")

        if args.payload_output:
            payload_output = Path(args.payload_output).expanduser().resolve()
            payload_output.parent.mkdir(parents=True, exist_ok=True)
            payload_output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(output),
                    "chartName": "journey",
                    "mermaid": journey_text(payload),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
