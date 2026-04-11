"""ユーザー投稿プリセットの管理。

JSON ファイルで永続化し、スレッドロックで並行書き込みを保護する。
"""

import json
import threading
import time
from pathlib import Path

from app.backend.presets import PRESETS

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BASE_DIR / "data"
_JSON_PATH = _DATA_DIR / "user_presets.json"
_lock = threading.Lock()


def _read() -> dict:
    """JSON ファイルを読み込む。存在しなければ空の dict を返す。"""
    if not _JSON_PATH.exists():
        return {}
    with open(_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("presets", {})


def _write(presets: dict) -> None:
    """JSON ファイルに書き込み、GitHub 同期をスケジュールする。"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, ensure_ascii=False, indent=2)
    from app.backend.github_sync import schedule_sync

    schedule_sync()


def load_user_presets() -> dict:
    with _lock:
        return _read()


def save_user_preset(character_name: str, costumes: list[dict]) -> str:
    """ユーザー投稿プリセットを保存する。生成されたキーを返す。"""
    key = f"{character_name}_{int(time.time())}"
    entry = {
        "character_name": character_name,
        "costumes": costumes,
        "approved": False,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _lock:
        presets = _read()
        presets[key] = entry
        _write(presets)
    return key


def approve_preset(key: str) -> bool:
    with _lock:
        presets = _read()
        if key not in presets:
            return False
        presets[key]["approved"] = True
        _write(presets)
    return True


def delete_preset(key: str) -> bool:
    with _lock:
        presets = _read()
        if key not in presets:
            return False
        del presets[key]
        _write(presets)
    return True


def promote_preset(key: str, name: str | None = None) -> bool:
    """ユーザー投稿プリセットを公式 presets.json に昇格させる。"""
    from app.backend.presets import PRESETS, _PRESETS_PATH

    with _lock:
        presets = _read()
        if key not in presets:
            return False
        entry = presets[key]
        register_name = name or entry["character_name"]
        PRESETS[register_name] = entry["costumes"]
        with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(PRESETS, f, ensure_ascii=False, indent=2)
        del presets[key]
        _write(presets)
    return True


def _kata_to_hira(text: str) -> str:
    """カタカナをひらがなに変換する。"""
    return "".join(chr(ord(c) - 0x60) if "\u30a1" <= c <= "\u30f6" else c for c in text)


def _search_text(name: str) -> str:
    """検索用テキスト（カタカナ + ひらがな）を生成する。"""
    hira = _kata_to_hira(name)
    return f"{name} {hira}" if hira != name else name


def get_all_presets_for_dropdown() -> list[dict]:
    """ビルトイン + ユーザー投稿プリセットをドロップダウン用に返す。"""
    options = []
    for name in PRESETS:
        options.append(
            {
                "label": name,
                "value": f"builtin::{name}",
                "search": _search_text(name),
            }
        )

    user_presets = load_user_presets()
    for key, entry in user_presets.items():
        char_name = entry["character_name"]
        if entry.get("approved"):
            label = char_name
        else:
            label = f"{char_name} [ユーザー投稿]"
        options.append(
            {
                "label": label,
                "value": f"user::{key}",
                "search": _search_text(char_name),
            }
        )

    return options


def get_preset_data(dropdown_value: str) -> list[dict] | None:
    """ドロップダウン値からプリセットデータを取得する。

    Returns
    -------
    list[dict] | None
        {"costume_name": str, "bond_bonuses": list[int]} のリスト。見つからなければ None。
    """
    if dropdown_value.startswith("builtin::"):
        name = dropdown_value[len("builtin::") :]
        return PRESETS.get(name)

    if dropdown_value.startswith("user::"):
        key = dropdown_value[len("user::") :]
        user_presets = load_user_presets()
        entry = user_presets.get(key)
        if entry:
            return entry["costumes"]
        return None

    # 後方互換: プレフィックスなし → ビルトイン扱い
    return PRESETS.get(dropdown_value)
