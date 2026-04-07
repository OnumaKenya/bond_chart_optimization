"""ユーザー投稿プリセット用 REST API。

Flask の route として登録される。
"""

import os
from functools import wraps

from flask import jsonify, request

from app import app
from app.backend.user_presets import (
    save_user_preset,
    approve_preset,
    delete_preset,
    load_user_presets,
)

server = app.server
_ADMIN_TOKEN = os.environ.get("PRESET_ADMIN_TOKEN", "")
_MAX_COSTUMES = 10
_MAX_BONUS = 50


def _require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _ADMIN_TOKEN:
            return jsonify(
                {"status": "error", "message": "admin token not configured"}
            ), 503
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {_ADMIN_TOKEN}":
            return jsonify({"status": "error", "message": "unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


def _validate_costumes(costumes: list) -> str | None:
    if not isinstance(costumes, list) or not (1 <= len(costumes) <= _MAX_COSTUMES):
        return f"costumes must be a list of 1-{_MAX_COSTUMES} items"
    for c in costumes:
        if not isinstance(c, dict):
            return "each costume must be a dict"
        if not isinstance(c.get("costume_name"), str) or not c["costume_name"].strip():
            return "costume_name is required"
        bb = c.get("bond_bonuses")
        if not isinstance(bb, list) or len(bb) != 7:
            return "bond_bonuses must be a list of 7 integers"
        for v in bb:
            if not isinstance(v, int) or v < 0 or v > _MAX_BONUS:
                return f"bond_bonuses values must be integers 0-{_MAX_BONUS}"
    return None


@server.route("/api/presets/submit", methods=["POST"])
def api_submit_preset():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "invalid JSON"}), 400
    char_name = data.get("character_name", "").strip()
    if not char_name:
        return jsonify(
            {"status": "error", "message": "character_name is required"}
        ), 400
    costumes = data.get("costumes", [])
    err = _validate_costumes(costumes)
    if err:
        return jsonify({"status": "error", "message": err}), 400
    for c in costumes:
        c["costume_name"] = c["costume_name"].strip()
    key = save_user_preset(char_name, costumes)
    return jsonify({"status": "ok", "key": key})


@server.route("/api/presets/admin", methods=["POST"])
@_require_admin
def api_admin_action():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "invalid JSON"}), 400
    action = data.get("action")
    key = data.get("key", "")
    if action == "approve":
        if approve_preset(key):
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "preset not found"}), 404
    if action == "delete":
        if delete_preset(key):
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "preset not found"}), 404
    return jsonify(
        {"status": "error", "message": "action must be 'approve' or 'delete'"}
    ), 400


@server.route("/api/presets/admin/list", methods=["GET"])
@_require_admin
def api_admin_list():
    presets = load_user_presets()
    return jsonify({"status": "ok", "presets": presets})
