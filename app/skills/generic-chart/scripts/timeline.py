#!/usr/bin/env python3
"""Render a timeline whose left-side date labels align toward the timeline axis."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_ITEMS = [
    {
        "date": "2026-01",
        "title": "项目启动",
        "description": "明确目标、范围与关键里程碑。",
    },
    {
        "date": "2026-03",
        "title": "方案验证",
        "description": "完成核心方案验证并收集反馈。",
    },
    {
        "date": "2026-06",
        "title": "正式发布",
        "description": "完成上线并进入持续迭代阶段。",
    },
]

DEFAULT_PALETTE = [
    {
        "accent": "#2563EB",
        "soft": "#EFF6FF",
        "border": "#BFDBFE",
        "title": "#1E3A8A",
    },
    {
        "accent": "#059669",
        "soft": "#ECFDF5",
        "border": "#A7F3D0",
        "title": "#065F46",
    },
    {
        "accent": "#EA580C",
        "soft": "#FFF7ED",
        "border": "#FED7AA",
        "title": "#9A3412",
    },
    {
        "accent": "#7C3AED",
        "soft": "#F5F3FF",
        "border": "#DDD6FE",
        "title": "#5B21B6",
    },
    {
        "accent": "#DB2777",
        "soft": "#FDF2F8",
        "border": "#FBCFE8",
        "title": "#9D174D",
    },
    {
        "accent": "#0891B2",
        "soft": "#ECFEFF",
        "border": "#A5F3FC",
        "title": "#155E75",
    },
]

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")


def parse_json_or_text(value: str) -> Any:
    """Parse JSON when possible; otherwise preserve plain text."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def has_timeline_rows(value: Any) -> bool:
    """Return whether a payload already contains structured timeline rows."""
    if isinstance(value, list):
        return True
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("items"), list) or isinstance(value.get("events"), list):
        return True
    chart_payload = value.get("chartPayload")
    if isinstance(chart_payload, dict) and (
        isinstance(chart_payload.get("items"), list)
        or isinstance(chart_payload.get("events"), list)
    ):
        return True
    data = value.get("data")
    if isinstance(data, list):
        return True
    return isinstance(data, dict) and (
        isinstance(data.get("items"), list)
        or isinstance(data.get("events"), list)
    )


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Load payload and safely apply CLI overrides."""
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

    if args.data is not None:
        payload["data"] = parse_json_or_text(args.data)

    # Some chart runners append a generic --code value. Only accept it when it
    # contains structured JSON and no valid timeline rows are already present.
    if args.code is not None and not has_timeline_rows(payload):
        parsed_code = parse_json_or_text(args.code)
        if isinstance(parsed_code, (dict, list)):
            payload["data"] = parsed_code

    if args.title is not None:
        payload["title"] = args.title
    return payload


def first_list(mapping: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return None


def timeline_rows(payload: dict[str, Any]) -> list[Any]:
    """Read rows from every location supported by the timeline schema."""
    direct = first_list(payload, ("items", "events"))
    if direct is not None:
        return direct

    chart_payload = payload.get("chartPayload")
    if isinstance(chart_payload, dict):
        nested = first_list(chart_payload, ("items", "events"))
        if nested is not None:
            return nested

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = first_list(data, ("items", "events"))
        if nested is not None:
            return nested
    return []


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_style(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    aliases = {
        "accent": ("accent", "color", "accentColor", "lineColor"),
        "soft": ("soft", "background", "backgroundColor", "fillColor"),
        "border": ("border", "borderColor", "strokeColor"),
        "title": ("title", "titleColor", "textColor"),
    }
    for normalized, keys in aliases.items():
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and HEX_COLOR_RE.match(candidate.strip()):
                result[normalized] = candidate.strip()
                break
    return result


def normalize_item(row: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None

    date = clean_text(
        row.get("date")
        or row.get("time")
        or row.get("period")
        or row.get("year")
    )
    title = clean_text(
        row.get("title")
        or row.get("name")
        or row.get("label")
        or row.get("event")
    )
    description = clean_text(
        row.get("description")
        or row.get("text")
        or row.get("detail")
        or row.get("summary")
        or row.get("content")
    )

    # Required fields are date and title according to the schema. Keep rows
    # with one missing field usable by falling back to the other visible value.
    if not date and not title and not description:
        return None
    if not title:
        title = date or f"事件 {index + 1}"

    color_index_raw = row.get("colorIndex")
    try:
        color_index = int(color_index_raw) if color_index_raw is not None else None
    except (TypeError, ValueError):
        color_index = None

    style = normalize_style(row.get("style"))
    direct_color = row.get("color")
    if isinstance(direct_color, str) and HEX_COLOR_RE.match(direct_color.strip()):
        style.setdefault("accent", direct_color.strip())

    return {
        "date": date,
        "title": title,
        "description": description,
        "colorIndex": color_index,
        "style": style,
        "sourceIndex": index,
    }


def parse_date_key(value: str) -> tuple[int, int, int, int] | None:
    """Parse common timeline date/period strings for stable sorting."""
    text = value.strip()
    if not text:
        return None

    normalized = (
        text.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip(" -")

    quarter_match = re.search(r"(?i)(\d{4})\s*[- ]?Q([1-4])", normalized)
    if not quarter_match:
        quarter_match = re.search(r"(?i)Q([1-4])\s*[- ]?(\d{4})", normalized)
        if quarter_match:
            quarter = int(quarter_match.group(1))
            year = int(quarter_match.group(2))
            return (year, (quarter - 1) * 3 + 1, 1, 0)
    elif quarter_match:
        year = int(quarter_match.group(1))
        quarter = int(quarter_match.group(2))
        return (year, (quarter - 1) * 3 + 1, 1, 0)

    match = re.search(r"(?<!\d)(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?(?!\d)", normalized)
    if match:
        year = int(match.group(1))
        month = int(match.group(2) or 1)
        day = int(match.group(3) or 1)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (year, month, day, 0)

    for fmt in ("%b %Y", "%B %Y", "%d %b %Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return (parsed.year, parsed.month, parsed.day, 0)
        except ValueError:
            continue
    return None


def normalize_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = timeline_rows(payload)
    items = [
        item
        for index, row in enumerate(rows)
        if (item := normalize_item(row, index)) is not None
    ]

    sort_order = clean_text(payload.get("sortOrder") or payload.get("sort") or "asc").lower()
    if sort_order not in {"none", "source", "off"} and items:
        keys = [parse_date_key(item["date"]) for item in items]
        # Only sort when every dated row is safely parseable. This prevents
        # labels such as “早期 / 中期 / 未来” from being rearranged incorrectly.
        if all(key is not None for key in keys):
            reverse = sort_order in {"desc", "descending", "reverse"}
            items = [
                item
                for _, item in sorted(
                    zip(keys, items),
                    key=lambda pair: (pair[0], pair[1]["sourceIndex"]),
                    reverse=reverse,
                )
            ]

    for item in items:
        item.pop("sourceIndex", None)
    return items


def normalized_palette(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_palette = payload.get("palette")
    data = payload.get("data")
    if not isinstance(raw_palette, list) and isinstance(data, dict):
        raw_palette = data.get("palette")

    palette: list[dict[str, str]] = []
    if isinstance(raw_palette, list):
        for raw in raw_palette[:20]:
            if isinstance(raw, str) and HEX_COLOR_RE.match(raw.strip()):
                accent = raw.strip()
                palette.append(
                    {
                        "accent": accent,
                        "soft": "#F8FAFC",
                        "border": "#E2E8F0",
                        "title": accent,
                    }
                )
            elif isinstance(raw, dict):
                style = normalize_style(raw)
                if style.get("accent"):
                    palette.append(
                        {
                            "accent": style.get("accent", "#2563EB"),
                            "soft": style.get("soft", "#F8FAFC"),
                            "border": style.get("border", "#E2E8F0"),
                            "title": style.get("title", style.get("accent", "#1E3A8A")),
                        }
                    )
    return palette or [dict(item) for item in DEFAULT_PALETTE]


def display_config(payload: dict[str, Any]) -> dict[str, Any]:
    color_mode = clean_text(payload.get("colorMode") or "byOrder")
    if color_mode not in {"byOrder", "single", "custom"}:
        color_mode = "byOrder"
    return {
        "palette": normalized_palette(payload),
        "colorMode": color_mode,
        "emptyText": clean_text(payload.get("emptyText") or "暂无时间轴数据"),
    }


def build_html(payload: dict[str, Any]) -> str:
    title = clean_text(payload.get("title") or "时间轴")
    safe_title = html.escape(title)
    items_json = json.dumps(normalize_items(payload), ensure_ascii=False)
    config_json = json.dumps(display_config(payload), ensure_ascii=False)

    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>__TITLE__</title>
<style>
:root{
  --tl-page-bg:transparent;
  --tl-surface:transparent;
  --tl-text:#0F172A;
  --tl-muted:#64748B;
  --tl-line:#2563EB;
  --tl-button-bg:rgba(255,255,255,.94);
  --tl-button-border:rgba(15,23,42,.12);
  --tl-shadow:0 7px 20px rgba(15,23,42,.12);
}
*{box-sizing:border-box}
html,body{
  margin:0;
  width:100%;
  min-height:0;
  background:var(--tl-page-bg);
  color:var(--tl-text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  overflow-x:hidden;
  overflow-y:visible;
}
#container{
  position:relative;
  width:100%;
  height:auto;
  min-height:0;
  overflow:visible;
  background:var(--tl-surface);
}
#title{
  position:relative;
  top:auto;
  left:auto;
  right:auto;
  width:auto;
  margin:0 52px 0 16px;
  padding-top:16px;
  z-index:10;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  font-size:18px;
  line-height:28px;
  font-weight:760;
  letter-spacing:-.01em;
  pointer-events:none;
}
#fullscreenBtn,#exitFullscreenBtn{
  position:absolute;
  z-index:30;
  display:none;
  align-items:center;
  justify-content:center;
  width:26px;
  height:26px;
  padding:0;
  border:1px solid var(--tl-button-border);
  border-radius:7px;
  background:var(--tl-button-bg);
  color:#334155;
  box-shadow:var(--tl-shadow);
  cursor:pointer;
  -webkit-tap-highlight-color:transparent;
}
#fullscreenBtn{right:14px;top:17px}
#exitFullscreenBtn{right:14px;top:14px}
#fullscreenBtn svg,#exitFullscreenBtn svg{
  width:14px;
  height:14px;
  fill:none;
  stroke:currentColor;
  stroke-width:2;
  stroke-linecap:round;
  stroke-linejoin:round;
}
#viewport{
  position:relative;
  inset:auto;
  width:100%;
  padding:8px 0 24px 16px;
  overflow-x:auto;
  overflow-y:hidden;
  overscroll-behavior-x:contain;
  -webkit-overflow-scrolling:touch;
}
#root{
  width:100%;
  min-width:0;
  display:block;
  text-align:left;
}
.timeline{
  --axis-x:88px;
  --gap-x:18px;
  --content-width:560px;
  position:relative;
  width:fit-content;
  min-width:0;
  margin:0;
  padding:4px 0 16px;
  transform:none;
}
.timeline-line{
  position:absolute;
  left:calc(var(--axis-x) + var(--gap-x)/2);
  top:0;
  width:2px;
  height:0;
  border-radius:2px;
  background:#2563EB;
  transform:translateX(-1px);
}
.entry{
  --title-line:21px;
  position:relative;
  display:grid;
  grid-template-columns:var(--axis-x) var(--gap-x) var(--content-width, 560px);
  align-items:start;
  min-height:58px;
  margin:16px 0;
}
.date{
  grid-column:1;
  padding-right:8px;
  color:var(--tl-muted);
  text-align:right;
  font-size:13px;
  line-height:var(--title-line);
  font-weight:600;
  white-space:nowrap;
  overflow:visible;
  text-overflow:clip;
}
.axis{grid-column:2;position:relative;height:100%;min-height:var(--title-line)}
.dot{
  position:absolute;
  left:50%;
  top:calc(var(--title-line)/2);
  width:12px;
  height:12px;
  border:3px solid #2563EB;
  border-radius:50%;
  background:#FFFFFF;
  box-shadow:0 0 0 4px rgba(37,99,235,.10);
  transform:translate(-50%,-50%);
}
.content{
  grid-column:3;
  min-width:0;
  margin-left:8px;
  padding:0;
  border:0;
  border-radius:0;
  background:transparent;
  box-shadow:none;
}
.item-title{
  color:var(--tl-text);
  font-size:14px;
  line-height:var(--title-line);
  font-weight:720;
  overflow-wrap:anywhere;
}
.description{
  margin-top:4px;
  color:#475569;
  font-size:13px;
  line-height:1.6;
  overflow-wrap:anywhere;
  white-space:pre-wrap;
}
.description:empty{display:none}
.empty{
  width:100%;
  margin:8px 0;
  padding:22px;
  border:1px dashed #CBD5E1;
  border-radius:10px;
  color:var(--tl-muted);
  text-align:center;
  font-size:13px;
  background:rgba(248,250,252,.66);
}
@media(max-width:720px){
  #container{height:auto;min-height:0;max-height:none}
  #title{margin:0 46px 0 0;padding-top:10px;font-size:16px;line-height:26px}
  #fullscreenBtn{display:inline-flex;top:10px;right:8px}
  #viewport{inset:auto;padding:6px 0 18px 0}
  .timeline{--axis-x:80px;--gap-x:18px;--content-width:220px}
  .entry{min-height:54px;margin:14px 0}
  .date{padding-right:8px;font-size:12px}
  .content{margin-left:8px;padding:0;width:100%}
  .item-title{font-size:13px}
  .description{font-size:12px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}
  .dot{width:11px;height:11px}
}
@media(max-width:420px){
  .timeline{--axis-x:80px;--gap-x:18px}
  .date{font-size:11px}
}
@media(min-width:721px){#fullscreenBtn{display:none!important}}
body.is-fullscreen{
  width:100vw;
  height:100vh;
  overflow:hidden;
  background:#F8FAFC;
}
body.is-fullscreen #container{
  position:fixed;
  inset:0;
  z-index:9999;
  width:100vw;
  height:100vh;
  min-height:0;
  max-height:none;
  background:#FFFFFF;
}
body.is-fullscreen #title{
  position:absolute;
  top:14px;
  left:0;
  right:52px;
  width:auto;
  margin:0;
  padding:0;
  transform:none;
  font-size:16px;
}
body.is-fullscreen #fullscreenBtn{display:none!important}
body.is-fullscreen #exitFullscreenBtn{display:inline-flex}
body.is-fullscreen #viewport{
  position:absolute;
  inset:52px 0 0;
  width:auto;
  padding:8px 0 24px 0;
  overflow:auto;
}
body.is-fullscreen .timeline{
  width:fit-content;
  margin:0;
  --axis-x:88px;
  --gap-x:18px;
}
body.is-fullscreen.is-forced-landscape #container{
  width:100vh;
  height:100vw;
  left:50%;
  top:50%;
  right:auto;
  bottom:auto;
  transform:translate(-50%,-50%) rotate(90deg);
  transform-origin:center center;
}
</style>
</head>
<body>
<div id="container" data-timeline-container="true">
  <div id="title">__TITLE__</div>
  <button id="fullscreenBtn" type="button" aria-label="横屏全屏浏览" title="横屏全屏浏览">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5"></path><path d="M16 3h5v5"></path><path d="M21 16v5h-5"></path><path d="M3 16v5h5"></path></svg>
  </button>
  <button id="exitFullscreenBtn" type="button" aria-label="退出全屏" title="退出全屏">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3v6H3"></path><path d="M15 3v6h6"></path><path d="M21 15h-6v6"></path><path d="M3 15h6v6"></path></svg>
  </button>
  <div id="viewport"><div id="root"></div></div>
</div>
<script>
const items=__ITEMS__;
const config=__CONFIG__;
const root=document.getElementById("root");
const container=document.getElementById("container");
const viewport=document.getElementById("viewport");
const fullscreenBtn=document.getElementById("fullscreenBtn");
const exitFullscreenBtn=document.getElementById("exitFullscreenBtn");

function safeColor(value,fallback){
  return typeof value==="string"&&/^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value)?value:fallback;
}
function styleForItem(item,index){
  const palette=Array.isArray(config.palette)&&config.palette.length?config.palette:[{}];
  let paletteIndex=0;
  if(config.colorMode!=="single"){
    paletteIndex=Number.isInteger(item.colorIndex)?item.colorIndex:index;
  }
  const base=palette[((paletteIndex%palette.length)+palette.length)%palette.length]||{};
  const override=item&&item.style&&typeof item.style==="object"?item.style:{};
  return {
    accent:safeColor(override.accent,safeColor(base.accent,"#2563EB")),
    soft:safeColor(override.soft,safeColor(base.soft,"#EFF6FF")),
    border:safeColor(override.border,safeColor(base.border,"#BFDBFE")),
    title:safeColor(override.title,safeColor(base.title,"#1E3A8A"))
  };
}
function makeElement(tag,className,text){
  const element=document.createElement(tag);
  if(className) element.className=className;
  if(text!==undefined&&text!==null) element.textContent=String(text);
  return element;
}
function alignTimelineLine(){
  const timeline=root.querySelector(".timeline");
  const line=timeline?timeline.querySelector(".timeline-line"):null;
  const dots=timeline?[...timeline.querySelectorAll(".dot")]:[];
  if(!timeline||!line||!dots.length) return;
  const timelineRect=timeline.getBoundingClientRect();
  const firstRect=dots[0].getBoundingClientRect();
  const lastRect=dots[dots.length-1].getBoundingClientRect();
  const firstCenter=firstRect.top+firstRect.height/2-timelineRect.top;
  const lastCenter=lastRect.top+lastRect.height/2-timelineRect.top;
  line.style.top=`${firstCenter}px`;
  line.style.height=`${Math.max(0,lastCenter-firstCenter)}px`;
}
function intrinsicTextWidth(element){
  if(!element) return 0;
  try{
    const range=document.createRange();
    range.selectNodeContents(element);
    const width=range.getBoundingClientRect().width;
    if(Number.isFinite(width)&&width>0) return Math.ceil(width);
  }catch(e){}
  const text=element.textContent||"";
  const canvas=intrinsicTextWidth.canvas||(intrinsicTextWidth.canvas=document.createElement("canvas"));
  const context=canvas.getContext("2d");
  if(!context) return 0;
  const styles=getComputedStyle(element);
  context.font=`${styles.fontWeight} ${styles.fontSize} ${styles.fontFamily}`;
  return Math.ceil(context.measureText(text).width);
}
function updateTimelineSizing(){
  const timeline=root.querySelector(".timeline");
  if(!timeline||!viewport) return;

  const dates=[...timeline.querySelectorAll(".date")];
  const mobile=viewport.clientWidth<=720;
  if(dates.length){
    // Measure the text itself instead of the grid cell width. Measuring
    // scrollWidth caused a feedback loop where every resize made the date
    // column wider again, producing the large blank area before the axis.
    const widestDate=Math.max(...dates.map(intrinsicTextWidth));
    const axisPadding=mobile?8:10;
    const axisWidth=Math.max(1,widestDate+axisPadding);
    timeline.style.setProperty("--axis-x",`${axisWidth}px`);
  }else{
    timeline.style.removeProperty("--axis-x");
  }

  const styles=getComputedStyle(timeline);
  const axisWidth=parseFloat(styles.getPropertyValue("--axis-x"))||88;
  const gapWidth=parseFloat(styles.getPropertyValue("--gap-x"))||18;
  const contentMargin=8;
  const outerAllowance=mobile?8:16;
  const available=Math.max(160,viewport.clientWidth-axisWidth-gapWidth-contentMargin-outerAllowance);
  timeline.style.setProperty("--content-width",`${available}px`);
}
function renderTimeline(){
  root.replaceChildren();
  if(!Array.isArray(items)||!items.length){
    root.appendChild(makeElement("div","empty",config.emptyText||"暂无时间轴数据"));
    sendTimelineHeight();
    return;
  }
  const timeline=makeElement("div","timeline");
  timeline.appendChild(makeElement("div","timeline-line"));
  items.forEach((item,index)=>{
    const entry=makeElement("article","entry");

    entry.appendChild(makeElement("div","date",item.date||""));
    const axis=makeElement("div","axis");
    axis.appendChild(makeElement("div","dot"));
    entry.appendChild(axis);

    const content=makeElement("div","content");
    content.appendChild(makeElement("div","item-title",item.title||item.date||`事件 ${index+1}`));
    content.appendChild(makeElement("div","description",item.description||""));
    entry.appendChild(content);
    timeline.appendChild(entry);
  });
  root.appendChild(timeline);
  requestAnimationFrame(()=>{
    updateTimelineSizing();
    alignTimelineLine();
    sendTimelineHeight();
  });
}
function sendTimelineHeight(){
  if(document.body.classList.contains("is-fullscreen")) return;
  // The document and body heights are at least as tall as the iframe viewport.
  // Reading them here makes an oversized iframe self perpetuating. The
  // container is height:auto, so its border box is the actual timeline height.
  const rect=container?container.getBoundingClientRect():null;
  const height=Math.ceil(Math.max(rect?rect.height:0,1));
  try{parent.postMessage({type:"analysis-planner-report-height",height},"*");}catch(e){}
}
function updateFullscreenLayout(){
  const active=document.body.classList.contains("is-fullscreen");
  const needsForcedLandscape=active&&window.innerHeight>window.innerWidth;
  document.body.classList.toggle("is-forced-landscape",needsForcedLandscape);
}
function lockLandscape(){
  try{
    const orientation=screen.orientation;
    if(orientation&&typeof orientation.lock==="function") orientation.lock("landscape").catch(()=>{});
  }catch(e){}
}
function unlockOrientation(){
  try{
    const orientation=screen.orientation;
    if(orientation&&typeof orientation.unlock==="function") orientation.unlock();
  }catch(e){}
}
function refreshLayout(){
  updateFullscreenLayout();
  requestAnimationFrame(()=>{
    updateTimelineSizing();
    alignTimelineLine();
    sendTimelineHeight();
  });
}
async function enterFullscreen(){
  document.body.classList.add("is-fullscreen");
  updateFullscreenLayout();
  const target=document.documentElement||document.body;
  try{
    if(target.requestFullscreen) await target.requestFullscreen();
    else if(target.webkitRequestFullscreen) target.webkitRequestFullscreen();
  }catch(e){}
  lockLandscape();
  setTimeout(refreshLayout,80);
  setTimeout(refreshLayout,320);
}
function exitFullscreen(){
  document.body.classList.remove("is-fullscreen","is-forced-landscape");
  unlockOrientation();
  try{
    if(document.fullscreenElement&&document.exitFullscreen) document.exitFullscreen();
    else if(document.webkitFullscreenElement&&document.webkitExitFullscreen) document.webkitExitFullscreen();
  }catch(e){}
  setTimeout(refreshLayout,80);
  setTimeout(refreshLayout,320);
}
fullscreenBtn.addEventListener("click",enterFullscreen);
exitFullscreenBtn.addEventListener("click",exitFullscreen);
document.addEventListener("fullscreenchange",()=>{
  if(!document.fullscreenElement){
    document.body.classList.remove("is-fullscreen","is-forced-landscape");
    unlockOrientation();
    refreshLayout();
  }
});
document.addEventListener("webkitfullscreenchange",()=>{
  if(!document.webkitFullscreenElement){
    document.body.classList.remove("is-fullscreen","is-forced-landscape");
    unlockOrientation();
    refreshLayout();
  }
});
window.addEventListener("resize",refreshLayout);
window.addEventListener("orientationchange",()=>{setTimeout(refreshLayout,120);setTimeout(refreshLayout,420)});
renderTimeline();
setTimeout(refreshLayout,120);
setTimeout(refreshLayout,500);
setTimeout(sendTimelineHeight,900);
if(document.fonts&&document.fonts.ready){
  document.fonts.ready.then(()=>{refreshLayout();sendTimelineHeight();}).catch(()=>{});
}
if("ResizeObserver" in window){
  try{
    const heightObserver=new ResizeObserver(()=>{
      requestAnimationFrame(()=>{
        alignTimelineLine();
        sendTimelineHeight();
      });
    });
    heightObserver.observe(root);
  }catch(e){}
}
</script>
__MOBILE_TOUCH__
</body>
</html>'''

    return (
        template.replace("__TITLE__", safe_title)
        .replace("__ITEMS__", items_json)
        .replace("__CONFIG__", config_json)
        .replace("__MOBILE_TOUCH__", (Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a compact, content-height responsive timeline from items/events JSON."
    )
    parser.add_argument("--code", help="Structured JSON fallback; ignored when payload already contains rows.")
    parser.add_argument("--title")
    parser.add_argument("--payload", help="Path to a JSON payload file.")
    parser.add_argument("--data-json", help="Complete payload encoded as JSON.")
    parser.add_argument("--data", help="Timeline rows or object encoded as JSON.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    args, _ = parser.parse_known_args()

    try:
        payload = load_payload(args)
        items = normalize_items(payload)
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
                    "chartName": "timeline",
                    "itemCount": len(items),
                    "inputMode": (
                        "items"
                        if isinstance(payload.get("items"), list)
                        else "events"
                        if isinstance(payload.get("events"), list)
                        else "data"
                        if has_timeline_rows(payload)
                        else "empty"
                    ),
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
