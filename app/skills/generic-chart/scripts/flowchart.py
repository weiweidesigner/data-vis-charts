#!/usr/bin/env python3
"""Render Mermaid flowcharts from raw Mermaid code or structured nodes/edges JSON."""

from __future__ import annotations

import argparse
import html
import json
import re
import textwrap
from pathlib import Path
from typing import Any

DEFAULT_MERMAID = "flowchart LR\n  start([开始]) --> process[处理] --> end([结束])"
DEFAULT_INVESTMENT_GRAPH = {
    "direction": "LR",
    "nodes": [
        {"id": "goal", "label": "确定投资目标", "type": "terminal"},
        {"id": "screen", "label": "筛选标的池"},
        {"id": "fundamental", "label": "基本面分析"},
        {"id": "valuation", "label": "估值判断"},
        {"id": "technical", "label": "技术面择时"},
        {"id": "risk", "label": "风险与仓位规划"},
        {"id": "execute", "label": "执行交易"},
        {"id": "review", "label": "跟踪复盘", "type": "terminal"},
    ],
    "edges": [
        {"source": "goal", "target": "screen"},
        {"source": "screen", "target": "fundamental"},
        {"source": "fundamental", "target": "valuation"},
        {"source": "valuation", "target": "technical"},
        {"source": "technical", "target": "risk"},
        {"source": "risk", "target": "execute"},
        {"source": "execute", "target": "review"},
    ],
}
DEFAULT_NODE_PALETTE = [
    {"fillColor": "#EFF6FF", "strokeColor": "#60A5FA", "textColor": "#172554"},
    {"fillColor": "#ECFDF5", "strokeColor": "#34D399", "textColor": "#064E3B"},
    {"fillColor": "#FFF7ED", "strokeColor": "#FB923C", "textColor": "#431407"},
    {"fillColor": "#F5F3FF", "strokeColor": "#A78BFA", "textColor": "#2E1065"},
    {"fillColor": "#FDF2F8", "strokeColor": "#F472B6", "textColor": "#500724"},
    {"fillColor": "#F0FDFA", "strokeColor": "#2DD4BF", "textColor": "#134E4A"},
]
DEFAULT_NODE_STYLE = {
    "fillColor": "#F8FAFC",
    "strokeColor": "#94A3B8",
    "textColor": "#0F172A",
    "strokeWidth": 1.5,
}
DEFAULT_TYPE_STYLES = {
    "process": DEFAULT_NODE_PALETTE[0],
    "decision": DEFAULT_NODE_PALETTE[2],
    "terminal": DEFAULT_NODE_PALETTE[1],
    "input": DEFAULT_NODE_PALETTE[3],
    "database": DEFAULT_NODE_PALETTE[4],
    "subroutine": DEFAULT_NODE_STYLE,
}
VALID_COLOR_MODES = {"byOrder", "byType", "custom", "single"}

VALID_DIRECTIONS = {"TB", "TD", "BT", "RL", "LR"}
VALID_THEMES = {"default", "neutral", "dark", "forest", "base"}
VALID_SECURITY_LEVELS = {"strict", "loose", "antiscript", "sandbox"}
VALID_CURVES = {
    "basis",
    "bumpX",
    "bumpY",
    "cardinal",
    "catmullRom",
    "linear",
    "monotoneX",
    "monotoneY",
    "natural",
    "step",
    "stepAfter",
    "stepBefore",
}
MERMAID_PREFIXES = (
    "flowchart ",
    "graph ",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "erdiagram",
    "journey",
    "gantt",
    "pie ",
    "mindmap",
)


