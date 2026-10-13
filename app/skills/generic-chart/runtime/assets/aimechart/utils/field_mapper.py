from typing import Any, Dict, List, Optional
from datetime import datetime

from utils.common import ensure_list, ensure_number, ensure_str, lower_key_map


DEFAULT_MAIN_FIELD_MAP = {
    "time": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume"
}


def merge_field_map(user_map: Optional[Dict[str, Any]], default_map: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(default_map)
    if isinstance(user_map, dict):
        for k, v in user_map.items():
            result[str(k)] = v
    return result


def get_value_by_mapping(row: Any, mapping_value: Any, fallback_candidates: List[Any] = None) -> Any:
    fallback_candidates = fallback_candidates or []

    if isinstance(row, list):
        candidates = []
        if isinstance(mapping_value, int):
            candidates.append(mapping_value)
        for item in fallback_candidates:
            if isinstance(item, int):
                candidates.append(item)

        for idx in candidates:
            if 0 <= idx < len(row):
                return row[idx]
        return None

    if isinstance(row, dict):
        row_map = lower_key_map(row)

        candidates = []
        if mapping_value is not None:
            candidates.append(mapping_value)
        candidates.extend(fallback_candidates)

        for key in candidates:
            if key is None:
                continue
            if isinstance(key, str):
                if key in row:
                    return row[key]
                lk = key.lower()
                if lk in row_map:
                    return row[row_map[lk]]
        return None

    return None


def parse_date_to_timestamp(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e12:
            return int(v)
        if v > 1e9:
            return int(v * 1000)
        return int(v)

    s = ensure_str(value).strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except Exception:
            pass

    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        pass

    return None


def normalize_bars(raw_rows: List[Any], field_map: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    rows = ensure_list(raw_rows)
    fmap = merge_field_map(field_map, DEFAULT_MAIN_FIELD_MAP)

    result = []
    for idx, item in enumerate(rows):
        if not isinstance(item, (dict, list)):
            continue

        time_raw = get_value_by_mapping(
            item,
            fmap.get("time"),
            ["timestamp", "Timestamp", "date", "Date", "time", "Time", "datetime", "Datetime", "ts", "TS"]
        )

        open_v = get_value_by_mapping(item, fmap.get("open"), ["open", "Open"])
        high_v = get_value_by_mapping(item, fmap.get("high"), ["high", "High"])
        low_v = get_value_by_mapping(item, fmap.get("low"), ["low", "Low"])
        close_v = get_value_by_mapping(item, fmap.get("close"), ["close", "Close"])
        volume_v = get_value_by_mapping(item, fmap.get("volume"), ["volume", "Volume", "vol", "Vol"])

        ts = parse_date_to_timestamp(time_raw)
        if ts is None:
            continue

        open_num = ensure_number(open_v, None)
        high_num = ensure_number(high_v, None)
        low_num = ensure_number(low_v, None)
        close_num = ensure_number(close_v, None)

        if open_num is None or high_num is None or low_num is None or close_num is None:
            continue

        row = {
            "timestamp": ts,
            "open": open_num,
            "high": high_num,
            "low": low_num,
            "close": close_num,
            "volume": ensure_number(volume_v, 0),
            "__index": idx
        }
        result.append(row)

    return result


def normalize_dynamic_line_dataset(payload: Dict[str, Any], fetch_json_from_url_func) -> Dict[str, Any]:
    from utils.common import ensure_dict  # 避免循环引用

    encode = ensure_dict(payload.get("encode"))
    x_key = ensure_str(encode.get("x")).strip()
    y_key = ensure_str(encode.get("y")).strip()
    series_key = ensure_str(encode.get("series")).strip()

    if not x_key:
        raise ValueError("encode.x 不能为空")
    if not y_key:
        raise ValueError("encode.y 不能为空")
    if not series_key:
        raise ValueError("encode.series 不能为空")

    data_value = payload.get("data")
    if data_value is None:
        raise ValueError("data 不能为空")

    if isinstance(data_value, list):
        raw_rows = data_value
    elif isinstance(data_value, dict):
        raw_rows = fetch_json_from_url_func(data_value)
    else:
        raise ValueError("data 必须是数组或 URL 对象")

    raw_rows = ensure_list(raw_rows)
    if not raw_rows:
        raise ValueError("data 数据为空")

    normalized_rows: List[Dict[str, Any]] = []
    series_order: List[str] = []
    x_order: List[Any] = []

    seen_series = set()
    seen_x = set()

    import json

    for i, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            raise ValueError(f"data 第 {i + 1} 行必须是对象")

        if x_key not in item:
            raise ValueError(f"data 第 {i + 1} 行缺少 x 字段: {x_key}")
        if y_key not in item:
            raise ValueError(f"data 第 {i + 1} 行缺少 y 字段: {y_key}")
        if series_key not in item:
            raise ValueError(f"data 第 {i + 1} 行缺少 series 字段: {series_key}")

        x_value = item.get(x_key)
        series_value = ensure_str(item.get(series_key)).strip()
        y_value = ensure_number(item.get(y_key), 0)

        if series_value == "":
            raise ValueError(f"data 第 {i + 1} 行的 series 字段不能为空: {series_key}")

        normalized_rows.append({
            x_key: x_value,
            y_key: y_value,
            series_key: series_value
        })

        if series_value not in seen_series:
            seen_series.add(series_value)
            series_order.append(series_value)

        x_identity = json.dumps(x_value, ensure_ascii=False, sort_keys=True)
        if x_identity not in seen_x:
            seen_x.add(x_identity)
            x_order.append(x_value)

    return {
        "xKey": x_key,
        "yKey": y_key,
        "seriesKey": series_key,
        "rows": normalized_rows,
        "seriesList": series_order,
        "xList": x_order
    }