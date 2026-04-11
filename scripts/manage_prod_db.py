#!/usr/bin/env python3
"""本番データベースのuser_presetsテーブルをGUIで管理するローカルツール。

使い方:
    python scripts/manage_prod_db.py

実行するとローカル HTTP サーバーが起動し、自動でブラウザが開きます。
"""

import json
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

_DB_URL = os.environ.get("PROD_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(_DB_URL)
        _conn.autocommit = True
    return _conn


def load_all_presets() -> list[dict]:
    cur = _get_conn().cursor()
    cur.execute(
        "SELECT key, character_name, costumes, approved, submitted_at "
        "FROM user_presets ORDER BY submitted_at"
    )
    rows = cur.fetchall()
    return [
        {
            "key": r[0],
            "character_name": r[1],
            "costumes": r[2],
            "approved": r[3],
            "submitted_at": r[4],
        }
        for r in rows
    ]


def update_preset(key: str, character_name: str, costumes: list, approved: bool):
    cur = _get_conn().cursor()
    cur.execute(
        "UPDATE user_presets SET character_name=%s, costumes=%s, approved=%s WHERE key=%s",
        (character_name, json.dumps(costumes, ensure_ascii=False), approved, key),
    )


def delete_preset(key: str):
    cur = _get_conn().cursor()
    cur.execute("DELETE FROM user_presets WHERE key=%s", (key,))


def insert_preset(
    key: str, character_name: str, costumes: list, approved: bool, submitted_at: str
):
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO user_presets (key, character_name, costumes, approved, submitted_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            key,
            character_name,
            json.dumps(costumes, ensure_ascii=False),
            approved,
            submitted_at,
        ),
    )


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


_STYLE = """
<style>
  * { box-sizing: border-box; }
  body { font-family: sans-serif; max-width: 1200px; margin: 30px auto; padding: 0 20px;
         background: #f5f5f5; }
  h1 { color: #333; }
  h2 { font-size: 1.1rem; color: #333; margin-bottom: 8px; }
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
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
           font-size: 0.75rem; }
  .badge-true { background: #d4edda; color: #155724; }
  .badge-false { background: #fff3cd; color: #856404; }
  button { cursor: pointer; border: none; padding: 6px 14px; border-radius: 4px;
           font-size: 0.85rem; color: white; }
  .btn-save { background: #27ae60; }
  .btn-delete { background: #e74c3c; }
  .btn-add { background: #2980b9; padding: 8px 20px; font-size: 0.95rem; margin-top: 12px; }
  .btn-add-costume { background: #27ae60; font-size: 0.8rem; padding: 4px 10px; }
  .btn-remove-costume { background: #e74c3c; font-size: 0.75rem; padding: 3px 8px; }
  .btn-toggle { padding: 4px 12px; font-size: 0.8rem; }
  .btn-toggle-on { background: #27ae60; }
  .btn-toggle-off { background: #95a5a6; }
  input[type=text], input[type=number] {
    padding: 5px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
  input[type=text] { width: 100%; }
  input[type=number] { width: 52px; text-align: center; }
  input[type=number]::-webkit-inner-spin-button,
  input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  input[type=number] { -moz-appearance: textbox; appearance: textbox; }
  .costume-row { display: flex; gap: 4px; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
  .costume-row input[type=text] { width: 90px; flex-shrink: 0; }
  .actions { display: flex; gap: 6px; align-items: center; }
  form { margin: 0; }
  .section { margin-top: 24px; }
  .add-form { background: white; padding: 16px; border-radius: 8px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .add-form label { display: block; font-weight: bold; margin-top: 10px;
                    margin-bottom: 4px; font-size: 0.85rem; }
  .range-labels { display: flex; gap: 4px; margin-bottom: 4px; margin-left: 94px; }
  .range-labels span { font-size: 0.65rem; color: #888; width: 52px; text-align: center; }
  .footer { text-align: center; color: #999; font-size: 0.8rem; margin-top: 30px; }
  .empty { text-align: center; color: #888; padding: 30px; }
  .key-cell { font-size: 0.75rem; color: #888; word-break: break-all; max-width: 140px; }
  .submitted-cell { font-size: 0.75rem; color: #888; white-space: nowrap; }
</style>
"""

