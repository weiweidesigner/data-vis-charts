#!/usr/bin/env python3
"""Render an Aime chart payload to a standalone HTML file."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Any


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


def _first_dict_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _infer_dynamic_line_encode(payload: dict[str, Any]) -> None:
    if isinstance(payload.get("encode"), dict):
        return

    rows = _first_dict_rows(payload.get("data"))
    if not rows:
        return

    keys = list(rows[0].keys())
    lower = {key.lower(): key for key in keys}
    x_key = (
        lower.get("time")
        or lower.get("date")
        or lower.get("datetime")
        or lower.get("month")
        or lower.get("year")
    )
    y_key = (
        lower.get("value")
        or lower.get("amount")
        or lower.get("revenue")
        or lower.get("count")
        or lower.get("price")
    )
    series_key = lower.get("series") or lower.get("category") or lower.get("name") or lower.get("region")

    if not x_key:
        x_key = next((key for key in keys if not _is_number(rows[0].get(key))), keys[0])
    if not y_key:
        y_key = next((key for key in keys if key != x_key and _is_number(rows[0].get(key))), None)
    if not series_key:
        series_key = next(
            (key for key in keys if key not in {x_key, y_key} and not _is_number(rows[0].get(key))),
            None,
        )

    if not y_key:
        return

    if not series_key:
        series_key = "__series"
        for row in rows:
            row.setdefault(series_key, payload.get("title") or "Series")

    payload["encode"] = {"x": x_key, "y": y_key, "series": series_key}


def _apply_payload_defaults(payload: dict[str, Any]) -> None:
    chart_name = str(payload.get("chartName", "")).strip()
    if chart_name in {"dynamic_line", "dynamicline", "echart_dynamic_line"}:
        _infer_dynamic_line_encode(payload)


def _load_json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload:
        payload_text = Path(args.payload).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        payload_text = sys.stdin.read()
    else:
        payload_text = "{}"

    payload = _load_json_value(payload_text or "{}")
    if not isinstance(payload, dict):
        raise SystemExit("Payload must be a JSON object.")

    if args.chart_name:
        payload["chartName"] = args.chart_name
    if args.data:
        payload["data"] = _load_json_value(args.data)
    if args.title:
        payload["title"] = args.title

    if not payload.get("chartName"):
        raise SystemExit("Missing chartName. Pass --chart-name or include chartName in the payload.")
    if "data" not in payload:
        raise SystemExit("Missing data. Pass --data or include data in the payload.")

    _apply_payload_defaults(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an Aime chart payload to HTML.")
    parser.add_argument("--payload", help="Path to a JSON payload file. Reads stdin when omitted.")
    parser.add_argument("--chart-name", help="Chart name or alias, for example dynamic_line or kline.")
    parser.add_argument("--data", help="JSON array/object to use as payload.data.")
    parser.add_argument("--title", help="Optional chart title.")
    parser.add_argument("--output", help="Output HTML file path.")
    parser.add_argument("--list", action="store_true", help="Print supported chart names and exit.")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    app_root = skill_root / "assets" / "aimechart"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(app_root))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        with contextlib.redirect_stdout(io.StringIO()):
            from charts.echart_dynamic_line import build_dynamic_line_html
            HTML_BUILDERS = {name: build_dynamic_line_html for name in ("dynamic_line", "dynamicline", "echart_dynamic_line")}
            def render_chart_html(payload, debug_logs):
                name = payload.get("chartName")
                if name not in HTML_BUILDERS:
                    raise SystemExit(f"Unsupported runtime chart: {name}")
                return HTML_BUILDERS[name](payload, debug_logs)

    if args.list:
        print("\n".join(HTML_BUILDERS.keys()))
        return 0

    if not args.output:
        raise SystemExit("Missing --output.")

    payload = _load_payload(args)
    debug_logs: list[str] = []
    html = render_chart_html(payload, debug_logs)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "output": str(output),
        "chartName": payload["chartName"],
        "debugLogs": debug_logs,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