def parse_json_or_text(value: str) -> Any:
    """Parse JSON when possible; otherwise preserve the value as plain text."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def looks_like_mermaid(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith(MERMAID_PREFIXES):
        return True
    return "\n" in text and any(token in text for token in ("-->", "---", "-.->", "==>"))


def unwrap_chart_payload(payload: dict[str, Any]) -> dict[str, Any]:
    chart_payload = payload.get("chartPayload")
    if not isinstance(chart_payload, dict):
        return payload
    unwrapped = dict(chart_payload)
    for key in ("title", "direction", "layout", "visualStyle", "theme", "themeMode"):
        if key in payload and key not in unwrapped:
            unwrapped[key] = payload[key]
    return unwrapped


def has_structured_graph(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    value = unwrap_chart_payload(value)
    if isinstance(value.get("nodes"), list) and isinstance(value.get("edges"), list):
        return True
    data = value.get("data")
    return (
        isinstance(data, dict)
        and isinstance(data.get("nodes"), list)
        and isinstance(data.get("edges"), list)
    )


def remove_stale_code_data(payload: dict[str, Any], code: str | None) -> None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    allowed_keys = {"mermaid", "code", "content", "text"}
    if not set(data).issubset(allowed_keys):
        return
    text = first_non_empty(data, ("mermaid", "code", "content", "text"))
    if has_structured_graph(payload) and (code is None or text == str(code).strip()):
        payload.pop("data", None)
    elif text and not looks_like_mermaid(text) and (code is None or text == str(code).strip()):
        payload.pop("data", None)


def apply_title_default_graph(payload: dict[str, Any]) -> None:
    if has_structured_graph(payload) or extract_raw_mermaid(payload):
        return
    title = str(payload.get("title") or "").lower()
    if any(term in title for term in ("投资", "投資", "invest")):
        payload.setdefault("direction", DEFAULT_INVESTMENT_GRAPH["direction"])
        payload["nodes"] = [dict(item) for item in DEFAULT_INVESTMENT_GRAPH["nodes"]]
        payload["edges"] = [dict(item) for item in DEFAULT_INVESTMENT_GRAPH["edges"]]


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Load payload while allowing CLI values to override file values."""
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
    if args.code is not None and not has_structured_graph(payload) and looks_like_mermaid(args.code):
        payload["data"] = {"mermaid": args.code}
    if args.title is not None:
        payload["title"] = args.title
    apply_title_default_graph(payload)
    return payload


