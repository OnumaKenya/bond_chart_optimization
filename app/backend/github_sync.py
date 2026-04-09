"""GitHub リポジトリへの user_presets.json 同期。

書き込みのたびに schedule_sync() を呼び出し、
デバウンス後に GitHub API でブランチを更新し PR を確認する。

固定ブランチ名 + 既存 PR 検索により、複数 PR が作成されるのを防ぐ。
"""

import atexit
import base64
import json
import logging
import os
import threading

_logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 30
_FILE_PATH = "data/user_presets.json"
_BASE_BRANCH = "master"
_SYNC_BRANCH = "sync/user-presets"

_timer: threading.Timer | None = None
_timer_lock = threading.Lock()
_push_lock = threading.Lock()  # push_to_github の同時実行を防ぐ


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
    """user_presets.json を sync ブランチに push し、PR がなければ作成する。"""
    if not _push_lock.acquire(blocking=False):
        _logger.debug("GitHub sync: already running, skip")
        return
    try:
        _push_to_github_inner()
    finally:
        _push_lock.release()


def _push_to_github_inner() -> None:
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

    # --- master のファイルと比較 ---
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
            _logger.warning(
                "GitHub GET (master) failed: %d %s", resp.status_code, resp.text[:200]
            )
            return
    except requests.RequestException as e:
        _logger.warning("GitHub GET (master) error: %s", e)
        return

    # --- master HEAD SHA を取得 ---
    try:
        resp = requests.get(
            f"{api}/git/ref/heads/{_BASE_BRANCH}", headers=hdrs, timeout=15
        )
        if resp.status_code != 200:
            _logger.warning("GitHub get base ref failed: %d", resp.status_code)
            return
        base_sha = resp.json()["object"]["sha"]
    except requests.RequestException as e:
        _logger.warning("GitHub get base ref error: %s", e)
        return

    # --- sync ブランチを master HEAD にリセット (force) ---
    sync_ref = f"heads/{_SYNC_BRANCH}"
    try:
        resp = requests.get(f"{api}/git/ref/{sync_ref}", headers=hdrs, timeout=15)
        if resp.status_code == 200:
            # ブランチ存在 → master HEAD に force update
            resp = requests.patch(
                f"{api}/git/refs/{sync_ref}",
                headers=hdrs,
                json={"sha": base_sha, "force": True},
                timeout=15,
            )
            if resp.status_code != 200:
                _logger.warning(
                    "GitHub force-update branch failed: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return
        elif resp.status_code == 404:
            # ブランチ未作成 → 新規作成
            resp = requests.post(
                f"{api}/git/refs",
                headers=hdrs,
                json={"ref": f"refs/{sync_ref}", "sha": base_sha},
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                _logger.warning(
                    "GitHub create branch failed: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return
        else:
            _logger.warning("GitHub get branch ref failed: %d", resp.status_code)
            return
    except requests.RequestException as e:
        _logger.warning("GitHub branch update error: %s", e)
        return

    # --- ファイルを sync ブランチに commit ---
    try:
        # ブランチ上の現在のファイル SHA を取得 (master と同じはず)
        resp = requests.get(
            f"{api}/contents/{_FILE_PATH}",
            headers=hdrs,
            params={"ref": _SYNC_BRANCH},
            timeout=15,
        )
        file_sha = resp.json().get("sha") if resp.status_code == 200 else None

        payload = {
            "message": "sync user_presets.json",
            "content": base64.b64encode(local_bytes).decode(),
            "branch": _SYNC_BRANCH,
        }
        if file_sha:
            payload["sha"] = file_sha

        resp = requests.put(
            f"{api}/contents/{_FILE_PATH}", headers=hdrs, json=payload, timeout=15
        )
        if resp.status_code not in (200, 201):
            _logger.warning(
                "GitHub PUT failed: %d %s", resp.status_code, resp.text[:200]
            )
            return
    except requests.RequestException as e:
        _logger.warning("GitHub PUT error: %s", e)
        return

    # --- 既存 PR を検索 ---
    owner = repo.split("/")[0]
    try:
        resp = requests.get(
            f"{api}/pulls",
            headers=hdrs,
            params={
                "state": "open",
                "head": f"{owner}:{_SYNC_BRANCH}",
                "base": _BASE_BRANCH,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            existing_prs = resp.json()
            if existing_prs:
                _logger.info(
                    "GitHub sync: existing PR updated %s",
                    existing_prs[0].get("html_url", ""),
                )
                return
    except requests.RequestException as e:
        _logger.warning("GitHub list PRs error: %s", e)
        # PR 検索失敗時は作成を試みる (重複は 422 で防がれる)

    # --- PR 作成 ---
    try:
        resp = requests.post(
            f"{api}/pulls",
            headers=hdrs,
            json={
                "title": "sync: ユーザー投稿プリセットを同期",
                "body": "Render 上のユーザー投稿プリセットを自動同期します。",
                "head": _SYNC_BRANCH,
                "base": _BASE_BRANCH,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            pr_url = resp.json().get("html_url", "")
            _logger.info("GitHub sync: PR created %s", pr_url)
        elif resp.status_code == 422:
            _logger.info("GitHub sync: PR already exists or no diff")
        else:
            _logger.warning(
                "GitHub PR create failed: %d %s", resp.status_code, resp.text[:200]
            )
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
    """終了時に保留中のタイマーがあれば即座に同期する。"""
    global _timer
    pending = False
    with _timer_lock:
        if _timer is not None and _timer.is_alive():
            _timer.cancel()
            _timer = None
            pending = True
    if pending:
        push_to_github()


atexit.register(_flush_on_exit)
