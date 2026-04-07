"""GitHub リポジトリへの user_presets.json 同期。

書き込みのたびに schedule_sync() を呼び出し、
デバウンス後に GitHub API でブランチを作成し PR を出す。
"""

import atexit
import base64
import json
import logging
import os
import threading
import time

_logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 30
_FILE_PATH = "data/user_presets.json"
_BASE_BRANCH = "master"

_timer: threading.Timer | None = None
_timer_lock = threading.Lock()


def _get_config() -> tuple[str, str] | None:
    """環境変数から GitHub トークンとリポジトリを取得する。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return None
    return token, repo


def _local_content() -> bytes:
    """ローカルファイルの内容を読み取る。"""
    from app.backend.user_presets import _JSON_PATH

    if not _JSON_PATH.exists():
        return b'{"presets": {}}\n'
    return _JSON_PATH.read_bytes()


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def push_to_github() -> None:
    """user_presets.json の変更をブランチに push し PR を作成する。"""
    config = _get_config()
    if not config:
        _logger.debug("GitHub sync skipped: GITHUB_TOKEN or GITHUB_REPO not set")
        return

    token, repo = config
    import requests

    hdrs = _headers(token)
    api = f"https://api.github.com/repos/{repo}"
    local_bytes = _local_content()
    local_presets = json.loads(local_bytes).get("presets", {})

    if not local_presets:
        _logger.debug("GitHub sync: no presets to push")
        return

    # --- ベースブランチの現在のファイルと比較 ---
    try:
        resp = requests.get(
            f"{api}/contents/{_FILE_PATH}",
            headers=hdrs,
            params={"ref": _BASE_BRANCH},
            timeout=15,
        )
        if resp.status_code == 200:
            remote_content = base64.b64decode(resp.json()["content"])
            remote_presets = json.loads(remote_content).get("presets", {})
            if local_presets == remote_presets:
                _logger.debug("GitHub sync: no changes to push")
                return
        elif resp.status_code != 404:
            _logger.warning("GitHub GET failed: %d %s", resp.status_code, resp.text[:200])
            return
    except requests.RequestException as e:
        _logger.warning("GitHub GET error: %s", e)
        return

    # --- ベースブランチの HEAD SHA を取得 ---
    try:
        resp = requests.get(f"{api}/git/ref/heads/{_BASE_BRANCH}", headers=hdrs, timeout=15)
        if resp.status_code != 200:
            _logger.warning("GitHub get ref failed: %d", resp.status_code)
            return
        base_sha = resp.json()["object"]["sha"]
    except requests.RequestException as e:
        _logger.warning("GitHub get ref error: %s", e)
        return

    # --- ブランチ作成 ---
    branch_name = f"sync/user-presets-{int(time.time())}"
    try:
        resp = requests.post(
            f"{api}/git/refs",
            headers=hdrs,
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            _logger.warning("GitHub create branch failed: %d %s", resp.status_code, resp.text[:200])
            return
    except requests.RequestException as e:
        _logger.warning("GitHub create branch error: %s", e)
        return

    # --- ファイルを更新 (ブランチ上) ---
    try:
        # ブランチ上の現在のファイル SHA を取得
        resp = requests.get(
            f"{api}/contents/{_FILE_PATH}",
            headers=hdrs,
            params={"ref": branch_name},
            timeout=15,
        )
        file_sha = resp.json().get("sha") if resp.status_code == 200 else None

        payload = {
            "message": "sync user_presets.json",
            "content": base64.b64encode(local_bytes).decode(),
            "branch": branch_name,
        }
        if file_sha:
            payload["sha"] = file_sha

        resp = requests.put(f"{api}/contents/{_FILE_PATH}", headers=hdrs, json=payload, timeout=15)
        if resp.status_code not in (200, 201):
            _logger.warning("GitHub PUT failed: %d %s", resp.status_code, resp.text[:200])
            return
    except requests.RequestException as e:
        _logger.warning("GitHub PUT error: %s", e)
        return

    # --- PR 作成 ---
    try:
        resp = requests.post(
            f"{api}/pulls",
            headers=hdrs,
            json={
                "title": "sync: ユーザー投稿プリセットを同期",
                "body": "Render 上のユーザー投稿プリセットを自動同期します。",
                "head": branch_name,
                "base": _BASE_BRANCH,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            pr_url = resp.json().get("html_url", "")
            _logger.info("GitHub sync: PR created %s", pr_url)
        elif resp.status_code == 422:
            # 既に同内容の PR がある等
            _logger.info("GitHub sync: PR already exists or no diff")
        else:
            _logger.warning("GitHub PR create failed: %d %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        _logger.warning("GitHub PR create error: %s", e)


def schedule_sync() -> None:
    """デバウンス付きで GitHub 同期をスケジュールする。"""
    global _timer
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(_DEBOUNCE_SECONDS, push_to_github)
        _timer.daemon = True
        _timer.start()


def _flush_on_exit() -> None:
    """終了時に未 push のデータを同期する。"""
    global _timer
    with _timer_lock:
        if _timer is not None and _timer.is_alive():
            _timer.cancel()
            _timer = None
    push_to_github()


atexit.register(_flush_on_exit)
