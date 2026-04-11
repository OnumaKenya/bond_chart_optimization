"""プリセットの管理。

DATABASE_URL が設定されている場合は PostgreSQL を使用し、
未設定の場合は JSON ファイルにフォールバックする（ローカル開発用）。
全プリセット（旧ビルトイン含む）を DB で一元管理する。
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL")

# ======================================================================
# JSON ファイルバックエンド (ローカル開発用フォールバック)
# ======================================================================

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BASE_DIR / "data"
_JSON_PATH = _DATA_DIR / "user_presets.json"
_lock = threading.Lock()


def _json_read() -> dict:
    if not _JSON_PATH.exists():
        return {}
    with open(_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("presets", {})


def _json_write(presets: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, ensure_ascii=False, indent=2)


# ======================================================================
# PostgreSQL バックエンド
# ======================================================================

_conn = None


def _get_conn():
    """PostgreSQL 接続を取得する（再接続対応）。"""
    global _conn
    import psycopg2

    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(_DATABASE_URL)
        _conn.autocommit = True
    return _conn


def _ensure_table() -> None:
    """テーブルが存在しなければ作成する。"""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_presets (
                key            TEXT PRIMARY KEY,
                character_name TEXT NOT NULL,
                costumes       JSONB NOT NULL,
                approved       BOOLEAN NOT NULL DEFAULT FALSE,
                submitted_at   TEXT NOT NULL
            )
        """)


if _DATABASE_URL:
    try:
        _ensure_table()
        _logger.info("PostgreSQL backend initialized")
    except Exception:
        _logger.exception("Failed to initialize user_presets table")


# ======================================================================
# 公開 API
# ======================================================================


def load_user_presets() -> dict:
    """全プリセットを返す。"""
    if _DATABASE_URL:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key, character_name, costumes, approved, submitted_at "
                    "FROM user_presets"
                )
                rows = cur.fetchall()
            return {
                row[0]: {
                    "character_name": row[1],
                    "costumes": row[2],
                    "approved": row[3],
                    "submitted_at": row[4],
                }
                for row in rows
            }
        except Exception:
            _logger.exception("DB read error")
            return {}
    else:
        with _lock:
            return _json_read()


def save_user_preset(character_name: str, costumes: list[dict]) -> str:
    """プリセットを保存する。生成されたキーを返す。"""
    key = f"{character_name}_{int(time.time())}"
    submitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if _DATABASE_URL:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_presets (key, character_name, costumes, approved, submitted_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (key, character_name, json.dumps(costumes), False, submitted_at),
            )
    else:
        with _lock:
            presets = _json_read()
            presets[key] = {
                "character_name": character_name,
                "costumes": costumes,
                "approved": False,
                "submitted_at": submitted_at,
            }
            _json_write(presets)
    return key


def approve_preset(key: str) -> bool:
    """プリセットを承認する。"""
    if _DATABASE_URL:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_presets SET approved = TRUE WHERE key = %s", (key,)
            )
            return cur.rowcount > 0
    else:
        with _lock:
            presets = _json_read()
            if key not in presets:
                return False
            presets[key]["approved"] = True
            _json_write(presets)
        return True


def delete_preset(key: str) -> bool:
    """プリセットを削除する。"""
    if _DATABASE_URL:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_presets WHERE key = %s", (key,))
            return cur.rowcount > 0
    else:
        with _lock:
            presets = _json_read()
            if key not in presets:
                return False
            del presets[key]
            _json_write(presets)
        return True


# ======================================================================
# ドロップダウン用ヘルパー
# ======================================================================


def _kata_to_hira(text: str) -> str:
    """カタカナをひらがなに変換する。"""
    return "".join(chr(ord(c) - 0x60) if "\u30a1" <= c <= "\u30f6" else c for c in text)


def _search_text(name: str) -> str:
    """検索用テキスト（カタカナ + ひらがな）を生成する。"""
    hira = _kata_to_hira(name)
    return f"{name} {hira}" if hira != name else name


def get_all_presets_for_dropdown() -> list[dict]:
    """全プリセットをドロップダウン用に返す。"""
    options = []
    all_presets = load_user_presets()
    for key, entry in all_presets.items():
        char_name = entry["character_name"]
        if entry.get("approved"):
            label = char_name
        else:
            label = f"{char_name} [ユーザー投稿]"
        options.append(
            {
                "label": label,
                "value": key,
                "search": _search_text(char_name),
            }
        )
    return options


def get_preset_data(dropdown_value: str) -> list[dict] | None:
    """ドロップダウン値からプリセットデータを取得する。"""
    if _DATABASE_URL:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT costumes FROM user_presets WHERE key = %s",
                    (dropdown_value,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            _logger.exception("DB read error")
            return None
    else:
        presets = load_user_presets()
        entry = presets.get(dropdown_value)
        if entry:
            return entry["costumes"]
        return None
