import json
from typing import Any, Dict


def ensure_dict(value, default=None):
    if value is None:
        return default if default is not None else {}
    if isinstance(value, dict):
        return value
    raise ValueError("字段必须是对象")


def ensure_list(value, default=None):
    if value is None:
        return default if default is not None else []
    if isinstance(value, list):
        return value
    raise ValueError("字段必须是数组")


def ensure_str(value, default=""):
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def ensure_number(value, default=0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except Exception:
        return default


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def lower_key_map(d: Dict[str, Any]) -> Dict[str, str]:
    result = {}
    for k in d.keys():
        result[str(k).lower()] = k
    return result


def get_nested_value(obj: Any, path: str, default=None):
    if not path:
        return default
    if obj is None:
        return default

    current = obj
    for part in str(path).split("."):
        if not isinstance(current, dict):
            return default
        if part not in current:
            return default
        current = current[part]
    return current