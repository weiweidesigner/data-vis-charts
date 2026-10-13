#!/usr/bin/env python3
"""Render the project dynamic_line chart from generic data.

Yahoo and other data tools should only produce rows/payloads. This script owns
the dynamic_line visual style and delegates the chart runtime to the bundled
Aime dynamic line renderer.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AIME_RENDERER = Path(__file__).resolve().parents[1] / "runtime/scripts/render_aime_chart.py"
STATIC_ECHARTS = '<script src="/static/vendor/echarts.min.js"></script>'
CDN_ECHARTS = '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
ECHARTS_FALLBACK = (
    f"{STATIC_ECHARTS}\n"
    "<script>window.echarts||document.write('<script src=\"https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js\"><\\/script>')</script>"
)


def parse_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def first_rows(data: Any) -> list[dict[str, Any]]:
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def is_number(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        float(str(value).replace(",", ""))
        return True
    except ValueError:
        return False


def number_or_none(value: Any) -> float | None:
    if not is_number(value):
        return None
    num = float(str(value).replace(",", ""))
    return num if math.isfinite(num) else None


def normalize_theme(value: Any = None) -> str:
    text = str(value or "").strip().lower()
    if text in {"dark", "night", "black", "暗夜", "暗色", "深色", "黑夜"}:
        return "dark"
    return "light"


def infer_encode(payload: dict[str, Any]) -> dict[str, str]:
    encode = payload.get("encode") if isinstance(payload.get("encode"), dict) else {}
    rows = first_rows(payload.get("data"))
    keys = list(rows[0].keys()) if rows else []
    lower = {key.lower(): key for key in keys}
    x_key = encode.get("x") or lower.get("date") or lower.get("time") or lower.get("datetime") or lower.get("month")
    y_key = encode.get("y") or lower.get("value") or lower.get("amount") or lower.get("price") or lower.get("count")
    series_key = encode.get("series") or lower.get("series") or lower.get("symbol") or lower.get("name")
    if not x_key and keys:
        x_key = next((key for key in keys if not is_number(rows[0].get(key))), keys[0])
    if not y_key and keys:
        y_key = next((key for key in keys if key != x_key and is_number(rows[0].get(key))), keys[-1])
    if not series_key:
        series_key = "__series"
        for row in rows:
            row.setdefault(series_key, payload.get("title") or "Series")
    return {"x": str(x_key or "date"), "y": str(y_key or "value"), "series": str(series_key)}


def normalize_payload(raw: Any, args: argparse.Namespace) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("chartPayload"), dict):
        payload = dict(raw["chartPayload"])
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        payload = {"data": raw}

    if args.data:
        payload["data"] = parse_json(args.data)
    if args.title:
        payload["title"] = args.title
    if args.theme:
        payload["theme"] = normalize_theme(args.theme)

    payload["chartName"] = "dynamic_line"
    payload.setdefault("title", "动态折线图")
    payload["theme"] = normalize_theme(payload.get("theme") or "light")
    payload.setdefault("unit", "")
    payload["encode"] = infer_encode(payload)
    if not first_rows(payload.get("data")):
        raise SystemExit("dynamic_line requires data rows. Pass --data-json, --data, or --payload with a data array.")
    return payload


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload:
        raw = json.loads(Path(args.payload).expanduser().read_text(encoding="utf-8"))
    elif args.data_json:
        raw = parse_json(args.data_json)
    else:
        raw = {}
    return normalize_payload(raw, args)


def render_aime_dynamic_line(payload: dict[str, Any], output: Path) -> None:
    if not AIME_RENDERER.exists():
        raise SystemExit(f"Aime renderer not found: {AIME_RENDERER}")
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        payload_path = Path(tmp.name)
    try:
        cmd = [sys.executable, str(AIME_RENDERER), "--payload", str(payload_path), "--output", str(output)]
        result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
        if result.returncode != 0:
            raise SystemExit((result.stderr or result.stdout or "Aime dynamic_line render failed").strip())
    finally:
        try:
            payload_path.unlink()
        except FileNotFoundError:
            pass


def materialize_fast_series(payload: dict[str, Any], output: Path) -> None:
    rows = first_rows(payload.get("data"))
    encode = payload["encode"]
    x_key = encode["x"]
    y_key = encode["y"]
    series_key = encode["series"]

    series_list: list[str] = []
    x_list: list[str] = []
    values: dict[tuple[str, str], float | None] = {}
    for row in rows:
        series = str(row.get(series_key) or "")
        x_value = str(row.get(x_key) or "")
        if not series or not x_value:
            continue
        if series not in series_list:
            series_list.append(series)
        if x_value not in x_list:
            x_list.append(x_value)
        values[(series, x_value)] = number_or_none(row.get(y_key))

    if not series_list or not x_list:
        return

    full_series = {
        series: [values.get((series, x_value)) for x_value in x_list]
        for series in series_list
    }
    document = output.read_text(encoding="utf-8")
    document = re.sub(
        r"const rows = .*?;\n\s*const seriesList = .*?;\n\s*const xList = .*?;\n\s*const bgmDataUri = .*?;\n\s*const bgmFilename = .*?;",
        (
            "const rows = [];\n"
            f"    const seriesList = {json.dumps(series_list, ensure_ascii=False, separators=(',', ':'))};\n"
            f"    const xList = {json.dumps(x_list, ensure_ascii=False, separators=(',', ':'))};\n"
            "    const bgmDataUri = \"\";\n"
            "    const bgmFilename = \"\";"
        ),
        document,
        flags=re.S,
        count=1,
    )
    document = re.sub(
        r"const fullSeriesDataMap = \{\};\n\s*seriesList\.forEach\(\(seriesName\) => \{\n\s*fullSeriesDataMap\[seriesName\] = xList\.map\(\(xValue\) => \{\n\s*const found = rows\.find\(row => row\[seriesKey\] === seriesName && row\[xKey\] === xValue\);\n\s*return found \? rowValueToNumber\(found\[yKey\]\) : null;\n\s*\}\);\n\s*\}\);",
        f"const fullSeriesDataMap = {json.dumps(full_series, ensure_ascii=False, separators=(',', ':'))};",
        document,
        flags=re.S,
        count=1,
    )
    output.write_text(document, encoding="utf-8")


def replace_script_loader(document: str) -> str:
    return document.replace(CDN_ECHARTS, ECHARTS_FALLBACK)


def apply_shared_interaction_style(document: str) -> str:
    replacements = {
        "const speedPresets = [\n      { label: '0.5x', interval: 1200 },\n      { label: '1x', interval: 700 },\n      { label: '2x', interval: 350 }\n    ];": "const speedPresets = [\n      { label: '1x', interval: 700 },\n      { label: '2x', interval: 350 },\n      { label: '3x', interval: 230 }\n    ];",
        "let timer = null;\n    let isPlaying = false;": "let timer = null;\n    let isPlaying = false;\n    let lastFrameAt = 0;\n    let frameAccumulator = 0;",
        "speedPresetIndex = 1;": "speedPresetIndex = 1;",
        "connectNulls: false,": "connectNulls: true,",
        "lineStyle: {\n            width: isCompactLayout() ? 3.5 : 4,": "lineStyle: {\n            width: isCompactLayout() ? 2.4 : 2.8,",
        "symbolSize: 6,": "symbolSize: 5,",
        "symbolSize: 8,": "symbolSize: isCompactLayout() ? 7 : 8,",
        "itemStyle: { color: theme.line, borderWidth: 0 },\n            label: { show: false },": "itemStyle: { color: theme.line, borderWidth: 0 },\n            label: { show: false },",
        "splitNumber: 5,": "splitNumber: 4,",
        "type: 'dashed',": "type: 'solid',",
        "animation: true,": "animation: isPlaying,",
        "animationDuration: animDuration,": "animationDuration: animDuration,",
        "animationDurationUpdate: animDuration,": "animationDurationUpdate: animDuration,",
    }
    for old, new in replacements.items():
        document = document.replace(old, new)

    document = document.replace(
        "function formatValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      return `${value}${unit}`;\n"
        "    }",
        "function numberLocale() {\n"
        "      const localeText = [title, unit, xKey, yKey, seriesKey, ...seriesList].filter(Boolean).join(' ');\n"
        "      if (/[\\u4e00-\\u9fff]/.test(localeText)) return 'zh-CN';\n"
        "      if (/[\\u3040-\\u30ff]/.test(localeText)) return 'ja-JP';\n"
        "      if (/[\\uac00-\\ud7af]/.test(localeText)) return 'ko-KR';\n"
        "      return 'en-US';\n"
        "    }\n\n"
        "    function trimCompactZeros(text) {\n"
        "      return String(text).replace(/\\.0+$/, '').replace(/(\\.\\d*?)0+$/, '$1');\n"
        "    }\n\n"
        "    function compactNumber(value) {\n"
        "      const num = Number(value);\n"
        "      if (!Number.isFinite(num)) return String(value ?? '-');\n"
        "      const locale = numberLocale();\n"
        "      const abs = Math.abs(num);\n"
        "      let scaled = num;\n"
        "      let compactUnit = '';\n"
        "      const cjkUnits = locale === 'ja-JP'\n"
        "        ? [['兆', 1e12], ['億', 1e8], ['万', 1e4]]\n"
        "        : locale === 'ko-KR'\n"
        "          ? [['조', 1e12], ['억', 1e8], ['만', 1e4]]\n"
        "          : locale === 'zh-CN'\n"
        "            ? [['万亿', 1e12], ['亿', 1e8], ['万', 1e4]]\n"
        "            : null;\n"
        "      if (cjkUnits) {\n"
        "        const matched = cjkUnits.find(([, threshold]) => abs >= threshold);\n"
        "        if (matched) {\n"
        "          compactUnit = matched[0];\n"
        "          scaled = num / matched[1];\n"
        "        }\n"
        "      } else if (abs >= 1e4) {\n"
        "        if (abs >= 1e12) { scaled = num / 1e12; compactUnit = 'T'; }\n"
        "        else if (abs >= 1e9) { scaled = num / 1e9; compactUnit = 'B'; }\n"
        "        else if (abs >= 1e6) { scaled = num / 1e6; compactUnit = 'M'; }\n"
        "        else { scaled = num / 1e3; compactUnit = 'K'; }\n"
        "      }\n"
        "      const digits = Math.abs(scaled) >= 100 ? 0 : Math.abs(scaled) >= 10 ? 1 : 2;\n"
        "      const fixed = trimCompactZeros(scaled.toFixed(digits));\n"
        "      return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(Number(fixed)) + compactUnit;\n"
        "    }\n\n"
        "    function formatValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      return `${compactNumber(value)}${unit}`;\n"
        "    }\n\n"
        "    function formatPlainValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      return compactNumber(value);\n"
        "    }",
    )

    document = document.replace(
        "function formatValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      const num = Number(value);\n"
        "      if (Number.isFinite(num)) return `${num.toFixed(2)}${unit}`;\n"
        "      return `${value}${unit}`;\n"
        "    }\n\n"
        "    function formatPlainValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      const num = Number(value);\n"
        "      if (Number.isFinite(num)) return num.toFixed(2);\n"
        "      return String(value);\n"
        "    }",
        "function formatValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      return `${compactNumber(value)}${unit}`;\n"
        "    }\n\n"
        "    function formatPlainValue(value) {\n"
        "      if (value === null || value === undefined || value === '') return '-';\n"
        "      return compactNumber(value);\n"
        "    }",
    )

    document = document.replace(
        "function stopTimer() {\n      if (timer) {\n        clearInterval(timer);\n        timer = null;\n      }\n    }",
        "function stopTimer() {\n      if (timer) {\n        cancelAnimationFrame(timer);\n        timer = null;\n      }\n      lastFrameAt = 0;\n      frameAccumulator = 0;\n    }",
    )
    document = document.replace(
        "function startTimer() {\n      stopTimer();\n      timer = setInterval(() => {\n        if (currentIndex >= xList.length - 1) {\n          currentIndex = xList.length - 1;\n          isPlaying = false;\n          setPlayButtonState();\n          stopTimer();\n          stopBackgroundMusic(true);\n          renderChart();\n          return;\n        }\n        currentIndex += 1;\n        renderChart();\n      }, currentInterval);\n    }",
        "function startTimer() {\n      stopTimer();\n      const tick = (timestamp) => {\n        if (!isPlaying) return;\n        if (!lastFrameAt) lastFrameAt = timestamp;\n        const delta = Math.min(timestamp - lastFrameAt, currentInterval * 1.5);\n        lastFrameAt = timestamp;\n        frameAccumulator += delta;\n        if (frameAccumulator >= currentInterval) {\n          const steps = Math.max(1, Math.floor(frameAccumulator / currentInterval));\n          frameAccumulator = frameAccumulator % currentInterval;\n          currentIndex = Math.min(currentIndex + steps, xList.length - 1);\n          renderChart();\n          if (currentIndex >= xList.length - 1) {\n            currentIndex = xList.length - 1;\n            isPlaying = false;\n            setPlayButtonState();\n            stopBackgroundMusic(true);\n            renderChart();\n            stopTimer();\n            return;\n          }\n        }\n        timer = requestAnimationFrame(tick);\n      };\n      timer = requestAnimationFrame(tick);\n    }",
    )
    document = document.replace(
        "setTimeLabel(startLabel, xList[0] || '');",
        "setTimeLabel(startLabel, xList.length ? xList[0] : '');",
    )
    document = document.replace(
        "setTimeLabel(endLabel, xList[xList.length - 1] || '');",
        "setTimeLabel(endLabel, xList.length ? xList[xList.length - 1] : '');",
    )
    document = document.replace(
        "playBtn.textContent = isPlaying ? '❚❚' : '▶';",
        "playBtn.classList.toggle('is-playing', isPlaying);\n      playBtn.textContent = '';",
    )
    return document


def apply_layout_and_labels(document: str, *, dark: bool) -> str:
    if dark:
        text = "#f8fafc"
        muted = "#a7b5c9"
        grid = "rgba(148, 163, 184, 0.16)"
        axis = "rgba(148, 163, 184, 0.18)"
        wrap_bg = "transparent"
        player_bg = "transparent"
        player_border = "transparent"
        input_bg = "transparent"
        center_fill = "rgba(148,163,184,.16)"
    else:
        text = "#151922"
        muted = "#687386"
        grid = "rgba(104, 115, 134, 0.13)"
        axis = "rgba(104, 115, 134, 0.12)"
        wrap_bg = "transparent"
        player_bg = "transparent"
        player_border = "transparent"
        input_bg = "transparent"
        center_fill = "rgba(104,115,134,.13)"

    css = f"""
  <style id="projectDynamicLineStyle">
    html, body {{
      height: auto !important;
      min-height: 0 !important;
      background: {input_bg} !important;
      overflow: hidden !important;
    }}
    #wrap {{
      height: 520px !important;
      min-height: 520px !important;
      border: 0 !important;
      border-radius: 0 !important;
      background: {wrap_bg} !important;
    }}
    #chart {{
      height: 100% !important;
    }}
    #timelineBar {{
      left: 0 !important;
      right: 0 !important;
      bottom: 14px !important;
      gap: 8px !important;
      padding: 6px 8px !important;
      border-radius: 999px !important;
      background: {player_bg} !important;
      border: 1px solid {player_border} !important;
      backdrop-filter: none !important;
      -webkit-backdrop-filter: none !important;
      box-shadow: none !important;
    }}
    #musicBtn,
    #bgmAudio {{
      display: none !important;
    }}
    #playBtn {{
      width: 28px !important;
      height: 28px !important;
      position: relative !important;
      font-size: 0 !important;
      line-height: 1 !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      padding: 0 !important;
    }}
    #playBtn::before {{
      content: "" !important;
      width: 0 !important;
      height: 0 !important;
      border-top: 4px solid transparent !important;
      border-bottom: 4px solid transparent !important;
      border-left: 6px solid #ffffff !important;
      transform: translateX(1px) !important;
    }}
    #playBtn.is-playing::before {{
      width: 8px !important;
      height: 10px !important;
      border: 0 !important;
      border-radius: 1px !important;
      background: linear-gradient(90deg, #ffffff 0 36%, transparent 36% 64%, #ffffff 64% 100%) !important;
      transform: none !important;
    }}
    .pillBtn {{
      height: 28px !important;
      min-height: 28px !important;
      line-height: 28px !important;
      padding: 0 10px !important;
      color: {text} !important;
      background: rgba(148, 163, 184, .10) !important;
      border-color: {player_border} !important;
    }}
    .timeLabel, .timeLabel .yy {{
      color: {muted} !important;
    }}
    .timeLabel .md {{
      color: {text} !important;
    }}
    #sliderTrack {{
      background: rgba(76,145,255,.18) !important;
    }}
    #timelineRange::-webkit-slider-thumb {{
      background: #4c91ff !important;
      border: 0 !important;
      box-shadow: 0 0 0 5px rgba(76,145,255,.14) !important;
    }}
    #timelineRange::-moz-range-thumb {{
      background: #4c91ff !important;
      border: 0 !important;
      box-shadow: 0 0 0 5px rgba(76,145,255,.14) !important;
    }}
    @media (max-width: 720px) {{
      #wrap {{
        height: 320px !important;
        min-height: 320px !important;
      }}
      #timelineBar {{
        left: 0 !important;
        right: 0 !important;
        bottom: 12px !important;
        gap: 7px !important;
        padding-top: 5px !important;
        padding-bottom: 5px !important;
      }}
    }}
  </style>
