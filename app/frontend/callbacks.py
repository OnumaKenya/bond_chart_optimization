"""サーバーサイドコールバック。"""

from dash import callback, Input, Output, State, ALL, ctx
from dash.exceptions import PreventUpdate

from app.backend.presets import PRESETS
from app.frontend.layout import (
    make_student_card,
    _make_bond_rank_input,
    _default_costume_name,
)


@callback(
    Output("students-container", "children"),
    Output("student-indices", "data"),
    Output("next-student-index", "data"),
    Output("bond-rank-container", "children"),
    Input("add-student-btn", "n_clicks"),
    Input({"type": "remove-student", "index": ALL}, "n_clicks"),
    Input("load-preset-btn", "n_clicks"),
    State("student-indices", "data"),
    State("next-student-index", "data"),
    State("students-container", "children"),
    State("preset-dropdown", "value"),
    State("bond-rank-container", "children"),
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
    rank_children,
):
    trigger = ctx.triggered_id

    if trigger == "add-student-btn":
        indices.append(next_idx)
        children.append(make_student_card(next_idx))
        rank_children.append(_make_bond_rank_input(next_idx))
        return children, indices, next_idx + 1, rank_children

    if isinstance(trigger, dict) and trigger.get("type") == "remove-student":
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
            c
            for c in rank_children
            if not (
                isinstance(c, dict)
                and c["props"]["children"][1]["props"]["id"].get("index") == remove_idx
            )
        ]
        return children, indices, next_idx, rank_children

    if trigger == "load-preset-btn":
        if not preset_name or preset_name not in PRESETS:
            raise PreventUpdate
        students = PRESETS[preset_name]
        new_children = []
        new_indices = []
        new_rank_children = []
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
        return new_children, new_indices, len(students), new_rank_children

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