_RANGE_LABELS = ["2~5", "6~10", "11~15", "16~20", "21~30", "31~40", "41~50"]


def _render_costume_row_html(prefix: str, idx: int, costume: dict | None = None) -> str:
    cname = html_escape(costume["costume_name"]) if costume else ""
    bonuses = costume["bond_bonuses"] if costume else [0] * 7
    inputs = f'<input type="text" name="{prefix}_cname_{idx}" value="{cname}" placeholder="衣装名">'
    for j in range(7):
        v = bonuses[j] if j < len(bonuses) else 0
        inputs += (
            f'<input type="number" name="{prefix}_b{j}_{idx}" value="{v}" min="0">'
        )
    remove_btn = f' <button type="button" class="btn-remove-costume" onclick="this.parentElement.remove()">✕</button>'
    return f'<div class="costume-row">{inputs}{remove_btn}</div>'


def _render_range_header() -> str:
    labels = "".join(f"<span>{l}</span>" for l in _RANGE_LABELS)
    return f'<div class="range-labels"><span style="width:90px"></span>{labels}</div>'


def render_page(message: str = "", msg_type: str = "ok") -> str:
    presets = load_all_presets()
    msg_html = ""
    if message:
        cls = "msg-ok" if msg_type == "ok" else "msg-err"
        msg_html = f'<div class="msg {cls}">{html_escape(message)}</div>'

    # --- Preset table ---
    if not presets:
        table_html = '<div class="empty">レコードがありません。</div>'
    else:
        rows = ""
        for p in presets:
            ekey = html_escape(p["key"])
            ename = html_escape(p["character_name"])
            approved = p["approved"]
            submitted = html_escape(p.get("submitted_at", ""))

            # Costume edit rows
            costume_html = _render_range_header()
            for i, c in enumerate(p["costumes"]):
                costume_html += _render_costume_row_html(ekey, i, c)

            add_costume_js = f"addCostumeToEdit(this.parentElement.querySelector('.costumes-container'), '{ekey}')"

            approved_badge = (
                f'<span class="badge badge-true">承認済</span>'
                if approved
                else f'<span class="badge badge-false">未承認</span>'
            )

            toggle_val = "false" if approved else "true"
            toggle_label = "未承認にする" if approved else "承認する"
            toggle_cls = "btn-toggle-off" if approved else "btn-toggle-on"

            rows += f"""<tr>
              <td class="key-cell">{ekey}</td>
              <td>
                <form method="post" action="/update" id="form_{ekey}">
                  <input type="hidden" name="key" value="{ekey}">
                  <input type="hidden" name="approved" value="{"true" if approved else "false"}">
                  <input type="text" name="character_name" value="{ename}" style="width:140px;margin-bottom:6px">
                  <div class="costumes-container">
                    {costume_html}
                  </div>
                  <button type="button" class="btn-add-costume" onclick="{add_costume_js}">+ 衣装</button>
                </form>
              </td>
              <td style="text-align:center">
                {approved_badge}<br><br>
                <form method="post" action="/toggle_approved" style="display:inline">
                  <input type="hidden" name="key" value="{ekey}">
                  <input type="hidden" name="approved" value="{toggle_val}">
                  <button type="submit" class="btn-toggle {toggle_cls}">{toggle_label}</button>
                </form>
              </td>
              <td class="submitted-cell">{submitted}</td>
              <td>
                <div class="actions" style="flex-direction:column;gap:8px">
                  <button type="submit" form="form_{ekey}" class="btn-save">保存</button>
                  <form method="post" action="/delete"
                    onsubmit="return confirm('「{ename}」を削除しますか？')">
                    <input type="hidden" name="key" value="{ekey}">
                    <button type="submit" class="btn-delete">削除</button>
                  </form>
                </div>
              </td>
            </tr>"""

        table_html = f"""<table><thead><tr>
          <th style="width:120px">Key</th>
          <th>生徒 / 衣装</th>
          <th style="width:90px">状態</th>
          <th style="width:100px">投稿日時</th>
          <th style="width:80px">操作</th>
        </tr></thead><tbody>{rows}</tbody></table>"""

    # --- Add form ---
    add_form = f"""
    <div class="section">
      <h2>新規レコード追加</h2>
      <div class="add-form">
        <form method="post" action="/add" id="add-form">
          <label>生徒名</label>
          <input type="text" name="character_name" required style="width:200px">
          <label>承認</label>
          <select name="approved" style="padding:5px;font-size:0.85rem">
            <option value="true" selected>承認済</option>
            <option value="false">未承認</option>
          </select>
          <label>衣装（ボーナス値: {", ".join(_RANGE_LABELS)}）</label>
          {_render_range_header()}
          <div id="add-costumes-container">
            <div class="costume-row">
              <input type="text" name="add_cname_0" placeholder="衣装名" required>
              <input type="number" name="add_b0_0" value="0" min="0">
              <input type="number" name="add_b1_0" value="0" min="0">
              <input type="number" name="add_b2_0" value="0" min="0">
              <input type="number" name="add_b3_0" value="0" min="0">
              <input type="number" name="add_b4_0" value="0" min="0">
              <input type="number" name="add_b5_0" value="0" min="0">
              <input type="number" name="add_b6_0" value="0" min="0">
            </div>
          </div>
          <button type="button" class="btn-add-costume" onclick="addCostumeToAdd()">+ 衣装追加</button>
          <br>
          <button type="submit" class="btn-add">追加</button>
        </form>
      </div>
    </div>"""

    script = """
    <script>
    var addIdx = 1;
    function addCostumeToAdd() {
      var container = document.getElementById('add-costumes-container');
      var row = document.createElement('div');
      row.className = 'costume-row';
      row.innerHTML = '<input type="text" name="add_cname_' + addIdx + '" placeholder="衣装名" required>'
        + '<input type="number" name="add_b0_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b1_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b2_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b3_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b4_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b5_' + addIdx + '" value="0" min="0">'
        + '<input type="number" name="add_b6_' + addIdx + '" value="0" min="0">'
        + ' <button type="button" class="btn-remove-costume" onclick="this.parentElement.remove()">✕</button>';
      container.appendChild(row);
      addIdx++;
    }

    var editCounters = {};
    function addCostumeToEdit(container, prefix) {
      if (!(prefix in editCounters)) {
        editCounters[prefix] = container.querySelectorAll('.costume-row').length;
      }
      var idx = editCounters[prefix];
      var row = document.createElement('div');
      row.className = 'costume-row';
      row.innerHTML = '<input type="text" name="' + prefix + '_cname_' + idx + '" placeholder="衣装名">'
        + '<input type="number" name="' + prefix + '_b0_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b1_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b2_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b3_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b4_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b5_' + idx + '" value="0" min="0">'
        + '<input type="number" name="' + prefix + '_b6_' + idx + '" value="0" min="0">'
        + ' <button type="button" class="btn-remove-costume" onclick="this.parentElement.remove()">✕</button>';
      container.appendChild(row);
      editCounters[prefix] = idx + 1;
    }
    </script>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>本番DB管理 - user_presets</title>{_STYLE}</head><body>
    <h1>本番DB管理 - user_presets</h1>
    <div class="summary">接続先: {html_escape(_DB_URL.split("@")[-1] if "@" in _DB_URL else "(unknown)")}</div>
    {msg_html}
    <div class="summary">全 {len(presets)} 件</div>
    {table_html}
    {add_form}
    {script}
    <div class="footer">Ctrl+C で停止</div>
    </body></html>"""