"""
    document = document.replace("</head>", css + "</head>", 1)
    js = f"""
  <script id="projectDynamicLinePatch">
    window.__projectDynamicLineTheme = {{
      text: {json.dumps(text)},
      muted: {json.dumps(muted)},
      grid: {json.dumps(grid)},
      axis: {json.dumps(axis)},
      centerFill: {json.dumps(center_fill)}
    }};
  </script>
"""
    document = document.replace("<script>\n    const chart", js + "  <script>\n    const chart", 1)
    document = document.replace(
        "    const bgmDataUri = \"\";\n"
        "    const bgmFilename = \"\";",
        "    const bgmDataUri = \"\";\n"
        "    const bgmFilename = \"\";\n\n"
        "    function estimateLegendRows() {\n"
        "      const compact = isCompactLayout();\n"
        "      const width = chart.getWidth() || chartDom.clientWidth || 320;\n"
        "      const usableWidth = Math.max(120, width - (compact ? 24 : 32));\n"
        "      const averageItemWidth = compact ? 92 : 124;\n"
        "      return Math.max(1, Math.ceil((seriesList.length * averageItemWidth) / usableWidth));\n"
        "    }\n\n"
        "    function dynamicChartLayout() {\n"
        "      const compact = isCompactLayout();\n"
        "      const legendTop = compact ? 40 : 46;\n"
        "      const legendRows = estimateLegendRows();\n"
        "      const legendRowHeight = compact ? 20 : 22;\n"
        "      return {\n"
        "        legendTop,\n"
        "        legendLeft: 0,\n"
        "        legendRight: 0,\n"
        "        gridLeft: 0,\n"
        "        gridRight: 0,\n"
        "        gridTop: legendTop + legendRows * legendRowHeight + (compact ? 12 : 16),\n"
        "        gridBottom: compact ? 76 : 92\n"
        "      };\n"
        "    }",
        1,
    )
    document = document.replace("color: '#f8fafc'", f"color: window.__projectDynamicLineTheme.text")
    document = document.replace("fill: '#f8fafc'", "fill: window.__projectDynamicLineTheme.text")
    document = document.replace("color: '#a7b5c9'", "color: window.__projectDynamicLineTheme.muted")
    document = document.replace("color: '#8ea1bc'", "color: window.__projectDynamicLineTheme.muted")
    document = document.replace("color: 'rgba(56, 104, 190, 0.16)'", "color: window.__projectDynamicLineTheme.grid")
    document = document.replace("color: 'rgba(71, 85, 105, 0.45)'", "color: window.__projectDynamicLineTheme.axis")
    document = document.replace(
        "fill: compact ? 'rgba(148, 163, 184, 0.14)' : 'rgba(148, 163, 184, 0.16)'",
        "fill: window.__projectDynamicLineTheme.centerFill",
    )
    document = document.replace(
        "function buildCenterTimeGraphic() {\n"
        "      const compact = isCompactLayout();\n"
        "      return {\n"
        "        type: 'text',\n"
        "        left: 'center',\n"
        "        top: '47%',\n"
        "        silent: true,\n"
        "        z: 1,\n"
        "        style: {\n"
        "          text: getCurrentTimeText(),\n"
        "          fill: window.__projectDynamicLineTheme.centerFill,\n"
        "          fontSize: compact ? 32 : 38,\n"
        "          fontWeight: 700,\n"
        "          textAlign: 'center',\n"
        "          textVerticalAlign: 'middle'\n"
        "        }\n"
        "      };\n"
        "    }",
        "function buildCenterTimeGraphic() {\n"
        "      const compact = isCompactLayout();\n"
        "      const width = chart.getWidth();\n"
        "      const height = chart.getHeight();\n"
        "      const layout = dynamicChartLayout();\n"
        "      const gridLeft = layout.gridLeft;\n"
        "      const gridRight = layout.gridRight;\n"
        "      const gridTop = layout.gridTop;\n"
        "      const gridBottom = layout.gridBottom;\n"
        "      return {\n"
        "        type: 'text',\n"
        "        x: Math.round((gridLeft + width - gridRight) / 2),\n"
        "        y: Math.round((gridTop + height - gridBottom) / 2),\n"
        "        silent: true,\n"
        "        z: 1,\n"
        "        style: {\n"
        "          text: getCurrentTimeText(),\n"
        "          fill: window.__projectDynamicLineTheme.centerFill,\n"
        "          fontSize: compact ? 32 : 38,\n"
        "          fontWeight: 700,\n"
        "          textAlign: 'center',\n"
        "          textVerticalAlign: 'middle'\n"
        "        }\n"
        "      };\n"
        "    }",
    )
    document = document.replace(
        "backgroundColor: 'rgba(15, 23, 42, 0.94)',\n          borderColor: '#334155',",
        f"backgroundColor: {json.dumps(player_bg)},\n          borderColor: {json.dumps(player_border)},",
    )
    document = document.replace("textStyle: { color: '#f1f5f9' }", "textStyle: { color: window.__projectDynamicLineTheme.text }")
    document = document.replace("color:#f8fafc;", f"color:{text};")
    document = document.replace("color:#cbd5e1;", f"color:{muted};")

    document = document.replace(
        "top: compact ? 42 : 46,\n          left: compact ? 16 : 20,",
        "top: compact ? 44 : 50,\n          left: 0,",
    )
    document = document.replace(
        "left: compact ? 16 : 20,\n          top: compact ? 14 : 18,",
        "left: 0,\n          top: compact ? 14 : 18,",
    )
    document = document.replace(
        "legend: {\n"
        "          data: seriesList,\n"
        "          top: dynamicChartLayout().legendTop,\n"
        "          left: dynamicChartLayout().legendLeft,\n"
        "          right: dynamicChartLayout().legendRight,\n"
        "          itemWidth: compact ? 14 : 16,\n"
        "          itemHeight: 4,\n"
        "          icon: 'roundRect',\n"
        "          textStyle: {\n"
        "            color: window.__projectDynamicLineTheme.muted,\n"
        "            fontSize: compact ? 11 : 12,\n"
        "            padding: [0, 0, 0, 5]\n"
        "          }\n"
        "        },",
        "legend: {\n"
        "          data: seriesList,\n"
        "          top: compact ? 44 : 50,\n"
        "          left: compact ? 16 : 20,\n"
        "          itemWidth: compact ? 14 : 16,\n"
        "          itemHeight: 4,\n"
        "          itemGap: compact ? 10 : 18,\n"
        "          icon: 'roundRect',\n"
        "          formatter: function(name) {\n"
        "            const data = fullSeriesDataMap[name] || [];\n"
        "            const end = Math.min(getSafeIndex(), data.length - 1);\n"
        "            const point = getLastValidPoint(data.slice(0, end + 1));\n"
        "            return point ? `${name}  ${formatPlainValue(point.value)}` : name;\n"
        "          },\n"
        "          textStyle: {\n"
        "            color: window.__projectDynamicLineTheme.muted,\n"
        "            fontSize: compact ? 11 : 12,\n"
        "            padding: [0, 0, 0, 5]\n"
        "          }\n"
        "        },",
    )
    document = re.sub(
        r"legend:\s*\{.*?\n\s*\},\n\s*tooltip:\s*\{",
        "legend: {\n"
        "          data: seriesList,\n"
        "          top: dynamicChartLayout().legendTop,\n"
        "          left: dynamicChartLayout().legendLeft,\n"
        "          right: dynamicChartLayout().legendRight,\n"
        "          itemWidth: compact ? 14 : 16,\n"
        "          itemHeight: 4,\n"
        "          itemGap: compact ? 10 : 18,\n"
        "          icon: 'roundRect',\n"
        "          formatter: function(name) {\n"
        "            const data = fullSeriesDataMap[name] || [];\n"
        "            const end = Math.min(getSafeIndex(), data.length - 1);\n"
        "            const point = getLastValidPoint(data.slice(0, end + 1));\n"
        "            return point ? `${name}  ${formatPlainValue(point.value)}` : name;\n"
        "          },\n"
        "          textStyle: {\n"
        "            color: window.__projectDynamicLineTheme.muted,\n"
        "            fontSize: compact ? 11 : 12,\n"
        "            padding: [0, 0, 0, 5]\n"
        "          }\n"
        "        },\n"
        "        tooltip: {",
        document,
        flags=re.S,
        count=1,
    )
    document = document.replace(
        "grid: {\n          left: compact ? 16 : 20,\n          right: compact ? 12 : 16,\n          top: compact ? 74 : 80,\n          bottom: compact ? 78 : 82,",
        "grid: {\n          left: dynamicChartLayout().gridLeft,\n          right: dynamicChartLayout().gridRight,\n          top: dynamicChartLayout().gridTop,\n          bottom: dynamicChartLayout().gridBottom,",
    )
    document = document.replace(
        "tooltip: {\n          trigger: 'axis',",
        "tooltip: {\n          show: false,\n          trigger: 'none',",
    )
    document = document.replace(
        "return formatValue(value);\n            }",
        "return formatPlainValue(value);\n            }",
    )
    document = document.replace(
        "const minGap = compact ? 22 : 24;",
        "const minGap = compact ? 24 : 28;",
    )
    document = document.replace(
        "const leftLimit = compact ? 16 : 20;\n      const labelGap = 10;",
        "const leftLimit = compact ? 16 : 20;\n      const rightLimit = Math.max(leftLimit, chart.getWidth() - (compact ? 112 : 170));\n      const labelGap = compact ? 16 : 20;",
    )
    document = document.replace(
        "const anchorX = Math.max(item.x - labelGap, leftLimit);",
        "const anchorX = Math.max(leftLimit, Math.min(item.x + labelGap, rightLimit));",
    )
    document = document.replace(
        "graphic: [\n"
        "          buildCenterTimeGraphic(),\n"
        "          ...buildRightLabelsGraphics(safeIndex)\n"
        "        ]",
        "graphic: [\n"
        "          buildCenterTimeGraphic()\n"
        "        ]",
    )
    document = re.sub(
        r",\n\s*markPoint:\s*lastPoint\s*\?\s*\{.*?\n\s*\}\s*:\s*undefined",
        ",\n          markPoint: undefined",
        document,
        flags=re.S,
        count=0,
    )
    document = document.replace(
        "fill: window.__projectDynamicLineTheme.text,\n            backgroundColor: 'rgba(15, 23, 42, 0.68)',\n            borderColor: item.color,\n            borderWidth: 1.2,\n            borderRadius: 999,\n            padding: compact ? [4, 9] : [4, 10],",
        "fill: item.color,\n            backgroundColor: 'transparent',\n            borderColor: 'transparent',\n            borderWidth: 0,\n            borderRadius: 0,\n            padding: 0,",
    )
    document = document.replace("shadowBlur: 8,", "shadowBlur: 0,")
    document = document.replace("textAlign: 'right',", "textAlign: 'left',")
    return document


def postprocess_dynamic_line(payload: dict[str, Any], output: Path) -> None:
    materialize_fast_series(payload, output)
    document = output.read_text(encoding="utf-8")
    document = replace_script_loader(document)
    document = apply_shared_interaction_style(document)
    document = apply_layout_and_labels(document, dark=str(payload.get("theme") or "light").lower() == "dark")
    if "projectDynamicLineHeightReporter" not in document:
        document = document.replace(
            "</body>",
            """
  <script id="projectDynamicLineHeightReporter">
    (function(){
      function postChartHeight(){
        var wrap = document.getElementById('wrap');
        var rect = wrap ? wrap.getBoundingClientRect() : null;
        var height = Math.ceil(Math.max(180, rect ? rect.bottom : 0, document.body.scrollHeight || 0));
        try { parent.postMessage({type:'analysis-planner-chart-height', height:height}, '*'); } catch (e) {}
      }
      window.addEventListener('load', postChartHeight);
      window.addEventListener('resize', postChartHeight);
      setTimeout(postChartHeight, 80);
      setTimeout(postChartHeight, 300);
      setTimeout(postChartHeight, 900);
    })();
  </script>
