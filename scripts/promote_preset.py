#!/usr/bin/env python3
"""ユーザー投稿プリセットを公式プリセットに昇格させるローカル管理ツール。

使い方:
    python scripts/promote_preset.py

実行するとローカル HTTP サーバーが起動し、自動でブラウザが開きます。
"""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_BASE_DIR = Path(__file__).resolve().parent.parent
_PRESETS_PATH = _BASE_DIR / "data" / "presets.json"
_USER_PRESETS_PATH = _BASE_DIR / "data" / "user_presets.json"


def load_presets() -> dict:
    with open(_PRESETS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_presets(presets: dict) -> None:
    with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def load_user_presets() -> dict:
    if not _USER_PRESETS_PATH.exists():
        return {}
    with open(_USER_PRESETS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("presets", {})


def save_user_presets(presets: dict) -> None:
    with open(_USER_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, ensure_ascii=False, indent=2)


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
  body { font-family: sans-serif; max-width: 1000px; margin: 30px auto; padding: 0 20px;
         background: #f5f5f5; }
  h1 { color: #333; }
  .msg { padding: 10px; border-radius: 6px; margin: 12px 0; }
  .msg-ok { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
  table { border-collapse: collapse; width: 100%; background: white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th, td { border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 0.9rem;
           vertical-align: top; }
  th { background: #2ecc71; color: white; }
  tr:nth-child(even) { background: #f9f9f9; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
           font-size: 0.75rem; }
  .badge-pending { background: #fff3cd; color: #856404; }
  .badge-approved { background: #d4edda; color: #155724; }
  button { cursor: pointer; border: none; padding: 6px 14px; border-radius: 4px;
           font-size: 0.85rem; color: white; }
  .btn-approve { background: #27ae60; }
  .btn-promote { background: #2980b9; }
  .btn-delete { background: #e74c3c; }
  input[type=text] { padding: 6px; border: 1px solid #ccc; border-radius: 4px;
                     font-size: 0.85rem; width: 110px; }
  .actions { display: flex; flex-direction: column; gap: 6px; }
  .action-row { display: flex; gap: 4px; align-items: center; }
  .costume-list { font-size: 0.78rem; color: #555; line-height: 1.5; }
  form { margin: 0; }
  .empty { text-align: center; color: #888; padding: 30px; }
  .footer { text-align: center; color: #999; font-size: 0.8rem; margin-top: 30px; }
  .section { margin-top: 24px; }
  .section h2 { font-size: 1.1rem; color: #333; margin-bottom: 8px; }
  .add-form { background: white; padding: 16px; border-radius: 8px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .add-form label { display: block; font-weight: bold; margin-top: 10px;
                    margin-bottom: 4px; font-size: 0.85rem; }
  .add-form input[type=text], .add-form input[type=number] {
    padding: 6px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
  .add-form input[type=number] { width: 60px; text-align: center; }
  .costume-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px;
                 flex-wrap: wrap; }
  .costume-row input[type=text] { width: 100px; }
  .btn-add-costume { background: #27ae60; font-size: 0.8rem; padding: 4px 10px; }
  .btn-remove-costume { background: #e74c3c; font-size: 0.75rem; padding: 3px 8px; }
  .btn-register { background: #2980b9; padding: 8px 20px; font-size: 0.95rem; margin-top: 12px; }
  .range-labels { display: flex; gap: 6px; flex-wrap: wrap; }
  .range-labels span { font-size: 0.75rem; color: #888; width: 60px; text-align: center; }
  input[type=number]::-webkit-inner-spin-button,
  input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  input[type=number] { -moz-appearance: textbox; appearance: textbox; }
</style>
"""


def render_page(message: str = "") -> str:
    user_presets = load_user_presets()
    msg_html = (
        f'<div class="msg msg-ok">{html_escape(message)}</div>' if message else ""
    )

    if not user_presets:
        body = '<div class="empty">ユーザー投稿プリセットはありません。</div>'
    else:
        rows = ""
        for key, entry in user_presets.items():
            name = html_escape(entry["character_name"])
            costumes_html = "<br>".join(
                f"・{html_escape(c['costume_name'])}: {c['bond_bonuses']}"
                for c in entry["costumes"]
            )
            status = (
                '<span class="badge badge-approved">承認済</span>'
                if entry.get("approved")
                else '<span class="badge badge-pending">未承認</span>'
            )
            submitted = html_escape(entry.get("submitted_at", ""))
            ekey = html_escape(key)

            rows += f"""<tr>
              <td><strong>{name}</strong><br><div class="costume-list">{costumes_html}</div></td>
              <td>{status}<br><small>{submitted}</small></td>
              <td><div class="actions">
                <form method="post" action="/action" class="action-row">
                  <input type="hidden" name="key" value="{ekey}">
                  <input type="hidden" name="action" value="promote">
                  <input type="text" name="name" value="{name}">
                  <button type="submit" class="btn-promote">公式に昇格</button>
                </form>
                <div class="action-row">
                  <form method="post" action="/action">
                    <input type="hidden" name="key" value="{ekey}">
                    <input type="hidden" name="action" value="approve">
                    <button type="submit" class="btn-approve">承認</button>
                  </form>
                  <form method="post" action="/action"
                    onsubmit="return confirm('「{name}」を削除しますか？')">
                    <input type="hidden" name="key" value="{ekey}">
                    <input type="hidden" name="action" value="delete">
                    <button type="submit" class="btn-delete">削除</button>
                  </form>
                </div>
              </div></td>
            </tr>"""
        body = f"""<table><thead><tr>
          <th style="width:50%">生徒 / 衣装</th><th>状態</th><th>操作</th>
        </tr></thead><tbody>{rows}</tbody></table>"""

    # --- 公式プリセット一覧 ---
    presets = load_presets()
    preset_rows = ""
    for pname, costumes in presets.items():
        ename = html_escape(pname)
        cos_html = ", ".join(html_escape(c["costume_name"]) for c in costumes)
        preset_rows += f"""<tr>
          <td><strong>{ename}</strong></td>
          <td style="font-size:0.8rem">{cos_html}</td>
          <td>
            <form method="post" action="/action"
              onsubmit="return confirm('「{ename}」を削除しますか？')">
              <input type="hidden" name="action" value="delete_official">
              <input type="hidden" name="name" value="{ename}">
              <button type="submit" class="btn-delete">削除</button>
            </form>
          </td>
        </tr>"""

    official_section = f"""
    <div class="section">
      <h2>公式プリセット ({len(presets)}件)</h2>
      <table><thead><tr><th>生徒名</th><th>衣装</th><th>操作</th></tr></thead>
      <tbody>{preset_rows}</tbody></table>
    </div>"""

    # --- 直接登録フォーム ---
    add_form = """
    <div class="section">
      <h2>プリセットを直接登録</h2>
      <div class="add-form">
        <form method="post" action="/action" id="register-form">
          <input type="hidden" name="action" value="register">
          <label>生徒名</label>
          <input type="text" name="char_name" required style="width:200px">

          <label>衣装（ボーナス値: 絆2~5, 6~10, 11~15, 16~20, 21~30, 31~40, 41~50）</label>
          <div id="costumes-container">
            <div class="costume-row">
              <input type="text" name="costume_name" placeholder="衣装名" required>
              <input type="number" name="b0" value="0" min="0">
              <input type="number" name="b1" value="0" min="0">
              <input type="number" name="b2" value="0" min="0">
              <input type="number" name="b3" value="0" min="0">
              <input type="number" name="b4" value="0" min="0">
              <input type="number" name="b5" value="0" min="0">
              <input type="number" name="b6" value="0" min="0">
            </div>
          </div>
          <button type="button" class="btn-add-costume" onclick="addCostume()">+ 衣装追加</button>
          <br>
          <button type="submit" class="btn-register">公式プリセットに登録</button>
        </form>
      </div>
    </div>
    <script>
    function addCostume() {
      var container = document.getElementById('costumes-container');
      var row = document.createElement('div');
      row.className = 'costume-row';
      row.innerHTML = '<input type="text" name="costume_name" placeholder="衣装名" required>'
        + '<input type="number" name="b0" value="0" min="0">'
        + '<input type="number" name="b1" value="0" min="0">'
        + '<input type="number" name="b2" value="0" min="0">'
        + '<input type="number" name="b3" value="0" min="0">'
        + '<input type="number" name="b4" value="0" min="0">'
        + '<input type="number" name="b5" value="0" min="0">'
        + '<input type="number" name="b6" value="0" min="0">'
        + ' <button type="button" class="btn-remove-costume" onclick="this.parentElement.remove()">✕</button>';
      container.appendChild(row);
    }
    </script>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>プリセット管理</title>{_STYLE}</head><body>
    <h1>プリセット管理</h1>
    {msg_html}
    {body}
    {official_section}
    {add_form}
    <div class="footer">このウィンドウを閉じてサーバーを停止してください</div>
    </body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args, **_kwargs):
        pass  # ログを抑制

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
            self._send_html(render_page(msg))
        else:
            self._send_html("Not Found", 404)

    def do_POST(self):
        if self.path != "/action":
            self._send_html("Not Found", 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        action = params.get("action", [""])[0]
        key = params.get("key", [""])[0]
        name = params.get("name", [""])[0].strip()

        msg = ""

        if action == "register":
            msg = self._handle_register(params)
        elif action == "delete_official":
            msg = self._handle_delete_official(name)
        else:
            user_presets = load_user_presets()
            if key not in user_presets:
                msg = "プリセットが見つかりません"
            elif action == "approve":
                user_presets[key]["approved"] = True
                save_user_presets(user_presets)
                msg = f"「{user_presets[key]['character_name']}」を承認しました"
            elif action == "delete":
                del_name = user_presets[key]["character_name"]
                del user_presets[key]
                save_user_presets(user_presets)
                msg = f"「{del_name}」を削除しました"
            elif action == "promote":
                register_name = name or user_presets[key]["character_name"]
                presets = load_presets()
                presets[register_name] = user_presets[key]["costumes"]
                save_presets(presets)
                del user_presets[key]
                save_user_presets(user_presets)
                msg = f"「{register_name}」を公式プリセットに昇格しました"

        from urllib.parse import quote

        self._redirect(f"/?msg={quote(msg)}")

    @staticmethod
    def _handle_register(params: dict) -> str:
        char_name = params.get("char_name", [""])[0].strip()
        if not char_name:
            return "生徒名を入力してください"
        costume_names = params.get("costume_name", [])
        if not costume_names:
            return "衣装を1つ以上入力してください"
        costumes = []
        for i, cname in enumerate(costume_names):
            bonuses = []
            for j in range(7):
                vals = params.get(f"b{j}", [])
                v = int(vals[i]) if i < len(vals) and vals[i] else 0
                bonuses.append(v)
            costumes.append(
                {
                    "costume_name": cname.strip(),
                    "bond_bonuses": bonuses,
                }
            )
        presets = load_presets()
        presets[char_name] = costumes
        save_presets(presets)
        return f"「{char_name}」を公式プリセットに登録しました"

    @staticmethod
    def _handle_delete_official(name: str) -> str:
        if not name:
            return "生徒名が指定されていません"
        presets = load_presets()
        if name not in presets:
            return f"「{name}」が見つかりません"
        del presets[name]
        save_presets(presets)
        return f"「{name}」を公式プリセットから削除しました"


def _open_browser(url: str) -> None:
    """Windows 側のブラウザで URL を開く (WSL 対応)。"""
    import shutil
    import subprocess

    # WSL: cmd.exe 経由で Windows ブラウザを開く
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
    # フォールバック
    webbrowser.open(url)


def main():
    port = 18765
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"プリセット管理サーバーを起動しました: {url}")
    print("Ctrl+C で停止します")
    threading.Timer(0.5, lambda: _open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
        server.server_close()


if __name__ == "__main__":
    main()
