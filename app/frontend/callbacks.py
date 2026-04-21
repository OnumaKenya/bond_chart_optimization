"""サーバーサイドコールバック。"""

from dash import html, callback, Input, Output, State, ALL, ctx, no_update
from dash.exceptions import PreventUpdate

from app.backend.student import BOND_RANGES
from app.backend.user_presets import (
    get_all_presets_for_dropdown,
    get_preset_data,
    save_user_preset,
)
from app.frontend.layout import (
    make_student_card,
    _make_bond_rank_input,
    _default_costume_name,
)


def _sort_options_with_favorites(options, favorites):
    """★付きお気に入りを先頭に固定したオプションリストを返す。"""
    fav_set = set(favorites or [])
    favs, others = [], []
    for opt in options:
        value = opt["value"]
        label = opt["label"]
        if value in fav_set:
            new_label = label if label.startswith("★") else f"★ {label}"
            favs.append({**opt, "label": new_label})
        else:
            others.append(opt)
    fav_order = {v: i for i, v in enumerate(favorites or [])}
    favs.sort(key=lambda o: fav_order.get(o["value"], 0))
    return favs + others


def _build_priority_data(order, costume_map):
    """Store に保存する優先度データを構築する。"""
    return [
        {"idx": idx, "name": costume_map.get(idx) or _default_costume_name(idx)}
        for idx in order
    ]


