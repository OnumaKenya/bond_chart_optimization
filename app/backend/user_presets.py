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


def _ensure_preset_approval() -> None:
    """(生徒名, ステータス名) ごとの承認フラグ用テーブルを用意する。

    プリセット1件 = (生徒名, ステータス名) なので student_priority と
    同じ粒度で管理する。新規ユーザー投稿は未承認(FALSE)、それ以外の
    既存データはマイグレーション時に承認済み(TRUE)として埋める。
    """
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS preset_approval (
                student_name TEXT NOT NULL,
                status_name  TEXT NOT NULL,
                approved     BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (student_name, status_name)
            )
        """)
        # 既存プリセット(costume⨝bond_bonus に存在するが未登録の組)は
        # 承認済みとして埋める。ユーザー投稿で既に FALSE 登録済みの組は
        # ON CONFLICT DO NOTHING で保持される。
        try:
            cur.execute("""
                INSERT INTO preset_approval (student_name, status_name, approved)
                SELECT DISTINCT c.student_name, bb.status_name, TRUE
                FROM costume c
                JOIN bond_bonus bb ON bb.costume_id = c.id
                ON CONFLICT (student_name, status_name) DO NOTHING
            """)
        except Exception:
            # costume / bond_bonus 未作成の環境ではバックフィルをスキップ。
            _logger.exception("preset_approval backfill skipped")


if _DATABASE_URL:
    try:
        _ensure_table()
        _ensure_preset_approval()
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


# --- 新スキーマ (costume ⨝ bond_bonus) からの読み込み ---

# ドロップダウン値の区切り文字（生徒名・ステータス名には出現しない）。
_PRESET_VALUE_SEP = "\x1f"

# ステータス名の選択肢。
VALID_STATUS_NAMES = ("攻撃", "HP", "治癒力", "防御")


def preset_exists(student_name: str, status_name: str) -> bool:
    """(生徒名, ステータス名) が登録済みかを返す。"""
    if not _DATABASE_URL:
        return False
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM costume c "
                "JOIN bond_bonus bb ON bb.costume_id = c.id "
                "WHERE c.student_name = %s AND bb.status_name = %s LIMIT 1",
                (student_name, status_name),
            )
            return cur.fetchone() is not None
    except Exception:
        _logger.exception("DB read error")
        return False


def register_costume_preset(
    student_name: str, status_name: str, costumes: list[dict]
) -> None:
    """新スキーマ (costume + bond_bonus) へプリセットを登録する。

    既存の (生徒名, 衣装名) は再利用し、(衣装, ステータス名) の
    bond_bonuses を追加する。
    """
    conn = _get_conn()
    with conn.cursor() as cur:
        for sort_order, c in enumerate(costumes):
            cur.execute(
                "INSERT INTO costume (student_name, costume_name, sort_order) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (student_name, costume_name) "
                "DO UPDATE SET costume_name = EXCLUDED.costume_name "
                "RETURNING id",
                (student_name, c["costume_name"], sort_order),
            )
            costume_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO bond_bonus (costume_id, status_name, bond_bonuses) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (costume_id, status_name) DO NOTHING",
                (costume_id, status_name, list(c["bond_bonuses"])),
            )
        # ユーザー投稿は未承認(FALSE)。既存登録があれば現状の承認状態を保持。
        cur.execute(
            "INSERT INTO preset_approval (student_name, status_name, approved) "
            "VALUES (%s, %s, FALSE) "
            "ON CONFLICT (student_name, status_name) DO NOTHING",
            (student_name, status_name),
        )


def _preset_label(student_name: str, status_name: str) -> str:
    """表示名。ステータスが既定の「攻撃」なら生徒名のみ、それ以外は括弧付き。"""
    if status_name == "攻撃":
        return student_name
    return f"{student_name}({status_name})"


def parse_preset_value(dropdown_value: str) -> tuple[str, str] | None:
    """ドロップダウン値を (生徒名, ステータス名) に分解する。"""
    if not dropdown_value or _PRESET_VALUE_SEP not in dropdown_value:
        return None
    student_name, status_name = dropdown_value.split(_PRESET_VALUE_SEP, 1)
    return student_name, status_name


def _load_costume_grouped() -> dict[tuple[str, str], list[dict]]:
    """costume と bond_bonus を結合し、(生徒名, ステータス名) ごとに
    [{costume_name, bond_bonuses}, ...] へまとめて返す。"""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.student_name, bb.status_name, c.costume_name, bb.bond_bonuses "
            "FROM costume c "
            "JOIN bond_bonus bb ON bb.costume_id = c.id "
            "LEFT JOIN student_priority sp ON sp.student_name = c.student_name "
            "ORDER BY COALESCE(sp.priority, 1000000), c.student_name, "
            "bb.status_name, c.sort_order, c.id"
        )
        rows = cur.fetchall()
    grouped: dict[tuple[str, str], list[dict]] = {}
    for student_name, status_name, costume_name, bond_bonuses in rows:
        grouped.setdefault((student_name, status_name), []).append(
            {
                "costume_name": costume_name,
                "bond_bonuses": list(bond_bonuses),
            }
        )
    return grouped


def _load_approval_map() -> dict[tuple[str, str], bool]:
    """(生徒名, ステータス名) -> 承認済みか の辞書を返す。

    未登録の組はテーブル作成時のバックフィルで承認済みになる想定だが、
    取得失敗時も安全側（承認済み扱い）に倒すため呼び出し側で
    dict.get(..., True) する。
    """
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT student_name, status_name, approved FROM preset_approval")
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}


def get_all_presets_for_dropdown() -> list[dict]:
    """全プリセットをドロップダウン用に返す。

    プリセット1件 = (生徒名, ステータス名) の組。
    """
    if not _DATABASE_URL:
        # JSON フォールバック (旧形式)
        options = []
        for key, entry in load_user_presets().items():
            char_name = entry["character_name"]
            label = (
                char_name if entry.get("approved") else f"{char_name} [ユーザー投稿]"
            )
            options.append(
                {"label": label, "value": key, "search": _search_text(char_name)}
            )
        return options

    try:
        grouped = _load_costume_grouped()
    except Exception:
        _logger.exception("DB read error")
        return []
    try:
        approval = _load_approval_map()
    except Exception:
        _logger.exception("DB read error (approval)")
        approval = {}
    options = []
    for student_name, status_name in grouped:
        base_label = _preset_label(student_name, status_name)
        approved = approval.get((student_name, status_name), True)
        label = base_label if approved else f"{base_label} [未承認]"
        options.append(
            {
                "label": label,
                "value": f"{student_name}{_PRESET_VALUE_SEP}{status_name}",
                "search": _search_text(base_label),
            }
        )
    return options


def get_preset_data(dropdown_value: str) -> tuple[str, list[dict]] | None:
    """ドロップダウン値からプリセットデータを取得する。

    Returns
    -------
    tuple[str, list[dict]] | None
        (表示名, [{costume_name, bond_bonuses}, ...]) のタプル。
        見つからなければ None。
    """
    if not _DATABASE_URL:
        presets = load_user_presets()
        entry = presets.get(dropdown_value)
        if entry:
            return (entry["character_name"], entry["costumes"])
        return None

    if _PRESET_VALUE_SEP not in dropdown_value:
        return None
    student_name, status_name = dropdown_value.split(_PRESET_VALUE_SEP, 1)
    try:
        grouped = _load_costume_grouped()
    except Exception:
        _logger.exception("DB read error")
        return None
    costumes = grouped.get((student_name, status_name))
    if not costumes:
        return None
    return (_preset_label(student_name, status_name), costumes)


# ======================================================================
# 管理画面用 (costume / bond_bonus / student_priority の編集)
# ======================================================================


def admin_load_presets() -> list[dict]:
    """(生徒名, ステータス名) ごとに編集用データを返す。"""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.student_name, bb.status_name, c.id, c.costume_name, "
            "c.sort_order, bb.bond_bonuses, COALESCE(pa.approved, TRUE) "
            "FROM costume c "
            "JOIN bond_bonus bb ON bb.costume_id = c.id "
            "LEFT JOIN student_priority sp ON sp.student_name = c.student_name "
            "LEFT JOIN preset_approval pa "
            "ON pa.student_name = c.student_name "
            "AND pa.status_name = bb.status_name "
            "ORDER BY COALESCE(sp.priority, 1000000), c.student_name, "
            "bb.status_name, c.sort_order, c.id"
        )
        rows = cur.fetchall()
    grouped: dict[tuple[str, str], dict] = {}
    for sn, st, cid, cname, so, bb, approved in rows:
        g = grouped.setdefault(
            (sn, st),
            {
                "student_name": sn,
                "status_name": st,
                "approved": approved,
                "costumes": [],
            },
        )
        g["costumes"].append(
            {
                "costume_id": cid,
                "costume_name": cname,
                "sort_order": so,
                "bond_bonuses": list(bb),
            }
        )
    return list(grouped.values())


def admin_load_priorities() -> list[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT student_name, priority FROM student_priority ORDER BY priority"
        )
        return [{"student_name": r[0], "priority": r[1]} for r in cur.fetchall()]


def admin_rebuild_preset(
    old_student: str,
    old_status: str,
    new_student: str,
    new_status: str,
    costumes: list[dict],
) -> None:
    """(生徒, ステータス) プリセットをフォーム内容で再構築する。

    共有 costume 行は再利用し、対象ステータスの bond_bonus のみ入れ替える。
    どのステータスからも参照されない costume 行は削除する。
    """
    conn = _get_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bond_bonus bb USING costume c "
                "WHERE bb.costume_id = c.id "
                "AND c.student_name = %s AND bb.status_name = %s",
                (old_student, old_status),
            )
            for i, c in enumerate(costumes):
                cur.execute(
                    "INSERT INTO costume (student_name, costume_name, sort_order) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (student_name, costume_name) "
                    "DO UPDATE SET sort_order = EXCLUDED.sort_order "
                    "RETURNING id",
                    (new_student, c["costume_name"], i),
                )
                costume_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO bond_bonus "
                    "(costume_id, status_name, bond_bonuses) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (costume_id, status_name) "
                    "DO UPDATE SET bond_bonuses = EXCLUDED.bond_bonuses",
                    (costume_id, new_status, list(c["bond_bonuses"])),
                )
            cur.execute(
                "DELETE FROM costume c "
                "WHERE c.student_name IN (%s, %s) "
                "AND NOT EXISTS "
                "(SELECT 1 FROM bond_bonus bb WHERE bb.costume_id = c.id)",
                (old_student, new_student),
            )
            if old_student != new_student:
                cur.execute(
                    "UPDATE student_priority SET student_name = %s "
                    "WHERE student_name = %s "
                    "AND NOT EXISTS "
                    "(SELECT 1 FROM student_priority WHERE student_name = %s)",
                    (new_student, old_student, new_student),
                )
            # 承認状態を引き継ぐ。既存登録があればその値を保持し
            # (管理者の編集・保存では承認状態を変えない)、
            # 未登録(=管理者の新規追加・既存マイグレ漏れ)は承認済み扱い。
            cur.execute(
                "SELECT approved FROM preset_approval "
                "WHERE student_name = %s AND status_name = %s",
                (old_student, old_status),
            )
            row = cur.fetchone()
            approved = row[0] if row else True
            if (old_student, old_status) != (new_student, new_status):
                cur.execute(
                    "DELETE FROM preset_approval "
                    "WHERE student_name = %s AND status_name = %s",
                    (old_student, old_status),
                )
            cur.execute(
                "INSERT INTO preset_approval "
                "(student_name, status_name, approved) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (student_name, status_name) "
                "DO UPDATE SET approved = EXCLUDED.approved",
                (new_student, new_status, approved),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def admin_delete_preset(student: str, status: str) -> None:
    conn = _get_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bond_bonus bb USING costume c "
                "WHERE bb.costume_id = c.id "
                "AND c.student_name = %s AND bb.status_name = %s",
                (student, status),
            )
            cur.execute(
                "DELETE FROM costume c "
                "WHERE c.student_name = %s "
                "AND NOT EXISTS "
                "(SELECT 1 FROM bond_bonus bb WHERE bb.costume_id = c.id)",
                (student,),
            )
            cur.execute(
                "DELETE FROM preset_approval "
                "WHERE student_name = %s AND status_name = %s",
                (student, status),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def admin_set_preset_approved(student: str, status: str, approved: bool) -> None:
    """(生徒名, ステータス名) プリセットの承認状態を設定する。"""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO preset_approval (student_name, status_name, approved) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (student_name, status_name) "
            "DO UPDATE SET approved = EXCLUDED.approved",
            (student, status, approved),
        )


def admin_upsert_priority(student: str, priority: int) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO student_priority (student_name, priority) "
            "VALUES (%s, %s) "
            "ON CONFLICT (student_name) DO UPDATE SET priority = EXCLUDED.priority",
            (student, priority),
        )


def admin_delete_priority(student: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM student_priority WHERE student_name = %s", (student,))


# ======================================================================
# 贈り物 (gift / present) — 贈り物配分シミュレータ用
# ======================================================================


def load_gifts() -> list[dict]:
    """全贈り物を定義順で返す。[{id, name, gift_type}, ...]"""
    if not _DATABASE_URL:
        return []
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, gift_type FROM gift ORDER BY sort_order")
            return [
                {"id": r[0], "name": r[1], "gift_type": r[2]} for r in cur.fetchall()
            ]
    except Exception:
        _logger.exception("DB read error")
        return []


def get_preset_present(
    student_name: str, status_name: str
) -> dict[str, dict[str, str]]:
    """(生徒名, ステータス名) プリセットの present を
    {衣装名: {gift_id: tier}} で返す。"""
    if not _DATABASE_URL:
        return {}
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.costume_name, p.gift_id, p.tier "
                "FROM present p "
                "JOIN costume c ON c.id = p.costume_id "
                "JOIN bond_bonus bb ON bb.costume_id = c.id "
                "WHERE c.student_name = %s AND bb.status_name = %s",
                (student_name, status_name),
            )
            out: dict[str, dict[str, str]] = {}
            for costume_name, gift_id, tier in cur.fetchall():
                out.setdefault(costume_name, {})[gift_id] = tier
            return out
    except Exception:
        _logger.exception("DB read error")
        return {}


def get_preset_preferred_gift_ids(student_name: str, status_name: str) -> set[str]:
    """(生徒名, ステータス名) プリセットの全衣装で、好み
    (favorite/superFavorite/ultraFavorite いずれか) に入る gift_id 集合。
    """
    if not _DATABASE_URL:
        return set()
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT p.gift_id "
                "FROM present p "
                "JOIN costume c ON c.id = p.costume_id "
                "JOIN bond_bonus bb ON bb.costume_id = c.id "
                "WHERE c.student_name = %s AND bb.status_name = %s",
                (student_name, status_name),
            )
            return {r[0] for r in cur.fetchall()}
    except Exception:
        _logger.exception("DB read error")
        return set()
