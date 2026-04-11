"""プリセット管理画面。

Flask の route として登録される。パスワード保護されたWebページで
ユーザー投稿プリセットの閲覧・承認・削除を行う。
"""

import os
from functools import wraps
from html import escape

from flask import redirect, request, session, url_for

from app import app
from app.backend.student import BOND_RANGES
from app.backend.user_presets import (
    approve_preset,
    delete_preset,
    load_user_presets,
)

server = app.server
server.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
_ADMIN_PASSWORD = os.environ.get("PRESET_ADMIN_TOKEN", "")


def _require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _ADMIN_PASSWORD:
            return "管理パスワードが設定されていません (PRESET_ADMIN_TOKEN)", 503
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return wrapper


@server.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not _ADMIN_PASSWORD:
        return "管理パスワードが設定されていません (PRESET_ADMIN_TOKEN)", 503
    error = ""
    if request.method == "POST":
        if request.form.get("password") == _ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_presets"))
        error = "パスワードが正しくありません"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>管理ログイン</title>
<style>
  body {{ font-family: sans-serif; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
  .login-box {{ background: #fff; padding: 32px; border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,.1); width: 320px; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 20px; text-align: center; }}
  input[type=password] {{ width: 100%; padding: 10px; border: 1px solid #ccc;
                          border-radius: 4px; font-size: 1rem; box-sizing: border-box; }}
  button {{ width: 100%; padding: 10px; margin-top: 12px; background: #4a90d9;
            color: #fff; border: none; border-radius: 4px; font-size: 1rem;
            cursor: pointer; }}
  button:hover {{ background: #3a7bc8; }}
  .error {{ color: red; font-size: 0.9rem; margin-top: 8px; }}
</style>
</head>
<body>
<div class="login-box">
  <h1>プリセット管理</h1>
  <form method="post">
    <input type="password" name="password" placeholder="パスワード" autofocus>
    <button type="submit">ログイン</button>
  </form>
  {"<p class='error'>" + escape(error) + "</p>" if error else ""}
</div>
</body>
</html>"""


@server.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@server.route("/admin/presets")
@_require_login
def admin_presets():
    presets = load_user_presets()

    range_headers = "".join(
        f"<th>絆{lo}~{hi}</th>" for lo, hi in BOND_RANGES
    )

    rows = ""
    for key, entry in sorted(
        presets.items(), key=lambda x: x[1].get("submitted_at", ""), reverse=True
    ):
        char_name = escape(entry["character_name"])
        approved = entry.get("approved", False)
        status = "承認済" if approved else "未承認"
        status_color = "#27ae60" if approved else "#e67e22"
        submitted = escape(entry.get("submitted_at", ""))

        # 衣装ごとの行
        costumes = entry.get("costumes", [])
        costume_rows = ""
        for c in costumes:
            cname = escape(c.get("costume_name", ""))
            bonus_cells = "".join(
                f"<td>{b}</td>" for b in c.get("bond_bonuses", [0] * 7)
            )
            costume_rows += f"<tr><td>{cname}</td>{bonus_cells}</tr>"

        ekey = escape(key)
        approve_btn = ""
        if not approved:
            approve_btn = (
                f'<form method="post" action="/admin/presets/action" style="display:inline">'
                f'<input type="hidden" name="key" value="{ekey}">'
                f'<input type="hidden" name="action" value="approve">'
                f'<button type="submit" class="btn btn-approve">承認</button></form>'
            )
        delete_btn = (
            f'<form method="post" action="/admin/presets/action" style="display:inline"'
            f' onsubmit="return confirm(\'削除しますか？\')">'
            f'<input type="hidden" name="key" value="{ekey}">'
            f'<input type="hidden" name="action" value="delete">'
            f'<button type="submit" class="btn btn-delete">削除</button></form>'
        )

        rows += f"""
        <div class="preset-card">
          <div class="preset-header">
            <span class="char-name">{char_name}</span>
            <span class="status" style="color:{status_color}">{status}</span>
            <span class="submitted">{submitted}</span>
            <span class="actions">{approve_btn} {delete_btn}</span>
          </div>
          <table class="costume-table">
            <thead><tr><th>衣装名</th>{range_headers}</tr></thead>
            <tbody>{costume_rows}</tbody>
          </table>
        </div>"""

    empty_msg = ""
    if not presets:
        empty_msg = '<p style="text-align:center;color:#888">投稿されたプリセットはありません。</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>プリセット管理</title>
<style>
  body {{ font-family: sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: center;
             margin-bottom: 20px; }}
  h1 {{ font-size: 1.4rem; margin: 0; }}
  .logout {{ color: #888; text-decoration: none; font-size: 0.9rem; }}
  .logout:hover {{ color: #333; }}
  .count {{ color: #888; font-size: 0.9rem; }}
  .preset-card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  padding: 16px; margin-bottom: 12px; }}
  .preset-header {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
                    margin-bottom: 10px; }}
  .char-name {{ font-weight: bold; font-size: 1.1rem; }}
  .status {{ font-size: 0.85rem; font-weight: bold; }}
  .submitted {{ color: #888; font-size: 0.8rem; }}
  .actions {{ margin-left: auto; display: flex; gap: 6px; }}
  .costume-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  .costume-table th, .costume-table td {{ border: 1px solid #ddd; padding: 4px 8px;
                                          text-align: center; }}
  .costume-table th {{ background: #f0f0f0; white-space: nowrap; }}
  .costume-table td:first-child {{ text-align: left; }}
  .btn {{ padding: 4px 14px; border: none; border-radius: 4px; cursor: pointer;
          font-size: 0.85rem; color: #fff; }}
  .btn-approve {{ background: #27ae60; }}
  .btn-approve:hover {{ background: #219a52; }}
  .btn-delete {{ background: #e74c3c; }}
  .btn-delete:hover {{ background: #c0392b; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>プリセット管理</h1>
    <span class="count">{len(presets)} 件</span>
    <a href="/admin/logout" class="logout">ログアウト</a>
  </div>
  {empty_msg}
  {rows}
</div>
</body>
</html>"""


@server.route("/admin/presets/action", methods=["POST"])
@_require_login
def admin_presets_action():
    key = request.form.get("key", "")
    action = request.form.get("action", "")
    if action == "approve":
        approve_preset(key)
    elif action == "delete":
        delete_preset(key)
    return redirect(url_for("admin_presets"))