def _make_priority_cards(priority_data):
    """上下ボタン付き優先度カードリストを生成する。"""
    n = len(priority_data)
    btn_style = {
        "background": "none",
        "border": "1px solid #ccc",
        "borderRadius": "4px",
        "cursor": "pointer",
        "padding": "2px 8px",
        "fontSize": "0.8rem",
        "lineHeight": "1",
    }
    items = []
    for pos, entry in enumerate(priority_data):
        idx = entry["idx"] if isinstance(entry, dict) else entry
        name = entry["name"] if isinstance(entry, dict) else _default_costume_name(idx)
        items.append(
            html.Div(
                [
                    html.Span(
                        f"{pos + 1}.",
                        style={
                            "fontWeight": "bold",
                            "color": "#888",
                            "marginRight": "6px",
                            "minWidth": "20px",
                        },
                    ),
                    html.Span(name, style={"flex": "1"}),
                    html.Button(
                        "▲",
                        id={"type": "priority-up", "index": idx},
                        n_clicks=0,
                        disabled=pos == 0,
                        style=btn_style,
                    ),
                    html.Button(
                        "▼",
                        id={"type": "priority-down", "index": idx},
                        n_clicks=0,
                        disabled=pos == n - 1,
                        style=btn_style,
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "6px",
                    "padding": "6px 12px",
                    "background": "#e8f5e9",
                    "border": "1px solid #a5d6a7",
                    "borderRadius": "6px",
                    "fontSize": "0.85rem",
                },
            )
        )
    return items


@callback(
    Output("students-container", "children"),
    Output("student-indices", "data"),
    Output("next-student-index", "data"),
    Output("bond-rank-container", "children"),
    Output("costume-priority-order", "data"),
    Output("chart-result", "children", allow_duplicate=True),
    Input("add-student-btn", "n_clicks"),
    Input({"type": "remove-student", "index": ALL}, "n_clicks"),
    Input("load-preset-btn", "n_clicks"),
    State("student-indices", "data"),
    State("next-student-index", "data"),
    State("students-container", "children"),
    State("preset-dropdown", "value"),
    State({"type": "bond-rank", "index": ALL}, "value"),
    State({"type": "bond-rank", "index": ALL}, "id"),
    State({"type": "costume", "index": ALL}, "value"),
    State({"type": "costume", "index": ALL}, "id"),
    State("costume-priority-order", "data"),
    prevent_initial_call=True,
)
def update_students(
    add_clicks,
    remove_clicks,
    load_preset_clicks,
    indices,
    next_idx,
    children,
    preset_name,
    rank_values,
    rank_ids,
    costume_values,
    costume_ids,
    priority_order,
):
    trigger = ctx.triggered_id

    # 現在のユーザー入力値をマップに保持
    rank_map = {rid["index"]: rv for rv, rid in zip(rank_values, rank_ids)}
    costume_map = {cid["index"]: cv for cv, cid in zip(costume_values, costume_ids)}

    # priority_order から idx リストを取得
    old_idx_order = [e["idx"] if isinstance(e, dict) else e for e in priority_order]

    if trigger == "add-student-btn":
        indices.append(next_idx)
        children.append(make_student_card(next_idx))
        rank_children = [
            _make_bond_rank_input(
                idx,
                costume_name=costume_map.get(idx, ""),
                value=rank_map.get(idx, 20),
            )
            for idx in indices
        ]
        new_order = [i for i in old_idx_order if i in indices] + [next_idx]
        priority_data = _build_priority_data(new_order, costume_map)
        return (
            children,
            indices,
            next_idx + 1,
            rank_children,
            priority_data,
            no_update,
        )

    if isinstance(trigger, dict) and trigger.get("type") == "remove-student":
        triggered_value = ctx.triggered[0]["value"] if ctx.triggered else None
        if not triggered_value:
            raise PreventUpdate
        if len(indices) <= 1:
            raise PreventUpdate
        remove_idx = trigger["index"]
        indices = [i for i in indices if i != remove_idx]
        children = [
            c
            for c in children
            if not (
                c["props"]["id"].get("type") == "student-card"
                and c["props"]["id"].get("index") == remove_idx
            )
        ]
        rank_children = [
            _make_bond_rank_input(
                idx,
                costume_name=costume_map.get(idx, ""),
                value=rank_map.get(idx, 20),
            )
            for idx in indices
        ]
        new_order = [i for i in old_idx_order if i != remove_idx]
        priority_data = _build_priority_data(new_order, costume_map)
        return (
            children,
            indices,
            next_idx,
            rank_children,
            priority_data,
            no_update,
        )

    if trigger == "load-preset-btn":
        if not preset_name:
            raise PreventUpdate
        result = get_preset_data(preset_name)
        if not result:
            raise PreventUpdate
        display_name, students = result
        new_children = []
        new_indices = []
        new_rank_children = []
        preset_costume_map = {}
        for i, s in enumerate(students):
            new_children.append(
                make_student_card(
                    i,
                    costume_name=s["costume_name"],
                    bond_bonuses=s["bond_bonuses"],
                )
            )
            new_indices.append(i)
            new_rank_children.append(
                _make_bond_rank_input(
                    i,
                    costume_name=s["costume_name"],
                )
            )
            preset_costume_map[i] = s["costume_name"]
        new_order = list(range(len(students)))
        priority_data = _build_priority_data(new_order, preset_costume_map)
        msg = html.P(
            f"プリセット「{display_name}」を読み込みました。",
            style={
                "color": "#27ae60",
                "fontWeight": "bold",
                "margin": "8px 0",
            },
        )
        return (
            new_children,
            new_indices,
            len(students),
            new_rank_children,
            priority_data,
            msg,
        )

    raise PreventUpdate


@callback(
    Output({"type": "bond-rank-label", "index": ALL}, "children"),
    Input({"type": "costume", "index": ALL}, "value"),
    State({"type": "costume", "index": ALL}, "id"),
)
def sync_bond_rank_labels(costume_values, costume_ids):
    return [
        v or _default_costume_name(cid["index"])
        for v, cid in zip(costume_values, costume_ids)
    ]


_BOND_RANK_BASE_STYLE = {"width": "50px", "textAlign": "center"}
_BOND_RANK_ERROR_STYLE = {**_BOND_RANK_BASE_STYLE, "border": "2px solid red", "color": "red"}


@callback(
    Output({"type": "bond-rank", "index": ALL}, "style"),
    Input({"type": "bond-rank", "index": ALL}, "value"),
)
def validate_bond_rank_style(values):
    return [
        _BOND_RANK_ERROR_STYLE
        if v is None or not isinstance(v, (int, float)) or v < 1 or v > 50
        else _BOND_RANK_BASE_STYLE
        for v in values
    ]




@callback(
    Output("costume-priority-container", "children"),
    Output("costume-priority-order", "data", allow_duplicate=True),
    Input("costume-priority-order", "data"),
    Input({"type": "priority-up", "index": ALL}, "n_clicks"),
    Input({"type": "priority-down", "index": ALL}, "n_clicks"),
    State({"type": "priority-up", "index": ALL}, "id"),
    State({"type": "priority-down", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def render_and_reorder_priority(
    priority_data, up_clicks, down_clicks, up_ids, down_ids
):
    trigger = ctx.triggered_id

    # 上下ボタンによる並べ替え
    if isinstance(trigger, dict):
        data = list(priority_data)
        move_idx = trigger["index"]
        pos = next(
            i
            for i, e in enumerate(data)
            if (e["idx"] if isinstance(e, dict) else e) == move_idx
        )
        if trigger["type"] == "priority-up" and pos > 0:
            data[pos], data[pos - 1] = data[pos - 1], data[pos]
        elif trigger["type"] == "priority-down" and pos < len(data) - 1:
            data[pos], data[pos + 1] = data[pos + 1], data[pos]
        return _make_priority_cards(data), data

    # Store 変更によるレンダリング
    return _make_priority_cards(priority_data), no_update


@callback(
    Output("autosave", "data"),
    Input({"type": "costume", "index": ALL}, "value"),
    Input({"type": "bond-rank", "index": ALL}, "value"),
    Input("costume-priority-order", "data"),
    Input("bond50-penalty", "value"),
    Input("preset-dropdown", "value"),
    State("student-indices", "data"),
    State("next-student-index", "data"),
    State({"type": "costume", "index": ALL}, "id"),
    State({"type": "bond-rank", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def save_autosave(
    costume_values,
    rank_values,
    priority_data,
    penalty,
    preset_value,
    indices,
    next_index,
    costume_ids,
    rank_ids,
):
    if not indices:
        raise PreventUpdate
    costumes = {str(cid["index"]): cv for cv, cid in zip(costume_values, costume_ids)}
    ranks = {str(rid["index"]): rv for rv, rid in zip(rank_values, rank_ids)}
    return {
        "indices": indices,
        "next_index": next_index,
        "costumes": costumes,
        "ranks": ranks,
        "priority": priority_data,
        "penalty": penalty,
        "preset_value": preset_value,
    }


@callback(
    Output("students-container", "children", allow_duplicate=True),
    Output("student-indices", "data", allow_duplicate=True),
    Output("next-student-index", "data", allow_duplicate=True),
    Output("bond-rank-container", "children", allow_duplicate=True),
    Output("costume-priority-order", "data", allow_duplicate=True),
    Output("bond50-penalty", "value", allow_duplicate=True),
    Output("preset-dropdown", "value"),
    Input("autosave-init", "n_intervals"),
    State("autosave", "data"),
    prevent_initial_call=True,
)
def restore_autosave(_n, data):
    if not data or not data.get("indices"):
        raise PreventUpdate

    penalty = data.get("penalty", 0)
    preset_value = data.get("preset_value")

    # プリセットが選択されていればプリセットから復元
    if preset_value:
        result = get_preset_data(preset_value)
        if result:
            _, students = result
            indices = list(range(len(students)))
            next_index = len(students)
            ranks = data.get("ranks") or {}
            student_children = [
                make_student_card(
                    i,
                    costume_name=s["costume_name"],
                    bond_bonuses=s["bond_bonuses"],
                )
                for i, s in enumerate(students)
            ]
            rank_children = [
                _make_bond_rank_input(
                    i,
                    costume_name=s["costume_name"],
                    value=ranks.get(str(i)) or 20,
                )
                for i, s in enumerate(students)
            ]
            priority = [
                {"idx": i, "name": s["costume_name"]}
                for i, s in enumerate(students)
            ]
            return (
                student_children,
                indices,
                next_index,
                rank_children,
                priority,
                penalty if penalty is not None else 0,
                preset_value,
            )

    # プリセット未選択: デフォルト状態（衣装1つ）
    raise PreventUpdate


@callback(
    Output("favorites", "data"),
    Output("fav-toggle-btn", "children"),
    Input("fav-toggle-btn", "n_clicks"),
    Input("preset-dropdown", "value"),
    State("favorites", "data"),
    prevent_initial_call=False,
)
def toggle_favorite(n_clicks, preset_value, favorites):
    favorites = list(favorites or [])
    trigger = ctx.triggered_id
    if trigger == "fav-toggle-btn":
        if not preset_value:
            raise PreventUpdate
        if preset_value in favorites:
            favorites.remove(preset_value)
        else:
            favorites.append(preset_value)
    star = "★" if preset_value and preset_value in favorites else "☆"
    return favorites, star


@callback(
    Output("preset-dropdown", "options"),
    Input("favorites", "data"),
    Input("submit-preset-status", "data"),
)
def render_preset_options(favorites, _submit_status):
    return _sort_options_with_favorites(get_all_presets_for_dropdown(), favorites or [])


@callback(
    Output("submit-feedback", "children"),
    Output("submit-preset-status", "data"),
    Input("submit-preset-btn", "submit_n_clicks"),
    State("submit-character-name", "value"),
    State("student-indices", "data"),
    State({"type": "costume", "index": ALL}, "value"),
    State({"type": "costume", "index": ALL}, "id"),
    State({"type": "bond", "range_idx": ALL, "index": ALL}, "value"),
    State({"type": "bond", "range_idx": ALL, "index": ALL}, "id"),
    prevent_initial_call=True,
)
def submit_preset(
    n_clicks,
    char_name,
    indices,
    costume_values,
    costume_ids,
    bond_values,
    bond_ids,
):
    if not char_name or not char_name.strip():
        return (
            html.Span("生徒名を入力してください。", style={"color": "red"}),
            no_update,
        )

    # 衣装データを組み立てる
    idx_order = [cid["index"] for cid in costume_ids]
    costume_map = {cid["index"]: cv for cv, cid in zip(costume_values, costume_ids)}
    bond_map = {}
    for idx in idx_order:
        bond_map[idx] = [0] * len(BOND_RANGES)
    for bid, bv in zip(bond_ids, bond_values):
        bond_map[bid["index"]][bid["range_idx"]] = bv or 0

    costumes = []
    for idx in idx_order:
        costumes.append(
            {
                "costume_name": costume_map.get(idx) or _default_costume_name(idx),
                "bond_bonuses": bond_map[idx],
            }
        )

    save_user_preset(char_name.strip(), costumes)
    return (
        html.Span(
            f"「{char_name.strip()}」を投稿しました。",
            style={"color": "#27ae60"},
        ),
        {"submitted": True},
    )