def first_non_empty(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_raw_mermaid(payload: dict[str, Any]) -> str | None:
    """Read raw Mermaid syntax from common payload locations."""
    payload = unwrap_chart_payload(payload)
    direct = first_non_empty(payload, ("mermaid", "code", "content", "text"))
    if direct and looks_like_mermaid(direct):
        return direct

    data = payload.get("data")
    if isinstance(data, str) and data.strip() and looks_like_mermaid(data):
        return data.strip()
    if isinstance(data, dict):
        candidate = first_non_empty(data, ("mermaid", "code", "content", "text"))
        return candidate if candidate and looks_like_mermaid(candidate) else None
    return None


def extract_graph(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Accept the schema shape at the top level or inside payload.data."""
    payload = unwrap_chart_payload(payload)
    candidates: list[dict[str, Any]] = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.append(data)

    for candidate in candidates:
        if isinstance(candidate.get("nodes"), list) and isinstance(
            candidate.get("edges"), list
        ):
            return candidate
    return None


def clean_mermaid_id(raw_id: Any, index: int, used: set[str]) -> str:
    """Create a stable Mermaid-safe identifier while preserving edge mapping."""
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", str(raw_id).strip())
    candidate = re.sub(r"_+", "_", candidate).strip("_") or f"node_{index + 1}"
    if candidate[0].isdigit():
        candidate = f"node_{candidate}"

    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def wrap_label(value: Any, max_chars: int) -> str:
    """Wrap long labels without changing their semantic content."""
    text = str(value).strip()
    if max_chars <= 0:
        return text

    wrapped_lines: list[str] = []
    for source_line in text.splitlines() or [text]:
        if len(source_line) <= max_chars:
            wrapped_lines.append(source_line)
            continue
        if " " in source_line:
            wrapped_lines.extend(
                textwrap.wrap(
                    source_line,
                    width=max_chars,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            )
        else:
            wrapped_lines.extend(
                source_line[i : i + max_chars]
                for i in range(0, len(source_line), max_chars)
            )
    return "\n".join(wrapped_lines)


def escape_label(value: Any, max_chars: int = 18) -> str:
    wrapped = wrap_label(value, max_chars)
    return html.escape(wrapped, quote=True).replace("\n", "<br/>")


def normalize_node_type(node: dict[str, Any]) -> str:
    explicit = str(node.get("type") or node.get("shape") or "").strip().lower()
    aliases = {
        "process": "process",
        "step": "process",
        "rect": "process",
        "rectangle": "process",
        "decision": "decision",
        "condition": "decision",
        "diamond": "decision",
        "start": "terminal",
        "end": "terminal",
        "terminal": "terminal",
        "round": "terminal",
        "input": "input",
        "output": "input",
        "io": "input",
        "data": "database",
        "database": "database",
        "cylinder": "database",
        "subroutine": "subroutine",
        "subprocess": "subroutine",
    }
    if explicit in aliases:
        return aliases[explicit]

    label = str(node.get("label") or "").strip()
    raw_id = str(node.get("id") or "").strip().lower()
    if raw_id in {"start", "begin", "end", "finish"} or label.lower() in {
        "start",
        "begin",
        "end",
        "finish",
        "开始",
        "结束",
    }:
        return "terminal"
    if label.startswith("是否") or label.endswith(("?", "？")):
        return "decision"
    return "process"


def node_expression(node_id: str, label: str, node_type: str) -> str:
    shapes = {
        "process": f'{node_id}["{label}"]',
        "decision": f'{node_id}{{"{label}"}}',
        "terminal": f'{node_id}(["{label}"])',
        "input": f'{node_id}[/"{label}"/]',
        "database": f'{node_id}[("{label}")]',
        "subroutine": f'{node_id}[["{label}"]]',
    }
    return shapes.get(node_type, shapes["process"])



def source_value(graph: dict[str, Any], payload: dict[str, Any], key: str, default: Any = None) -> Any:
    """Read a graph-level option first, then fall back to the payload."""
    if key in graph:
        return graph.get(key)
    return payload.get(key, default)


def safe_css_color(value: Any, fallback: str) -> str:
    """Allow common CSS color forms while blocking Mermaid style injection."""
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


def normalize_visual_style(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "fillColor": safe_css_color(source.get("fillColor"), str(fallback["fillColor"])),
        "strokeColor": safe_css_color(source.get("strokeColor"), str(fallback["strokeColor"])),
        "textColor": safe_css_color(source.get("textColor"), str(fallback["textColor"])),
        "strokeWidth": safe_positive_number(source.get("strokeWidth"), float(fallback.get("strokeWidth", 1.5))),
    }


def resolve_palette(graph: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_palette = source_value(graph, payload, "palette", DEFAULT_NODE_PALETTE)
    palette: list[dict[str, Any]] = []
    if isinstance(raw_palette, list):
        for item in raw_palette:
            if isinstance(item, dict):
                palette.append(normalize_visual_style(item, DEFAULT_NODE_STYLE))
    return palette or [normalize_visual_style(item, DEFAULT_NODE_STYLE) for item in DEFAULT_NODE_PALETTE]


def resolve_named_styles(graph: dict[str, Any], payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    named = {
        name: normalize_visual_style(style, DEFAULT_NODE_STYLE)
        for name, style in DEFAULT_TYPE_STYLES.items()
    }
    custom = source_value(graph, payload, "nodeStyles", {})
    if isinstance(custom, dict):
        for name, style in custom.items():
            if isinstance(style, dict):
                named[str(name)] = normalize_visual_style(style, named.get(str(name), DEFAULT_NODE_STYLE))
    return named


def resolve_node_style(
    node: dict[str, Any],
    node_type: str,
    index: int,
    graph: dict[str, Any],
    payload: dict[str, Any],
    palette: list[dict[str, Any]],
    named_styles: dict[str, dict[str, Any]],
    default_style: dict[str, Any],
) -> dict[str, Any]:
    color_mode = str(source_value(graph, payload, "colorMode", "byOrder"))
    if color_mode not in VALID_COLOR_MODES:
        color_mode = "byOrder"

    if color_mode == "single":
        base = dict(default_style)
    elif color_mode == "byType":
        base = dict(named_styles.get(node_type, default_style))
    else:
        color_index_raw = node.get("colorIndex", index)
        try:
            color_index = int(color_index_raw)
        except (TypeError, ValueError):
            color_index = index
        base = dict(palette[color_index % len(palette)])

    color_key = str(node.get("colorKey") or "").strip()
    if color_key and color_key in named_styles:
        base = dict(named_styles[color_key])

    node_style = node.get("style")
    if isinstance(node_style, dict):
        merged = dict(base)
        merged.update(node_style)
        base = normalize_visual_style(merged, base)
    else:
        base = normalize_visual_style(base, default_style)
    return base


def mermaid_node_style(style: dict[str, Any]) -> str:
    width = f"{style['strokeWidth']:g}px"
    return (
        f"fill:{style['fillColor']},"
        f"stroke:{style['strokeColor']},"
        f"color:{style['textColor']},"
        f"stroke-width:{width}"
    )


def mermaid_edge_style(style: Any) -> str | None:
    if not isinstance(style, dict):
        return None
    declarations: list[str] = []
    if style.get("lineColor"):
        declarations.append(f"stroke:{safe_css_color(style.get('lineColor'), '#64748B')}")
    if style.get("labelColor"):
        declarations.append(f"color:{safe_css_color(style.get('labelColor'), '#334155')}")
    if style.get("lineWidth") is not None:
        declarations.append(f"stroke-width:{safe_positive_number(style.get('lineWidth'), 1.5):g}px")
    dash = str(style.get("dash") or "solid").lower()
    if dash == "dashed":
        declarations.append("stroke-dasharray:7 5")
    elif dash == "dotted":
        declarations.append("stroke-dasharray:2 4")
    return ",".join(declarations) or None


def graph_to_mermaid(graph: dict[str, Any], payload: dict[str, Any]) -> str:
    """Convert structured nodes/edges into Mermaid with configurable colors."""
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Structured flowchart data requires nodes[] and edges[].")
    if not nodes:
        raise ValueError("nodes[] cannot be empty.")

    direction = str(graph.get("direction") or payload.get("direction") or "LR").upper()
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Unsupported direction: {direction}")

    max_label_chars_raw = graph.get("maxLabelChars", payload.get("maxLabelChars", 18))
    try:
        max_label_chars = max(0, int(max_label_chars_raw))
    except (TypeError, ValueError):
        max_label_chars = 18

    palette = resolve_palette(graph, payload)
    named_styles = resolve_named_styles(graph, payload)
    default_style = normalize_visual_style(
        source_value(graph, payload, "defaultNodeStyle", DEFAULT_NODE_STYLE),
        DEFAULT_NODE_STYLE,
    )

    used_mermaid_ids: set[str] = set()
    id_map: dict[str, str] = {}
    node_lines: list[str] = []
    node_class_lines: list[str] = []
    class_definition_lines: list[str] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"nodes[{index}] must be an object.")
        if "id" not in node or str(node.get("id")).strip() == "":
            raise ValueError(f"nodes[{index}].id is required.")
        if "label" not in node or str(node.get("label")).strip() == "":
            raise ValueError(f"nodes[{index}].label is required.")

        source_id = str(node["id"])
        if source_id in id_map:
            raise ValueError(f"Duplicate node id: {source_id}")

        mermaid_id = clean_mermaid_id(source_id, index, used_mermaid_ids)
        id_map[source_id] = mermaid_id
        node_type = normalize_node_type(node)
        node_lines.append(
            "  " + node_expression(
                mermaid_id,
                escape_label(node["label"], max_label_chars),
                node_type,
            )
        )

        style = resolve_node_style(
            node,
            node_type,
            index,
            graph,
            payload,
            palette,
            named_styles,
            default_style,
        )
        class_name = f"nodeStyle{index + 1}"
        node_class_lines.append(f"  class {mermaid_id} {class_name}")
        class_definition_lines.append(f"  classDef {class_name} {mermaid_node_style(style)}")

    edge_lines: list[str] = []
    edge_style_lines: list[str] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"edges[{index}] must be an object.")
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in id_map:
            raise ValueError(f"edges[{index}].source references unknown node: {source}")
        if target not in id_map:
            raise ValueError(f"edges[{index}].target references unknown node: {target}")

        label = str(edge.get("label") or "").strip()
        if label:
            safe_edge_label = escape_label(label, max_chars=24).replace("|", "&#124;")
            edge_lines.append(f"  {id_map[source]} -->|{safe_edge_label}| {id_map[target]}")
        else:
            edge_lines.append(f"  {id_map[source]} --> {id_map[target]}")

        edge_style = mermaid_edge_style(edge.get("style"))
        if edge_style:
            edge_style_lines.append(f"  linkStyle {index} {edge_style}")

    return "\n".join([
        f"flowchart {direction}",
        *node_lines,
        *edge_lines,
        *node_class_lines,
        *class_definition_lines,
        *edge_style_lines,
    ])

def flow_text(payload: dict[str, Any]) -> str:
    """Prefer explicit Mermaid code; otherwise compile structured graph JSON."""
    direct_mermaid = first_non_empty(payload, ("mermaid", "code", "content", "text"))
    if direct_mermaid and looks_like_mermaid(direct_mermaid):
        return direct_mermaid

    graph = extract_graph(payload)
    if graph:
        return graph_to_mermaid(graph, payload)

    raw_mermaid = extract_raw_mermaid(payload)
    if raw_mermaid:
        return raw_mermaid
    return DEFAULT_MERMAID


def mermaid_config(payload: dict[str, Any]) -> dict[str, Any]:
    theme = str(payload.get("theme") or "base")
    if theme not in VALID_THEMES:
        theme = "base"

    security_level = str(payload.get("securityLevel") or "strict")
    if security_level not in VALID_SECURITY_LEVELS:
        security_level = "strict"

    curve = str(payload.get("curve") or "basis")
    if curve not in VALID_CURVES:
        curve = "basis"

    default_theme_variables = {
        "fontFamily": '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif',
        "fontSize": "15px",
        "primaryColor": "#EFF6FF",
        "primaryTextColor": "#0F172A",
        "primaryBorderColor": "#60A5FA",
        "lineColor": "#64748B",
        "tertiaryColor": "#F8FAFC",
        "clusterBkg": "#F8FAFC",
        "clusterBorder": "#CBD5E1",
        "edgeLabelBackground": "transparent",
    }
    custom_theme_variables = payload.get("themeVariables")
    if isinstance(custom_theme_variables, dict):
        default_theme_variables.update(custom_theme_variables)

    return {
        "startOnLoad": False,
        "theme": theme,
        "securityLevel": security_level,
        "themeVariables": default_theme_variables,
        "flowchart": {
            "htmlLabels": True,
            "useMaxWidth": False,
            "curve": curve,
            "nodeSpacing": 44,
            "rankSpacing": 58,
            "padding": 14,
        },
    }


def build_html(payload: dict[str, Any]) -> str:
    title = str(payload.get("title") or "流程图")
    safe_title = html.escape(title)
    mermaid_code = flow_text(payload)
    code_json = json.dumps(mermaid_code, ensure_ascii=False)
    config_json = json.dumps(mermaid_config(payload), ensure_ascii=False)
    raw_color_mode = str(payload.get("colorMode") or "byOrder")
    auto_color_raw = (
        extract_graph(payload) is None
        and raw_color_mode == "byOrder"
        and not re.search(r"(?im)^\s*(?:classDef|style)\s+", mermaid_code)
    )
    palette_json = json.dumps(resolve_palette({}, payload), ensure_ascii=False)
    auto_color_raw_json = json.dumps(auto_color_raw)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>{safe_title}</title>
<style>
:root{{--text:#0F172A;--fullscreen-bg:#FFFFFF}}
*{{box-sizing:border-box}}
html,body{{
  margin:0;
  width:100%;
  height:100%;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:transparent!important;
  color:var(--text);
  overflow:hidden;
}}
#wrap{{
  position:relative;
  width:100%;
  height:100vh;
  overflow:hidden;
  background:transparent;
}}
#title{{
  position:absolute;
  left:16px;
  right:16px;
  top:14px;
  z-index:10;
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
  position:absolute;
  inset:0;
  overflow:auto;
  background:transparent;
}}
#diagram{{
  display:flex;
  align-items:flex-start;
  justify-content:center;
  min-width:100%;
  min-height:100%;
  padding:60px 32px 32px;
  background:transparent;
}}
#diagram svg{{
  display:block;
  max-width:none!important;
  height:auto!important;
  background:transparent!important;
}}
#diagram .edgeLabel{{background-color:transparent!important}}
#diagram .labelBkg{{fill:transparent!important}}
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
  background:rgba(255,255,255,.92);
  color:#334155;
  box-shadow:0 6px 18px rgba(15,23,42,.10);
  cursor:pointer;
  -webkit-tap-highlight-color:transparent;
}}
#fullscreenBtn{{right:14px;top:15px}}
#exitFullscreenBtn{{right:max(14px,env(safe-area-inset-right));top:max(14px,env(safe-area-inset-top));display:none}}
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
body.is-fullscreen #fullscreenBtn{{display:none}}
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
#error{{
  display:none;
  position:absolute;
  left:20px;
  right:20px;
  bottom:20px;
  padding:12px 14px;
  border:1px solid #FCA5A5;
  border-radius:10px;
  background:transparent;
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
@media (max-width:720px){{
  #title{{left:12px;right:52px;top:10px;font-size:16px}}
  #fullscreenBtn{{display:inline-flex;right:12px;top:10px}}
  #diagram{{padding:54px 18px 24px}}
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
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
const code = {code_json};
const config = {config_json};
const nodePalette = {palette_json};
const autoColorRawNodes = {auto_color_raw_json};
const diagram = document.getElementById("diagram");
const viewport = document.getElementById("viewport");
const errorBox = document.getElementById("error");
const sourceBox = document.getElementById("source");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const exitFullscreenBtn = document.getElementById("exitFullscreenBtn");
let svg = null;
let naturalWidth = 0;

function moveEdgeLabelsAboveLine() {{
  if (!svg) return;
  const edgeLabelOffset = window.innerWidth <= 720 ? 10 : 12;
  svg.querySelectorAll("g.edgeLabel").forEach((label) => {{
    if (label.dataset.shiftedAboveLine === "true") return;
    const transform = label.getAttribute("transform") || "";
    const match = transform.match(/translate\\(([-+0-9.eE]+)[ ,]+([-+0-9.eE]+)\\)/);
    if (!match) return;
    const x = Number.parseFloat(match[1]);
    const y = Number.parseFloat(match[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    label.setAttribute(
      "transform",
      transform.replace(
        /translate\\(([-+0-9.eE]+)[ ,]+([-+0-9.eE]+)\\)/,
        `translate(${{x}},${{y - edgeLabelOffset}})`
      )
    );
    label.dataset.shiftedAboveLine = "true";
  }});
}}

function applyRawNodePalette() {{
  if (!svg || !autoColorRawNodes || !Array.isArray(nodePalette) || !nodePalette.length) return;
  svg.querySelectorAll("g.node").forEach((node, index) => {{
    const style = nodePalette[index % nodePalette.length] || {{}};
    node.querySelectorAll("rect,polygon,path,circle,ellipse").forEach((shape) => {{
      if (style.fillColor) shape.style.fill = style.fillColor;
      if (style.strokeColor) shape.style.stroke = style.strokeColor;
      if (style.strokeWidth) shape.style.strokeWidth = `${{style.strokeWidth}}px`;
    }});
    node.querySelectorAll("text,tspan").forEach((textNode) => {{
      if (style.textColor) textNode.style.fill = style.textColor;
    }});
    node.querySelectorAll("foreignObject div,foreignObject span,foreignObject p").forEach((htmlNode) => {{
      if (style.textColor) htmlNode.style.color = style.textColor;
    }});
  }});
}}

function fitDiagram() {{
  if (!svg || !naturalWidth) return;
  const isFullscreen = document.body.classList.contains("is-fullscreen");
  const horizontalPadding = isFullscreen ? 56 : (window.innerWidth <= 640 ? 36 : 64);
  const availableWidth = Math.max(240, viewport.clientWidth - horizontalPadding);
  const viewBox = svg.viewBox && svg.viewBox.baseVal;
  const naturalHeight = viewBox && viewBox.height
    ? viewBox.height
    : svg.getBoundingClientRect().height;
  const verticalPadding = isFullscreen ? 78 : 92;
  const availableHeight = Math.max(160, viewport.clientHeight - verticalPadding);
  const widthScale = availableWidth / naturalWidth;
  const heightScale = naturalHeight > 0 ? availableHeight / naturalHeight : 1;
  const scale = isFullscreen
    ? Math.max(0.1, Math.min(widthScale, heightScale))
    : Math.min(1, widthScale);
  svg.style.width = `${{Math.round(naturalWidth * scale)}}px`;
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
  requestAnimationFrame(fitDiagram);
  setTimeout(fitDiagram, 80);
  setTimeout(fitDiagram, 320);
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
    const result = await mermaid.render("flowchartSvg", code);
    diagram.innerHTML = result.svg;
    if (typeof result.bindFunctions === "function") result.bindFunctions(diagram);

    svg = diagram.querySelector("svg");
    if (!svg) throw new Error("Mermaid did not return an SVG element.");

    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    naturalWidth = viewBox && viewBox.width
      ? viewBox.width
      : svg.getBoundingClientRect().width;

    svg.removeAttribute("height");
    svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
    applyRawNodePalette();
    moveEdgeLabelsAboveLine();
    refitDiagram();
  }} catch (err) {{
    errorBox.style.display = "block";
    errorBox.textContent = `流程图渲染失败：${{String(err?.message || err)}}`;
    diagram.style.display = "none";
    sourceBox.style.display = "block";
    sourceBox.textContent = code;
  }}
}})();

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
        description="Render a Mermaid flowchart from raw code or nodes/edges JSON."
    )
    parser.add_argument("--code", help="Raw Mermaid syntax; overrides payload data.")
    parser.add_argument("--title")
    parser.add_argument("--payload", help="Path to a JSON payload file.")
    parser.add_argument("--data-json", help="Complete payload encoded as JSON.")
    parser.add_argument("--data", help="JSON data or raw Mermaid syntax.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    args, _ = parser.parse_known_args()

    try:
        payload = load_payload(args)
        mermaid_code = flow_text(payload)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_html(payload), encoding="utf-8")

        if args.payload_output:
            payload_output = Path(args.payload_output).expanduser().resolve()
            payload_output.parent.mkdir(parents=True, exist_ok=True)
            payload_output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(output),
                    "chartName": "flowchart",
                    "inputMode": (
                        "mermaid"
                        if first_non_empty(payload, ("mermaid", "code", "content", "text"))
                        else "nodes-edges"
                        if extract_graph(payload)
                        else "mermaid"
                        if extract_raw_mermaid(payload)
                        else "default"
                    ),
                    "mermaid": mermaid_code,
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
