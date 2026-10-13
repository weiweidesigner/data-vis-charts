from typing import Any, Dict, List
import json
import ssl
import urllib.request

import requests

from utils.common import ensure_dict, ensure_list, ensure_str, get_nested_value


def _sanitize_json_text(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace(": NaN", ": null")
        .replace(": Infinity", ": null")
        .replace(": -Infinity", ": null")
    )


def _build_request_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    request_headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "Connection": "close",
    }
    for k, v in ensure_dict(headers).items():
        request_headers[str(k)] = str(v)
    return request_headers


def _parse_json_response_text(text: str) -> Any:
    safe_text = _sanitize_json_text(text)
    try:
        return json.loads(safe_text)
    except Exception as e:
        raise ValueError(f"远程 JSON 解析失败: {e}")


def _request_by_requests(
    url: str,
    method: str,
    headers: Dict[str, str],
    body: Any,
    timeout: int
) -> Any:
    if method == "GET":
        resp = requests.get(url, headers=headers, timeout=timeout)
    elif method == "POST":
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    else:
        raise ValueError(f"不支持的 method: {method}")

    resp.raise_for_status()
    return _parse_json_response_text(resp.text)


def _request_by_urllib(
    url: str,
    method: str,
    headers: Dict[str, str],
    body: Any,
    timeout: int
) -> Any:
    data = None
    if method == "POST":
        data = json.dumps(body if body is not None else {}).encode("utf-8")
        headers = dict(headers)
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    return _parse_json_response_text(text)


def fetch_json_from_url(source: Dict[str, Any]) -> Any:
    source = ensure_dict(source)
    mode = ensure_str(source.get("mode"), "url").lower().strip()
    if mode not in ("url", "remote_url"):
        raise ValueError("当前仅支持 mode = 'url' 或 'remote_url'")

    url = ensure_str(source.get("url"))
    if not url:
        raise ValueError("url 不能为空")

    method = ensure_str(source.get("method"), "GET").upper()
    headers = _build_request_headers(source.get("headers", {}))
    body = source.get("body")
    timeout = int(source.get("timeout", 20) or 20)

    requests_error = None

    try:
        return _request_by_requests(
            url=url,
            method=method,
            headers=headers,
            body=body,
            timeout=timeout,
        )
    except Exception as e:
        requests_error = e

    try:
        return _request_by_urllib(
            url=url,
            method=method,
            headers=headers,
            body=body,
            timeout=timeout,
        )
    except Exception as e:
        raise RuntimeError(
            "远程数据加载失败。\n"
            f"URL: {url}\n"
            f"requests错误: {repr(requests_error)}\n"
            f"urllib错误: {repr(e)}"
        )


def load_data_source(value: Any) -> List[Any]:
    """
    支持：
    1. data: [ ... ]
    2. data: {"mode":"inline","items":[...]}
    3. data: {"mode":"url","url":"...","path":"data"}
    4. data: {"mode":"remote_url","url":"...","path":"data"}
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        source = ensure_dict(value)
        mode = ensure_str(source.get("mode"), "inline").lower().strip()

        if mode == "inline":
            items = source.get("items")
            if items is None:
                items = source.get("data")
            return ensure_list(items, [])

        if mode in ("url", "remote_url"):
            data = fetch_json_from_url(source)
            path = ensure_str(source.get("path"), "").strip()
            if path:
                data = get_nested_value(data, path, [])
            if isinstance(data, list):
                return data
            raise ValueError("URL 返回的数据不是数组，请检查 path 配置")

    raise ValueError("data 必须是数组，或 inline/url/remote_url 配置对象")