</body>""",
            1,
        )
    document = document.replace("<script>\n    const chart", (Path(__file__).resolve().parents[1] / "runtime/dynamic_line_mobile.html").read_text(encoding="utf-8") + "<script>\n    const chart", 1)
    document = document.replace("    function renderChart() {", "    function renderChart() {\n      updateMobileDynamicHeader();")
    document = document.replace("        legend: {\n          data: seriesList,", "        legend: {\n          show: !compact,\n          selected: mobileLegendSelection,\n          data: seriesList,")
    document = document.replace("          text: title,", "          text: compact ? '' : title,")
    document = document.replace("gridTop: legendTop + legendRows * legendRowHeight + (compact ? 12 : 16)", "gridTop: compact ? document.querySelector('.mobileDynamicHeader').offsetHeight + 10 : legendTop + legendRows * legendRowHeight + 16")
    document = document.replace("gridBottom: compact ? 76 : 92", "gridBottom: compact ? 52 : 92")
    document = document.replace("</body>", (Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8") + "</body>")
    output.write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a generic dynamic_line chart.")
    parser.add_argument("--code")
    parser.add_argument("--title")
    parser.add_argument("--payload")
    parser.add_argument("--data-json")
    parser.add_argument("--data")
    parser.add_argument("--theme", default=None, help="Theme mode. Unknown/default values fall back to light.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    args, _ = parser.parse_known_args()

    payload = load_payload(args)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    render_aime_dynamic_line(payload, output)
    postprocess_dynamic_line(payload, output)

    if args.payload_output:
        payload_output = Path(args.payload_output).expanduser().resolve()
        payload_output.parent.mkdir(parents=True, exist_ok=True)
        payload_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "output": str(output), "chartName": "dynamic_line"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
