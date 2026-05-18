#!/usr/bin/env python3
"""プリセットDB（costume / bond_bonus / student_priority）をGUIで管理するローカルツール。

接続先は .env の DATABASE_URL（ローカル）。

使い方:
    python scripts/manage_prod_db.py

実行するとローカル HTTP サーバーが起動し、自動でブラウザが開きます。
"""

import os
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import psycopg2

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env():
    """Load .env file into environment variables."""
    if _ENV_PATH.exists():
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ローカルDBに接続する。
_DB_URL = os.environ.get("DATABASE_URL", "")

_STATUS_NAMES = ("攻撃", "HP", "治癒力", "防御")
_RANGE_LABELS = ["2~5", "6~10", "11~15", "16~20", "21~30", "31~40", "41~50"]
_NUM_RANGES = len(_RANGE_LABELS)

_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(_DB_URL)
        _conn.autocommit = True
    return _conn


def _ensure_tables() -> None:
    """新スキーマのテーブルが無ければ作成する（冪等）。"""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS costume (
                id           SERIAL PRIMARY KEY,
                student_name TEXT NOT NULL,
                costume_name TEXT NOT NULL,
                sort_order   INTEGER NOT NULL DEFAULT 0,
                UNIQUE (student_name, costume_name)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bond_bonus (
                id           SERIAL PRIMARY KEY,
                costume_id   INTEGER NOT NULL REFERENCES costume(id) ON DELETE CASCADE,
                status_name  TEXT NOT NULL,
                bond_bonuses INTEGER[] NOT NULL,
                UNIQUE (costume_id, status_name)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_bond_bonus_costume_id "
            "ON bond_bonus(costume_id)"
        )
        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_priority (
                student_name TEXT PRIMARY KEY,
                priority     INTEGER NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS preset_approval (
                student_name TEXT NOT NULL,
                status_name  TEXT NOT NULL,
                approved     BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (student_name, status_name)
            )
        """)
        # 既存プリセットは承認済みとして埋める（ユーザー投稿で未承認登録
        # 済みの組は ON CONFLICT DO NOTHING で保持）。
        cur.execute("""
            INSERT INTO preset_approval (student_name, status_name, approved)
            SELECT DISTINCT c.student_name, bb.status_name, TRUE
            FROM costume c
            JOIN bond_bonus bb ON bb.costume_id = c.id
            ON CONFLICT (student_name, status_name) DO NOTHING
        """)


# ======================================================================
# データアクセス
# ======================================================================


def load_presets() -> list[dict]:
    """(生徒名, ステータス名) ごとにプリセットをまとめて返す。"""
    cur = _get_conn().cursor()
    cur.execute(
        "SELECT c.student_name, bb.status_name, c.id, c.costume_name, "
        "c.sort_order, bb.bond_bonuses, COALESCE(pa.approved, TRUE) "
        "FROM costume c "
        "JOIN bond_bonus bb ON bb.costume_id = c.id "
        "LEFT JOIN student_priority sp ON sp.student_name = c.student_name "
        "LEFT JOIN preset_approval pa ON pa.student_name = c.student_name "
        "AND pa.status_name = bb.status_name "
        "ORDER BY COALESCE(sp.priority, 1000000), c.student_name, "
        "bb.status_name, c.sort_order, c.id"
    )
    grouped: dict[tuple[str, str], dict] = {}
    for sn, st, cid, cname, so, bb, approved in cur.fetchall():
        key = (sn, st)
        g = grouped.setdefault(
            key,
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


def load_priorities() -> list[dict]:
    cur = _get_conn().cursor()
    cur.execute("SELECT student_name, priority FROM student_priority ORDER BY priority")
    return [{"student_name": r[0], "priority": r[1]} for r in cur.fetchall()]


def _rebuild_preset(
    old_student: str,
    old_status: str,
    new_student: str,
    new_status: str,
    costumes: list[dict],
) -> None:
    """(生徒, ステータス) プリセットをフォーム内容で再構築する。

    共有 costume 行は再利用し、対象ステータスの bond_bonus のみ入れ替える。
    どのステータスからも参照されなくなった costume 行は削除する。
    """
    conn = _get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # 1. 旧 (生徒, ステータス) の bond_bonus を削除
        cur.execute(
            "DELETE FROM bond_bonus bb USING costume c "
            "WHERE bb.costume_id = c.id "
            "AND c.student_name = %s AND bb.status_name = %s",
            (old_student, old_status),
        )
        # 2. フォーム内容で costume / bond_bonus を upsert
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
                "INSERT INTO bond_bonus (costume_id, status_name, bond_bonuses) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (costume_id, status_name) "
                "DO UPDATE SET bond_bonuses = EXCLUDED.bond_bonuses",
                (costume_id, new_status, c["bond_bonuses"]),
            )
        # 3. 孤立 costume（bond_bonus から参照されない）を削除
        cur.execute(
            "DELETE FROM costume c "
            "WHERE c.student_name IN (%s, %s) "
            "AND NOT EXISTS "
            "(SELECT 1 FROM bond_bonus bb WHERE bb.costume_id = c.id)",
            (old_student, new_student),
        )
        # 4. 生徒名変更時は student_priority も移行（移行先が空なら）
        if old_student != new_student:
            cur.execute(
                "UPDATE student_priority SET student_name = %s "
                "WHERE student_name = %s "
                "AND NOT EXISTS "
                "(SELECT 1 FROM student_priority WHERE student_name = %s)",
                (new_student, old_student, new_student),
            )
        # 5. 承認状態を引き継ぐ。既存登録があれば保持し、未登録
        #    （新規追加・マイグレ漏れ）は承認済み扱い。
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
            "INSERT INTO preset_approval (student_name, status_name, approved) "
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


def delete_preset(student: str, status: str) -> None:
    conn = _get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    try:
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
            "DELETE FROM preset_approval WHERE student_name = %s AND status_name = %s",
            (student, status),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def set_preset_approved(student: str, status: str, approved: bool) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO preset_approval (student_name, status_name, approved) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (student_name, status_name) "
        "DO UPDATE SET approved = EXCLUDED.approved",
        (student, status, approved),
    )


def upsert_priority(student: str, priority: int) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO student_priority (student_name, priority) VALUES (%s, %s) "
        "ON CONFLICT (student_name) DO UPDATE SET priority = EXCLUDED.priority",
        (student, priority),
    )


def delete_priority(student: str) -> None:
    cur = _get_conn().cursor()
    cur.execute("DELETE FROM student_priority WHERE student_name = %s", (student,))


# ======================================================================
# HTML
# ======================================================================


def html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


_STYLE = """
<style>
  * { box-sizing: border-box; }
  body { font-family: sans-serif; max-width: 1280px; margin: 30px auto; padding: 0 20px;
         background: #f5f5f5; }
  h1 { color: #333; }
  h2 { font-size: 1.15rem; color: #333; margin: 28px 0 8px; }
  .msg { padding: 10px; border-radius: 6px; margin: 12px 0; }
  .msg-ok { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
  .msg-err { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
  .summary { color: #666; margin-bottom: 16px; font-size: 0.9rem; }
  table { border-collapse: collapse; width: 100%; background: white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
  th, td { border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.85rem;
           vertical-align: top; }
  th { background: #3498db; color: white; position: sticky; top: 0; }
  tr:nth-child(even) { background: #f9f9f9; }
  tr:hover { background: #eef6ff; }
  button { cursor: pointer; border: none; padding: 6px 14px; border-radius: 4px;
           font-size: 0.85rem; color: white; }
  .btn-save { background: #27ae60; }
  .btn-delete { background: #e74c3c; }
  .btn-add { background: #2980b9; padding: 8px 20px; font-size: 0.95rem; margin-top: 12px; }
  .btn-add-costume { background: #27ae60; font-size: 0.8rem; padding: 4px 10px; }
  .btn-remove-costume { background: #e74c3c; font-size: 0.75rem; padding: 3px 8px; }
  .btn-approve { background: #27ae60; }
  .btn-unapprove { background: #e67e22; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
           font-size: 0.75rem; font-weight: bold; }
  .badge-approved { background: #d4edda; color: #155724; }
  .badge-pending { background: #f8d7da; color: #721c24; }
  input[type=text], input[type=number], select {
    padding: 5px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
  input[type=number] { width: 54px; text-align: center; }
  input[type=number]::-webkit-inner-spin-button,
  input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  input[type=number] { -moz-appearance: textbox; appearance: textbox; }
  .costume-row { display: flex; gap: 4px; align-items: center; margin-bottom: 4px;
                 flex-wrap: wrap; }
  .costume-row input[type=text] { width: 100px; flex-shrink: 0; }
  .actions { display: flex; gap: 6px; align-items: center; }
  form { margin: 0; }
  .section { margin-top: 24px; }
  .add-form { background: white; padding: 16px; border-radius: 8px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .add-form label { display: block; font-weight: bold; margin-top: 10px;
                    margin-bottom: 4px; font-size: 0.85rem; }
  .range-labels { display: flex; gap: 4px; margin-bottom: 4px; margin-left: 104px; }
  .range-labels span { font-size: 0.65rem; color: #888; width: 54px; text-align: center; }
  .footer { text-align: center; color: #999; font-size: 0.8rem; margin-top: 30px; }
  .empty { text-align: center; color: #888; padding: 30px; }
  .pri-row { display: flex; gap: 6px; align-items: center; }
</style>
"""


def _status_select(name: str, selected: str) -> str:
    opts = "".join(
        f'<option value="{html_escape(s)}"'
        f"{' selected' if s == selected else ''}>{html_escape(s)}</option>"
        for s in _STATUS_NAMES
    )
    return f'<select name="{name}">{opts}</select>'


def _range_header() -> str:
    labels = "".join(f"<span>{lbl}</span>" for lbl in _RANGE_LABELS)
    return f'<div class="range-labels"><span style="width:100px"></span>{labels}</div>'


def _costume_row(prefix: str, idx: int, costume: dict | None = None) -> str:
    cname = html_escape(costume["costume_name"]) if costume else ""
    bonuses = costume["bond_bonuses"] if costume else [0] * _NUM_RANGES
    inp = (
        f'<input type="text" name="{prefix}_cname_{idx}" '
        f'value="{cname}" placeholder="衣装名">'
    )
    for j in range(_NUM_RANGES):
        v = bonuses[j] if j < len(bonuses) else 0
        inp += f'<input type="number" name="{prefix}_b{j}_{idx}" value="{v}" min="0">'
    inp += (
        ' <button type="button" class="btn-remove-costume" '
        'onclick="this.parentElement.remove()">✕</button>'
    )
    return f'<div class="costume-row">{inp}</div>'


def render_page(message: str = "", msg_type: str = "ok") -> str:
    presets = load_presets()
    priorities = load_priorities()

    msg_html = ""
    if message:
        cls = "msg-ok" if msg_type == "ok" else "msg-err"
        msg_html = f'<div class="msg {cls}">{html_escape(message)}</div>'

    # --- 表示優先度 ---
    pri_rows = ""
    for p in priorities:
        sn = html_escape(p["student_name"])
        pri_rows += f"""<tr>
          <td>
            <form method="post" action="/priority_save" class="pri-row">
              <input type="hidden" name="orig_student" value="{sn}">
              <input type="text" name="student_name" value="{sn}" style="width:160px">
              <input type="number" name="priority" value="{p["priority"]}"
                     style="width:80px">
              <button type="submit" class="btn-save">保存</button>
            </form>
          </td>
          <td>
            <form method="post" action="/priority_delete"
              onsubmit="return confirm('「{sn}」の優先度を削除しますか？')">
              <input type="hidden" name="student_name" value="{sn}">
              <button type="submit" class="btn-delete">削除</button>
            </form>
          </td>
        </tr>"""
    if not pri_rows:
        pri_rows = '<tr><td colspan="2" class="empty">優先度の設定なし</td></tr>'

    priority_section = f"""
    <h2>表示優先度 (student_priority)</h2>
    <div class="summary">数値が小さいほど先頭に表示。空き番号を残すと後から挿入しやすい。</div>
    <table>
      <thead><tr><th>生徒名 / 優先度</th><th style="width:90px">操作</th></tr></thead>
      <tbody>{pri_rows}</tbody>
    </table>
    <div class="add-form">
      <form method="post" action="/priority_save" class="pri-row">
        <input type="text" name="student_name" placeholder="生徒名" required
               style="width:160px">
        <input type="number" name="priority" placeholder="優先度" required
               style="width:80px">
        <button type="submit" class="btn-add">優先度を追加/更新</button>
      </form>
    </div>"""

    # --- プリセット ---
    if not presets:
        preset_rows = '<div class="empty">レコードがありません。</div>'
    else:
        rows = ""
        pending_count = 0
        for pi, p in enumerate(presets):
            sn = html_escape(p["student_name"])
            st = p["status_name"]
            approved = p.get("approved", True)
            if not approved:
                pending_count += 1
            prefix = f"p{pi}"
            costume_html = _range_header()
            for ci, c in enumerate(p["costumes"]):
                costume_html += _costume_row(prefix, ci, c)
            add_js = (
                f"addCostume(this.parentElement.querySelector('.costumes'),'{prefix}')"
            )
            if approved:
                badge = '<span class="badge badge-approved">承認済み</span>'
                appr_btn = (
                    '<input type="hidden" name="approved" value="0">'
                    '<button type="submit" class="btn-unapprove">承認解除</button>'
                )
            else:
                badge = '<span class="badge badge-pending">未承認</span>'
                appr_btn = (
                    '<input type="hidden" name="approved" value="1">'
                    '<button type="submit" class="btn-approve">承認</button>'
                )
            rows += f"""<tr>
              <td>
                <div style="margin-bottom:6px">{badge}</div>
                <form method="post" action="/preset_save" id="form_{prefix}">
                  <input type="hidden" name="old_student" value="{sn}">
                  <input type="hidden" name="old_status"
                         value="{html_escape(st)}">
                  生徒名:
                  <input type="text" name="student_name" value="{sn}"
                         style="width:150px">
                  ステータス: {_status_select("status_name", st)}
                  <div class="costumes" style="margin-top:8px">{costume_html}</div>
                  <button type="button" class="btn-add-costume"
                          onclick="{add_js}">+ 衣装</button>
                </form>
              </td>
              <td>
                <div class="actions" style="flex-direction:column;gap:8px">
                  <button type="submit" form="form_{prefix}"
                          class="btn-save">保存</button>
                  <form method="post" action="/preset_set_approval">
                    <input type="hidden" name="student" value="{sn}">
                    <input type="hidden" name="status" value="{html_escape(st)}">
                    {appr_btn}
                  </form>
                  <form method="post" action="/preset_delete"
                    onsubmit="return confirm('「{sn}({html_escape(st)})」を削除しますか？')">
                    <input type="hidden" name="student" value="{sn}">
                    <input type="hidden" name="status" value="{html_escape(st)}">
                    <button type="submit" class="btn-delete">削除</button>
                  </form>
                </div>
              </td>
            </tr>"""
        preset_rows = f"""<table><thead><tr>
          <th>生徒 / ステータス / 衣装（ボーナス: {", ".join(_RANGE_LABELS)}）</th>
          <th style="width:90px">操作</th>
        </tr></thead><tbody>{rows}</tbody></table>"""
        if pending_count:
            preset_rows = (
                f'<div class="summary">未承認: {pending_count} 件 '
                "（公開側では「[未承認]」表示）</div>" + preset_rows
            )

    add_preset = f"""
    <div class="section">
      <h2>新規プリセット追加</h2>
      <div class="add-form">
        <form method="post" action="/preset_add" id="add-form">
          <label>生徒名</label>
          <input type="text" name="student_name" required style="width:200px">
          <label>ステータス名</label>
          {_status_select("status_name", "攻撃")}
          <label>衣装</label>
          {_range_header()}
          <div id="add-costumes" class="costumes">
            {_costume_row("add", 0)}
          </div>
          <button type="button" class="btn-add-costume"
                  onclick="addCostume(document.getElementById('add-costumes'),'add')">
            + 衣装追加</button>
          <br>
          <button type="submit" class="btn-add">追加</button>
        </form>
      </div>
    </div>"""

    nranges = _NUM_RANGES
    script = f"""
    <script>
    var counters = {{}};
    function addCostume(container, prefix) {{
      if (!(prefix in counters)) {{
        counters[prefix] = container.querySelectorAll('.costume-row').length;
      }}
      var idx = counters[prefix];
      var row = document.createElement('div');
      row.className = 'costume-row';
      var html = '<input type="text" name="' + prefix + '_cname_' + idx
        + '" placeholder="衣装名">';
      for (var j = 0; j < {nranges}; j++) {{
        html += '<input type="number" name="' + prefix + '_b' + j + '_' + idx
          + '" value="0" min="0">';
      }}
      html += ' <button type="button" class="btn-remove-costume"'
        + ' onclick="this.parentElement.remove()">✕</button>';
      row.innerHTML = html;
      container.appendChild(row);
      counters[prefix] = idx + 1;
    }}
    </script>"""

    target = _DB_URL.split("@")[-1] if "@" in _DB_URL else "(unknown)"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>プリセットDB管理</title>{_STYLE}</head><body>
    <h1>プリセットDB管理</h1>
    <div class="summary">接続先: {html_escape(target)}</div>
    {msg_html}
    {priority_section}
    <h2>プリセット (costume + bond_bonus) — 全 {len(presets)} 件</h2>
    {preset_rows}
    {add_preset}
    {script}
    <div class="footer">Ctrl+C で停止</div>
    </body></html>"""


def _parse_costumes(params: dict, prefix: str) -> list[dict]:
    costumes = []
    idx = 0
    while True:
        cname_key = f"{prefix}_cname_{idx}"
        if cname_key not in params:
            break
        cname = params[cname_key][0].strip()
        if cname:
            bonuses = []
            for j in range(_NUM_RANGES):
                vals = params.get(f"{prefix}_b{j}_{idx}", ["0"])
                try:
                    bonuses.append(int(vals[0]) if vals[0] else 0)
                except ValueError:
                    bonuses.append(0)
            costumes.append({"costume_name": cname, "bond_bonuses": bonuses})
        idx += 1
    return costumes


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a, **_k):
        pass

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            q = parse_qs(parsed.query)
            self._send_html(
                render_page(q.get("msg", [""])[0], q.get("type", ["ok"])[0])
            )
        else:
            self._send_html("Not Found", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        path = urlparse(self.path).path
        msg, msg_type = "", "ok"
        try:
            if path == "/preset_save":
                msg = self._preset_save(params)
            elif path == "/preset_add":
                msg = self._preset_add(params)
            elif path == "/preset_delete":
                msg = self._preset_delete(params)
            elif path == "/preset_set_approval":
                msg = self._preset_set_approval(params)
            elif path == "/priority_save":
                msg = self._priority_save(params)
            elif path == "/priority_delete":
                msg = self._priority_delete(params)
            else:
                msg, msg_type = "不明な操作です", "err"
        except Exception as e:
            msg, msg_type = f"エラー: {e}", "err"
        self._redirect(f"/?msg={quote(msg)}&type={msg_type}")

    @staticmethod
    def _preset_save(params: dict) -> str:
        old_s = params.get("old_student", [""])[0]
        old_st = params.get("old_status", [""])[0]
        new_s = params.get("student_name", [""])[0].strip()
        new_st = params.get("status_name", [""])[0].strip()
        if not new_s:
            return "生徒名が空です"
        if new_st not in _STATUS_NAMES:
            return "ステータス名が不正です"
        costumes = _parse_costumes_for_save(params)
        if not costumes:
            return "衣装が1つもありません"
        _rebuild_preset(old_s, old_st, new_s, new_st, costumes)
        return f"「{new_s}({new_st})」を更新しました"

    @staticmethod
    def _preset_add(params: dict) -> str:
        new_s = params.get("student_name", [""])[0].strip()
        new_st = params.get("status_name", [""])[0].strip()
        if not new_s:
            return "生徒名を入力してください"
        if new_st not in _STATUS_NAMES:
            return "ステータス名が不正です"
        costumes = _parse_costumes(params, "add")
        if not costumes:
            return "衣装を1つ以上入力してください"
        _rebuild_preset(new_s, new_st, new_s, new_st, costumes)
        return f"「{new_s}({new_st})」を追加しました"

    @staticmethod
    def _preset_delete(params: dict) -> str:
        s = params.get("student", [""])[0]
        st = params.get("status", [""])[0]
        if not s or not st:
            return "対象が指定されていません"
        delete_preset(s, st)
        return f"「{s}({st})」を削除しました"

    @staticmethod
    def _preset_set_approval(params: dict) -> str:
        s = params.get("student", [""])[0]
        st = params.get("status", [""])[0]
        approved = params.get("approved", ["0"])[0] == "1"
        if not s or not st:
            return "対象が指定されていません"
        set_preset_approved(s, st, approved)
        return f"「{s}({st})」を{'承認' if approved else '承認解除'}しました"

    @staticmethod
    def _priority_save(params: dict) -> str:
        s = params.get("student_name", [""])[0].strip()
        orig = params.get("orig_student", [""])[0].strip()
        pri_raw = params.get("priority", [""])[0].strip()
        if not s or not pri_raw:
            return "生徒名と優先度を入力してください"
        try:
            pri = int(pri_raw)
        except ValueError:
            return "優先度は整数で入力してください"
        if orig and orig != s:
            delete_priority(orig)
        upsert_priority(s, pri)
        return f"優先度を保存しました（{s} = {pri}）"

    @staticmethod
    def _priority_delete(params: dict) -> str:
        s = params.get("student_name", [""])[0]
        if not s:
            return "生徒名が指定されていません"
        delete_priority(s)
        return f"優先度を削除しました（{s}）"


def _parse_costumes_for_save(params: dict) -> list[dict]:
    """編集フォームの prefix は p<pi> だが、フォーム単位の送信なので
    送られてきた最初の prefix を検出して解析する。"""
    prefixes = set()
    for k in params:
        if "_cname_" in k:
            prefixes.add(k.split("_cname_")[0])
    for pref in prefixes:
        costumes = _parse_costumes(params, pref)
        if costumes:
            return costumes
    return []


def _open_browser(url: str) -> None:
    cmd_exe = shutil.which("cmd.exe")
    if cmd_exe:
        try:
            subprocess.Popen(
                [cmd_exe, "/C", "start", url.replace("&", "^&")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    webbrowser.open(url)


def main():
    if not _DB_URL:
        print("エラー: DATABASE_URL が設定されていません")
        print(".env ファイルを確認してください")
        return
    try:
        _ensure_tables()
    except Exception as e:
        print(f"エラー: テーブル初期化に失敗しました: {e}")
        return

    print(f"接続先: {_DB_URL.split('@')[-1] if '@' in _DB_URL else '(unknown)'}")
    port = 18766
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"プリセットDB管理サーバーを起動しました: {url}")
    print("Ctrl+C で停止します")
    threading.Timer(0.5, lambda: _open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
        server.server_close()


if __name__ == "__main__":
    main()
