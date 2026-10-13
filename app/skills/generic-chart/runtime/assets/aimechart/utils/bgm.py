from typing import Any, Dict, List, Optional
import base64
import mimetypes
from pathlib import Path

from utils.common import ensure_str


DEFAULT_BGM_FILENAME = "f41bae72-bb10-46b7-8755-48be89abb60e.mp3"
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac"}


def _empty_bgm(filename: str = "", mime_type: str = "audio/mpeg") -> Dict[str, str]:
    return {"data_uri": "", "filename": filename, "mime_type": mime_type}


def _encode_audio_file(path: Path, debug_logs: Optional[List[str]] = None) -> Dict[str, str]:
    if debug_logs is None:
        debug_logs = []

    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or "audio/mpeg"

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        debug_logs.append(f"背景音乐已加载: {path}")
        return {
            "data_uri": f"data:{mime_type};base64,{encoded}",
            "filename": path.name,
            "mime_type": mime_type,
        }
    except Exception as e:
        debug_logs.append(f"读取背景音乐失败: {path}, error={e}")
        return _empty_bgm(path.name, mime_type)


def _default_assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def pick_background_music_base64(
    payload: Optional[Dict[str, Any]] = None,
    debug_logs: Optional[List[str]] = None,
    assets_dir: Optional[str] = None,
) -> Dict[str, str]:
    if debug_logs is None:
        debug_logs = []
    payload = payload if isinstance(payload, dict) else {}

    data_uri = ensure_str(payload.get("bgmDataUri") or payload.get("bgm_data_uri"), "").strip()
    filename = ensure_str(payload.get("bgmFilename") or payload.get("bgm_filename"), "").strip()
    if data_uri:
        return {
            "data_uri": data_uri,
            "filename": filename or "inline-bgm",
            "mime_type": "audio/mpeg",
        }

    bgm_path = ensure_str(payload.get("bgmPath") or payload.get("bgm_path"), "").strip()
    if bgm_path:
        path = Path(bgm_path).expanduser()
        if path.is_file():
            return _encode_audio_file(path, debug_logs)
        debug_logs.append(f"指定背景音乐不存在: {path}")

    root = Path(assets_dir).expanduser() if assets_dir else _default_assets_dir()
    if not root.is_dir():
        debug_logs.append(f"背景音乐目录不存在: {root}")
        return _empty_bgm()

    preferred = root / DEFAULT_BGM_FILENAME
    if preferred.is_file():
        return _encode_audio_file(preferred, debug_logs)

    audio_files = sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTS
    )
    if not audio_files:
        debug_logs.append(f"未在目录中找到音频文件: {root}")
        return _empty_bgm()

    return _encode_audio_file(audio_files[0], debug_logs)