def _parse_costumes_from_params(params: dict, prefix: str) -> list[dict]:
    """Parse costume rows from form params with given prefix."""
    costumes = []
    idx = 0
    while True:
        cname_key = f"{prefix}_cname_{idx}"
        if cname_key not in params:
            break
        cname = params[cname_key][0].strip()
        if cname:
            bonuses = []
            for j in range(7):
                bkey = f"{prefix}_b{j}_{idx}"
                vals = params.get(bkey, ["0"])
                bonuses.append(int(vals[0]) if vals[0] else 0)
            costumes.append({"costume_name": cname, "bond_bonuses": bonuses})
        idx += 1
    return costumes


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args, **_kwargs):
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
            msg = parse_qs(parsed.query).get("msg", [""])[0]
            msg_type = parse_qs(parsed.query).get("type", ["ok"])[0]
            self._send_html(render_page(msg, msg_type))
        else:
            self._send_html("Not Found", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        path = urlparse(self.path).path
        msg = ""
        msg_type = "ok"

        try:
            if path == "/update":
                msg = self._handle_update(params)
            elif path == "/delete":
                msg = self._handle_delete(params)
            elif path == "/add":
                msg = self._handle_add(params)
            elif path == "/toggle_approved":
                msg = self._handle_toggle(params)
            else:
                msg = "不明な操作です"
                msg_type = "err"
        except Exception as e:
            msg = f"エラー: {e}"
            msg_type = "err"

        self._redirect(f"/?msg={quote(msg)}&type={msg_type}")

    @staticmethod
    def _handle_update(params: dict) -> str:
        key = params.get("key", [""])[0]
        character_name = params.get("character_name", [""])[0].strip()
        approved = params.get("approved", ["false"])[0] == "true"
        if not key or not character_name:
            return "キーまたは生徒名が空です"
        costumes = _parse_costumes_from_params(params, key)
        if not costumes:
            return "衣装が1つもありません"
        update_preset(key, character_name, costumes, approved)
        return f"「{character_name}」を更新しました"

    @staticmethod
    def _handle_delete(params: dict) -> str:
        key = params.get("key", [""])[0]
        if not key:
            return "キーが指定されていません"
        delete_preset(key)
        return f"削除しました (key: {key})"

    @staticmethod
    def _handle_add(params: dict) -> str:
        character_name = params.get("character_name", [""])[0].strip()
        if not character_name:
            return "生徒名を入力してください"
        approved = params.get("approved", ["false"])[0] == "true"
        costumes = _parse_costumes_from_params(params, "add")
        if not costumes:
            return "衣装を1つ以上入力してください"
        import time

        key = f"{character_name}_{int(time.time())}"
        submitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        insert_preset(key, character_name, costumes, approved, submitted_at)
        return f"「{character_name}」を追加しました"

    @staticmethod
    def _handle_toggle(params: dict) -> str:
        key = params.get("key", [""])[0]
        approved = params.get("approved", ["false"])[0] == "true"
        if not key:
            return "キーが指定されていません"
        cur = _get_conn().cursor()
        cur.execute("UPDATE user_presets SET approved=%s WHERE key=%s", (approved, key))
        status = "承認済" if approved else "未承認"
        return f"ステータスを「{status}」に変更しました"


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
        print("エラー: PROD_DATABASE_URL または DATABASE_URL が設定されていません")
        print(".env ファイルを確認してください")
        return

    print(f"接続先: {_DB_URL.split('@')[-1] if '@' in _DB_URL else '(unknown)'}")
    port = 18766
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"本番DB管理サーバーを起動しました: {url}")
    print("Ctrl+C で停止します")
    threading.Timer(0.5, lambda: _open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
        server.server_close()


if __name__ == "__main__":
    main()
