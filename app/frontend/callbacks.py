"""サーバーサイドコールバック。"""

from dash import html, dcc, callback, Input, Output, State, ALL, ctx, no_update
from dash.exceptions import PreventUpdate

from app.backend.student import BOND_RANGES
from app.backend.user_presets import (
    HAS_DB,
    get_all_presets_for_dropdown,
    get_favorite_options,
    get_preset_data,
    get_status_options_for,
    get_student_options,
    make_preset_value,
    preset_exists,
    register_costume_preset,
    VALID_STATUS_NAMES,
    load_gifts,
    gift_image_src,
    get_preset_present,
    parse_preset_value,
    VALID_PRESENT_TIERS,
)
from app.backend.gift_exp import (
    gift_exp,
    gift_select_box_exp,
    GIFT_SELECT_BOX_ID,
)
from app.backend.gift_solver import (
    solve_gift_distribution,
    solve_required_boxes,
    bonus_gain,
)
from app.frontend.layout import (
    make_student_card,
    _make_bond_rank_input,
    _default_costume_name,
    PAGES,
    EXTRA_PAGES,
    ROOT_REDIRECT,
    create_layout,
    build_gs_gift_list,
    gs_default_used,
    GS_BOX_RANK_WRAP_STYLE,
    GS_BOX_STATUS_WRAP_STYLE,
)


@callback(
    Output("url", "pathname"),
    Input("url", "pathname"),
)
def redirect_root(pathname):
    """ルート (/) を計算機ページへリダイレクトする。"""
    if pathname == "/":
        return ROOT_REDIRECT
    raise PreventUpdate


@callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
)
def display_page(pathname):
    """URL に応じてページを差し替える。未知のパスは計算機ページ。"""
    entry = PAGES.get(pathname) or EXTRA_PAGES.get(pathname)
    if entry is not None:
        _, builder = entry
        return builder()
    return create_layout()


# ----------------------------------------------------------------------
# プリセット選択（生徒ドロップダウン + ステータスラジオ）共通ヘルパー
# ----------------------------------------------------------------------


def _dropdown_student(dropdown_value):
    """ドロップダウン値から生徒名を取り出す。

    値は通常は生徒名のみだが、お気に入り経由では結合値
    (生徒名+ステータス名) が入る。
    """
    parsed = parse_preset_value(dropdown_value)
    return parsed[0] if parsed else dropdown_value


def _combined_preset_value(dropdown_value, status_value):
    """生徒選択とステータス選択からプリセット値（結合値）を作る。

    ステータス未選択時（DB未接続の旧形式キーなど）はドロップダウン値を
    そのまま返す。
    """
    if not dropdown_value:
        return None
    if status_value:
        return make_preset_value(_dropdown_student(dropdown_value), status_value)
    return dropdown_value


def _status_options_for_selection(dropdown_value, saved_value):
    """選択された生徒のステータス選択肢と初期選択を返す。

    初期選択の優先順: 結合値に含まれるステータス（お気に入り経由）
    → autosave に保存されたステータス（同一生徒の場合）→ 攻撃 → 先頭。
    """
    if not dropdown_value:
        return [], None
    parsed = parse_preset_value(dropdown_value)
    student = parsed[0] if parsed else dropdown_value
    options = get_status_options_for(student)
    if not options:
        return [], None
    valid = [o["value"] for o in options]
    if parsed and parsed[1] in valid:
        return options, parsed[1]
    saved = parse_preset_value(saved_value) if saved_value else None
    if saved and saved[0] == student and saved[1] in valid:
        return options, saved[1]
    if "攻撃" in valid:
        return options, "攻撃"
    return options, valid[0]


@callback(
    Output("preset-status-radio", "options"),
    Output("preset-status-radio", "value"),
    Input("preset-dropdown", "value"),
    State("autosave", "data"),
)
def update_status_radio(dropdown_value, autosave_data):
    saved = (autosave_data or {}).get("preset_value")
    return _status_options_for_selection(dropdown_value, saved)


@callback(
    Output("gs-status-radio", "options"),
    Output("gs-status-radio", "value"),
    Input("gs-preset-dropdown", "value"),
    State("gs-autosave", "data"),
)
def gs_update_status_radio(dropdown_value, autosave_data):
    saved = (autosave_data or {}).get("preset_value")
    return _status_options_for_selection(dropdown_value, saved)


# ----------------------------------------------------------------------
# 贈り物配分シミュレータ: プリセット読み込み
# ----------------------------------------------------------------------


def _gs_costume_rows(
    costumes: list[dict],
    rank_by_index=None,
    remain_by_index=None,
) -> list:
    """衣装ごとに 衣装名 / 絆ボーナス(表示のみ) / 現在の絆ランク入力 /
    次の絆上昇までの残り経験値(任意) を生成。

    rank_by_index / remain_by_index が与えられた場合は保存値で上書きする。
    """
    rank_by_index = rank_by_index or {}
    remain_by_index = remain_by_index or {}
    rows = []
    for i, c in enumerate(costumes):
        rank_val = rank_by_index.get(i, rank_by_index.get(str(i), 20))
        remain_val = remain_by_index.get(i, remain_by_index.get(str(i), None))
        bonus_cells = [
            html.Span(
                f"絆{lo}~{hi}: {c['bond_bonuses'][j]}",
                style={
                    "display": "inline-block",
                    "minWidth": "78px",
                    "fontSize": "0.78rem",
                    "color": "#555",
                },
            )
            for j, (lo, hi) in enumerate(BOND_RANGES)
        ]
        rows.append(
            html.Div(
                [
                    html.Strong(
                        c["costume_name"],
                        style={"minWidth": "70px", "display": "inline-block"},
                    ),
                    html.Div(
                        [
                            html.Span("現在の絆ランク: ", style={"fontSize": "0.8rem"}),
                            dcc.Input(
                                id={"type": "gs-bond-rank", "index": i},
                                type="number",
                                min=1,
                                max=50,
                                value=rank_val,
                                debounce=True,
                                style={"width": "60px", "textAlign": "center"},
                            ),
                            html.Span(
                                "次の絆まで残りEXP: ",
                                style={"fontSize": "0.8rem", "marginLeft": "8px"},
                                title=(
                                    "次の絆ランクまでの残り経験値（任意）。"
                                    "空欄なら現在ランクの開始（経験値0）として計算。"
                                ),
                            ),
                            dcc.Input(
                                id={"type": "gs-bond-remain", "index": i},
                                type="number",
                                min=1,
                                value=remain_val,
                                debounce=True,
                                placeholder="任意",
                                style={"width": "72px", "textAlign": "center"},
                            ),
                        ],
                        style={
                            "flexShrink": "0",
                            "whiteSpace": "nowrap",
                            "display": "flex",
                            "alignItems": "center",
                            "gap": "4px",
                        },
                    ),
                    html.Span(bonus_cells, style={"flex": "1"}),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "8px",
                    "padding": "6px 0",
                    "borderBottom": "1px solid #eee",
                },
            )
        )
    return rows


def _gs_box_target_rows(costumes: list[dict], target_by_index=None) -> html.Div:
    """衣装ごとの目標絆ランク入力欄（必要ボックス数計算カード用）。

    target_by_index が与えられた場合は保存値で上書きする。
    """
    target_by_index = target_by_index or {}
    items = []
    for i, c in enumerate(costumes):
        target_val = target_by_index.get(i, target_by_index.get(str(i), None))
        items.append(
            html.Div(
                [
                    html.Span(c["costume_name"], style={"fontSize": "0.85rem"}),
                    dcc.Input(
                        id={"type": "gs-bond-target", "index": i},
                        type="number",
                        min=1,
                        max=50,
                        value=target_val,
                        debounce=True,
                        placeholder="任意",
                        style={"width": "60px", "textAlign": "center"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "4px"},
            )
        )
    return html.Div(
        items,
        style={"display": "flex", "flexWrap": "wrap", "gap": "6px 16px"},
    )


# present.tier -> リアクションアイコン (assets/reaction/<name>.png)。
# admin._TIER_ICON と同じ対応。
_GS_TIER_ICON = {
    "favorite": "favorite",
    "superFavorite": "super",
    "ultraFavorite": "ultra",
}
_GS_TIER_LABELS = {
    "favorite": "中",
    "superFavorite": "大",
    "ultraFavorite": "特大",
}


def _gs_present_table(costumes: list[dict], present: dict, gifts: list[dict]):
    """衣装ごとの好物（normal 以外）を 衣装(縦)×リアクション(横) の表にする。

    present: {衣装名: {gift_id: tier}}。データが無い場合はメッセージを返す。
    """
    if not any(present.get(c["costume_name"]) for c in costumes):
        return html.P(
            "好物データが登録されていません。",
            style={"color": "#888", "margin": "8px 0"},
        )
    header = html.Tr(
        [html.Th("衣装", style=_TH)]
        + [
            html.Th(
                html.Img(
                    src=f"/assets/reaction/{_GS_TIER_ICON[t]}.png",
                    alt=_GS_TIER_LABELS[t],
                    title=_GS_TIER_LABELS[t],
                    style={"height": "24px", "verticalAlign": "middle"},
                ),
                style=_TH,
            )
            for t in VALID_PRESENT_TIERS
        ]
    )
    rows = []
    for c in costumes:
        tier_by_gift = present.get(c["costume_name"], {})
        cells = []
        for t in VALID_PRESENT_TIERS:
            imgs = [
                html.Img(
                    src=gift_image_src(g),
                    title=g["name"],
                    style={
                        "width": "34px",
                        "height": "26px",
                        "objectFit": "contain",
                        "padding": "2px",
                        "borderRadius": "4px",
                        # 高級は淡い紫、通常は淡い黄色
                        "background": (
                            "#ede7f6"
                            if g["gift_type"] in ("high", "high-all")
                            else "#fff9c4"
                        ),
                    },
                )
                for g in gifts
                if tier_by_gift.get(g["id"]) == t
            ]
            cells.append(html.Td(imgs if imgs else "－", style=_TD))
        rows.append(html.Tr([html.Td(c["costume_name"], style=_TD_LABEL)] + cells))
    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={"borderCollapse": "collapse"},
    )


def _preset_present_children(preset_value, costumes: list[dict]):
    """プリセット値から好物表を構築する（両ページ共通の入口）。"""
    parsed = parse_preset_value(preset_value)
    if not parsed:
        return html.P(
            "好物データが登録されていません。",
            style={"color": "#888", "margin": "8px 0"},
        )
    return _gs_present_table(costumes, get_preset_present(*parsed), load_gifts())


def _gs_build_view(
    preset_value, ranks=None, qty=None, use=None, remain=None, targets=None
):
    """プリセットから 衣装表示 / 好物表 / フィードバック / loaded-store /
    贈り物リスト / 目標絆ランク入力欄 を構築する。ranks/qty/use/remain/targets
    は保存値の上書き（復元用）。

    Returns (costume_children, present_children, feedback, store_data,
    gift_list_children, box_target_children) または失敗時
    (None, None, error_span, None, None, None)。
    """
    result = get_preset_data(preset_value)
    parsed = parse_preset_value(preset_value)
    if not result or not parsed:
        return (
            None,
            None,
            html.Span("プリセットが見つかりません。", style={"color": "red"}),
            None,
            None,
            None,
        )
    display_name, costumes = result
    student_name, status_name = parsed
    present = get_preset_present(student_name, status_name)
    preferred = {gid for tiers in present.values() for gid in tiers}

    gifts = load_gifts()
    gift_list_children = build_gs_gift_list(
        gifts,
        lambda g: gs_default_used(g, preferred),
        qty_by_gift=qty,
        use_by_gift=use,
    )
    present_children = _gs_present_table(costumes, present, gifts)
    feedback = html.Span(
        f"「{display_name}」を読み込みました。", style={"color": "#27ae60"}
    )
    return (
        _gs_costume_rows(costumes, rank_by_index=ranks, remain_by_index=remain),
        present_children,
        feedback,
        {
            "student_name": student_name,
            "status_name": status_name,
            "costumes": costumes,
        },
        gift_list_children,
        _gs_box_target_rows(costumes, target_by_index=targets),
    )


@callback(
    Output("gs-costume-display", "children"),
    Output("gs-present-display", "children"),
    Output("gs-load-feedback", "children"),
    Output("gs-loaded-preset", "data"),
    Output("gs-gift-list", "children"),
    Output("gs-box-rank-targets", "children"),
    Input("gs-load-preset-btn", "n_clicks"),
    State("gs-preset-dropdown", "value"),
    State("gs-status-radio", "value"),
    prevent_initial_call=True,
)
def gs_load_preset(n_clicks, dropdown_value, status_value):
    preset_value = _combined_preset_value(dropdown_value, status_value)
    if not preset_value:
        return (
            no_update,
            no_update,
            html.Span("プリセットを選択してください。", style={"color": "red"}),
            no_update,
            no_update,
            no_update,
        )
    (
        costume_children,
        present_children,
        feedback,
        store,
        gift_list,
        box_targets,
    ) = _gs_build_view(preset_value)
    if store is None:
        return (no_update, no_update, feedback, no_update, no_update, no_update)
    return (costume_children, present_children, feedback, store, gift_list, box_targets)


# ----------------------------------------------------------------------
# 贈り物配分シミュレータ: 入力保存（localStorage autosave）
# ----------------------------------------------------------------------


@callback(
    Output("gs-autosave", "data"),
    Input("gs-preset-dropdown", "value"),
    Input("gs-status-radio", "value"),
    Input({"type": "gs-bond-rank", "index": ALL}, "value"),
    Input({"type": "gs-bond-remain", "index": ALL}, "value"),
    Input({"type": "gs-bond-target", "index": ALL}, "value"),
    Input({"type": "gs-gift-qty", "gift": ALL}, "value"),
    Input({"type": "gs-gift-use", "gift": ALL}, "value"),
    Input("gs-box-target-mode", "value"),
    Input("gs-box-target-status", "value"),
    State({"type": "gs-bond-rank", "index": ALL}, "id"),
    State({"type": "gs-bond-remain", "index": ALL}, "id"),
    State({"type": "gs-bond-target", "index": ALL}, "id"),
    State({"type": "gs-gift-qty", "gift": ALL}, "id"),
    State({"type": "gs-gift-use", "gift": ALL}, "id"),
    State("gs-autosave-ready", "data"),
    prevent_initial_call=True,
)
def gs_save_autosave(
    dropdown_value,
    status_value,
    rank_values,
    remain_values,
    target_values,
    qty_values,
    use_values,
    box_mode,
    box_status,
    rank_ids,
    remain_ids,
    target_ids,
    qty_ids,
    use_ids,
    ready,
):
    # 復元前の保存は禁止。動的レイアウト挿入直後は prevent_initial_call が
    # 効かず初期値で発火するため、そのまま保存すると復元前のデータが潰れる。
    if not ready:
        raise PreventUpdate
    ranks = {
        str(rid["index"]): rv
        for rv, rid in zip(rank_values, rank_ids)
        if rv is not None
    }
    remain = {
        str(rid["index"]): rv
        for rv, rid in zip(remain_values, remain_ids)
        if rv is not None
    }
    targets = {
        str(tid["index"]): tv
        for tv, tid in zip(target_values, target_ids)
        if tv is not None
    }
    qty = {}
    for qv, qid in zip(qty_values, qty_ids):
        try:
            qty[qid["gift"]] = max(0, int(qv))
        except (TypeError, ValueError):
            qty[qid["gift"]] = 0
    use = {
        uid["gift"]: bool(uv and "use" in uv) for uv, uid in zip(use_values, use_ids)
    }
    return {
        "preset_value": _combined_preset_value(dropdown_value, status_value),
        "ranks": ranks,
        "remain": remain,
        "targets": targets,
        "qty": qty,
        "use": use,
        "box_mode": box_mode,
        "box_status": box_status,
    }


@callback(
    Output("gs-preset-dropdown", "value"),
    Output("gs-costume-display", "children", allow_duplicate=True),
    Output("gs-present-display", "children", allow_duplicate=True),
    Output("gs-load-feedback", "children", allow_duplicate=True),
    Output("gs-loaded-preset", "data", allow_duplicate=True),
    Output("gs-gift-list", "children", allow_duplicate=True),
    Output("gs-box-rank-targets", "children", allow_duplicate=True),
    Output("gs-box-target-mode", "value"),
    Output("gs-box-target-status", "value"),
    Output("gs-autosave-ready", "data"),
    Input("gs-autosave-init", "n_intervals"),
    State("gs-autosave", "data"),
    prevent_initial_call=True,
)
def gs_restore_autosave(_n, data):
    # 復元するものがなくても ready フラグは立てる（以降の保存を許可）
    if not data:
        return (no_update,) * 9 + (True,)
    preset_value = data.get("preset_value")
    qty = data.get("qty") or {}
    use = data.get("use") or {}
    ranks = data.get("ranks") or {}
    remain = data.get("remain") or {}
    targets = data.get("targets") or {}
    box_mode = data.get("box_mode") or "rank"
    box_status = data.get("box_status")

    if not preset_value:
        # プリセット未選択でも所持数・使用フラグは復元する
        gifts = load_gifts()
        gift_list = build_gs_gift_list(
            gifts,
            lambda g: gs_default_used(g),
            qty_by_gift=qty,
            use_by_gift=use,
        )
        return (
            None,
            no_update,
            no_update,
            no_update,
            no_update,
            gift_list,
            no_update,
            box_mode,
            box_status,
            True,
        )

    (
        costume_children,
        present_children,
        feedback,
        store,
        gift_list,
        box_targets,
    ) = _gs_build_view(
        preset_value, ranks=ranks, qty=qty, use=use, remain=remain, targets=targets
    )
    if store is None:
        return (no_update,) * 9 + (True,)
    return (
        _dropdown_student(preset_value),
        costume_children,
        present_children,
        feedback,
        store,
        gift_list,
        box_targets,
        box_mode,
        box_status,
        True,
    )


def _rank_bg(rank: int) -> str:
    """最終絆ランクの色分け。"""
    if rank >= 50:
        return "#ffd54f"
    if rank >= 40:
        return "#aed581"
    if rank >= 30:
        return "#dce775"
    if rank >= 20:
        return "#fff59d"
    if rank >= 10:
        return "#ffcc80"
    return "#ef9a9a"


_TH = {
    "border": "1px solid #ccc",
    "padding": "4px 8px",
    "background": "#3498db",
    "color": "white",
    "fontSize": "0.8rem",
    "whiteSpace": "nowrap",
}
_TD = {
    "border": "1px solid #ddd",
    "padding": "4px 8px",
    "textAlign": "center",
    "fontSize": "0.82rem",
}
_TD_LABEL = {**_TD, "textAlign": "left", "whiteSpace": "nowrap"}


def _gs_result_table(
    col_names: list,
    used_gifts: list,
    allocation: list,
    final_ranks: list,
    other_normal_alloc=None,
    other_high_alloc=None,
    extra_rows: list | None = None,
) -> html.Table:
    """贈り物×衣装の配分マトリクス（MILP 解）。

    other_normal_alloc / other_high_alloc が list（衣装ごとの配分数）なら
    その他(通常)/その他(高級) の集約行として表示する。None なら非表示。
    extra_rows は (ラベル, 衣装ごとの個数リスト) の列で、最終絆ランク行の
    直前に強調表示で追加する（不足ボックス数など）。
    """
    ncol = len(col_names)

    header = html.Tr(
        [html.Th("贈り物 ＼ 衣装", style=_TH)]
        + [html.Th(n, style=_TH) for n in col_names]
    )

    body = []
    for gi, g in enumerate(used_gifts):
        label = html.Td(
            html.Div(
                [
                    html.Img(
                        src=gift_image_src(g),
                        title=g["name"],
                        style={
                            "width": "28px",
                            "height": "22px",
                            "objectFit": "contain",
                        },
                    ),
                    html.Span(
                        g["name"],
                        style={"fontSize": "0.78rem", "marginLeft": "6px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
            style=_TD_LABEL,
        )
        body.append(
            html.Tr(
                [label]
                + [html.Td(str(allocation[gi][ci]), style=_TD) for ci in range(ncol)]
            )
        )

    # その他(通常)/その他(高級) 集約行（使用ON・非好み・非all・非boxを集約）
    if other_normal_alloc is not None:
        body.append(
            html.Tr(
                [html.Td("その他(通常)", style=_TD_LABEL)]
                + [
                    html.Td(str(other_normal_alloc[ci]), style=_TD)
                    for ci in range(ncol)
                ]
            )
        )
    if other_high_alloc is not None:
        body.append(
            html.Tr(
                [html.Td("その他(高級)", style=_TD_LABEL)]
                + [html.Td(str(other_high_alloc[ci]), style=_TD) for ci in range(ncol)]
            )
        )

    for label_text, counts in extra_rows or []:
        body.append(
            html.Tr(
                [html.Td(label_text, style={**_TD_LABEL, "fontWeight": "bold"})]
                + [
                    html.Td(
                        str(counts[ci]),
                        style={**_TD, "fontWeight": "bold", "background": "#f3e5f5"},
                    )
                    for ci in range(ncol)
                ]
            )
        )

    # 最終絆ランク行（色分け）
    rank_cells = [
        html.Td(
            str(final_ranks[ci]),
            style={
                **_TD,
                "fontWeight": "bold",
                "background": _rank_bg(final_ranks[ci]),
            },
        )
        for ci in range(ncol)
    ]
    body.append(
        html.Tr(
            [html.Td("最終絆ランク", style={**_TD_LABEL, "fontWeight": "bold"})]
            + rank_cells
        )
    )

    return html.Table(
        [html.Thead(header), html.Tbody(body)],
        style={"borderCollapse": "collapse", "marginTop": "8px"},
    )


def _gs_parse_current_ranks(rank_values, rank_ids, n: int) -> list[int]:
    """現在の絆ランク入力を衣装 index 順のリストにする（不正値は20）。"""
    rank_by_idx = {rid["index"]: rv for rv, rid in zip(rank_values, rank_ids)}
    current_ranks = []
    for i in range(n):
        v = rank_by_idx.get(i)
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = 20
        current_ranks.append(min(50, max(1, v)))
    return current_ranks


def _gs_parse_remaining_exp(remain_values, remain_ids, n: int) -> list[int | None]:
    """次の絆上昇までの残り経験値入力を衣装 index 順のリストにする。

    未入力/不正/0以下は None（= 通常どおりレベル満額を要求）。
    """
    remain_by_idx = {rid["index"]: rv for rv, rid in zip(remain_values, remain_ids)}
    remaining_exp: list[int | None] = []
    for i in range(n):
        rv = remain_by_idx.get(i)
        try:
            rv = int(rv)
        except (TypeError, ValueError):
            rv = None
        if rv is not None and rv <= 0:
            rv = None
        remaining_exp.append(rv)
    return remaining_exp


def _gs_box_values(costumes: list[dict], present: dict, type_by_id: dict) -> list[int]:
    """衣装ごとの 贈り物選択ボックス1個あたり獲得EXP。"""
    values = []
    for c in costumes:
        tiers = present.get(c["costume_name"], {})
        rows = [(type_by_id.get(gid, ""), tier) for gid, tier in tiers.items()]
        values.append(gift_select_box_exp(rows))
    return values


def _gs_build_gift_inputs(
    costumes: list[dict],
    present: dict,
    catalog: list[dict],
    use_values,
    use_ids,
    qty_values,
    qty_ids,
):
    """使用ON贈り物を MILP 入力（個別 + プール集約）へ変換する。

    使用ON贈り物を「個別」と「その他(集約)」に振り分ける。
     個別     : 好み(present) / all型 / 贈り物選択ボックス
     その他通常: 上記以外の素 normal（非好み=一律20EXP相当）
     その他高級: 上記以外の素 high （非好み=一律120EXP相当）

    Returns
    -------
    (individual_gifts, value, gift_qty, pool_idx_normal, pool_idx_high)
        individual_gifts : 個別扱いの贈り物（カタログ行）
        value / gift_qty : プール擬似贈り物 2 行を含む MILP 入力
        pool_idx_normal / pool_idx_high : プール行の index（無ければ None）
    """
    used_ids = {
        uid["gift"] for uid, val in zip(use_ids, use_values) if val and "use" in val
    }
    qty_by_gift = {}
    for qid, qv in zip(qty_ids, qty_values):
        try:
            qty_by_gift[qid["gift"]] = max(0, int(qv))
        except (TypeError, ValueError):
            qty_by_gift[qid["gift"]] = 0

    type_by_id = {g["id"]: g["gift_type"] for g in catalog}
    preferred = {gid for tiers in present.values() for gid in tiers}
    ncol = len(costumes)

    individual_gifts = []
    pool_normal_qty = 0
    pool_high_qty = 0
    has_pool_normal = False
    has_pool_high = False
    for g in catalog:
        if g["id"] not in used_ids:
            continue
        gtype = g["gift_type"]
        is_individual = (
            g["id"] == GIFT_SELECT_BOX_ID or "all" in gtype or g["id"] in preferred
        )
        if is_individual:
            individual_gifts.append(g)
        elif gtype == "normal":
            has_pool_normal = True
            pool_normal_qty += qty_by_gift.get(g["id"], 0)
        elif gtype == "high":
            has_pool_high = True
            pool_high_qty += qty_by_gift.get(g["id"], 0)

    # 価値行列 value[g][c]（個別贈り物）
    value = []
    for g in individual_gifts:
        row = []
        for c in costumes:
            tiers = present.get(c["costume_name"], {})
            if g["id"] == GIFT_SELECT_BOX_ID:
                rows = [(type_by_id.get(gid, ""), tier) for gid, tier in tiers.items()]
                row.append(gift_select_box_exp(rows))
            else:
                row.append(gift_exp(g["gift_type"], tiers.get(g["id"])))
        value.append(row)
    gift_qty = [qty_by_gift.get(g["id"], 0) for g in individual_gifts]

    # その他 集約の擬似贈り物（全衣装一律 EXP）。
    other_normal_exp = gift_exp("normal", None)  # 20
    other_high_exp = gift_exp("high", None)  # 120
    pool_idx_normal = pool_idx_high = None
    if has_pool_normal:
        pool_idx_normal = len(value)
        value.append([other_normal_exp] * ncol)
        gift_qty.append(pool_normal_qty)
    if has_pool_high:
        pool_idx_high = len(value)
        value.append([other_high_exp] * ncol)
        gift_qty.append(pool_high_qty)

    return individual_gifts, value, gift_qty, pool_idx_normal, pool_idx_high


@callback(
    Output("gs-calc-result", "children"),
    Input("gs-calc-btn", "n_clicks"),
    State("gs-loaded-preset", "data"),
    State({"type": "gs-gift-use", "gift": ALL}, "value"),
    State({"type": "gs-gift-use", "gift": ALL}, "id"),
    State({"type": "gs-gift-qty", "gift": ALL}, "value"),
    State({"type": "gs-gift-qty", "gift": ALL}, "id"),
    State({"type": "gs-bond-rank", "index": ALL}, "value"),
    State({"type": "gs-bond-rank", "index": ALL}, "id"),
    State({"type": "gs-bond-remain", "index": ALL}, "value"),
    State({"type": "gs-bond-remain", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def gs_calculate(
    n_clicks,
    loaded,
    use_values,
    use_ids,
    qty_values,
    qty_ids,
    rank_values,
    rank_ids,
    remain_values,
    remain_ids,
):
    """MILP(SCIP) で贈り物配分を最適化し、マトリクスを表示する。"""
    if not loaded:
        return html.Span("先にプリセットを読み込んでください。", style={"color": "red"})

    costumes = loaded.get("costumes", [])
    if not costumes:
        return html.Span("衣装がありません。", style={"color": "red"})

    # 現在の絆ランク / 次の絆上昇までの残り経験値（衣装index順）
    current_ranks = _gs_parse_current_ranks(rank_values, rank_ids, len(costumes))
    remaining_exp = _gs_parse_remaining_exp(remain_values, remain_ids, len(costumes))

    student = loaded["student_name"]
    status_name = loaded["status_name"]
    present = get_preset_present(student, status_name)  # 衣装名->{gift:tier}
    (
        individual_gifts,
        value,
        gift_qty,
        pool_idx_normal,
        pool_idx_high,
    ) = _gs_build_gift_inputs(
        costumes, present, load_gifts(), use_values, use_ids, qty_values, qty_ids
    )

    bond_bonuses = [c["bond_bonuses"] for c in costumes]

    try:
        result = solve_gift_distribution(
            current_ranks,
            bond_bonuses,
            gift_qty,
            value,
            remaining_exp=remaining_exp,
        )
    except Exception as e:
        return html.Span(f"計算エラー: {e}", style={"color": "red"})

    status = result["status"]
    if status not in ("optimal", "timelimit"):
        return html.Span(
            f"解を得られませんでした（SCIP: {status}）。",
            style={"color": "red"},
        )

    alloc = result["allocation"]
    n_ind = len(individual_gifts)
    other_normal_alloc = (
        list(alloc[pool_idx_normal]) if pool_idx_normal is not None else None
    )
    other_high_alloc = list(alloc[pool_idx_high]) if pool_idx_high is not None else None

    col_names = [c["costume_name"] for c in costumes]
    table = _gs_result_table(
        col_names,
        individual_gifts,
        alloc[:n_ind],
        result["final_ranks"],
        other_normal_alloc,
        other_high_alloc,
    )
    status_note = []
    if status == "optimal":
        status_note.append(
            html.Span(
                "（SCIP: 最適）",
                style={"color": "#888", "fontSize": "0.8rem"},
            )
        )
    elif status == "timelimit":
        status_note.append(
            html.Span(
                "（時間制限到達: 暫定解。最適とは限りません）",
                style={"color": "#e67e22", "fontSize": "0.8rem"},
            )
        )
    else:
        status_note.append(
            html.Span(
                f"（SCIP: {status}）",
                style={"color": "#888", "fontSize": "0.8rem"},
            )
        )
    summary = html.Div(
        [
            html.Span(
                f"絆ボーナス上昇量 合計: +{result['total_gain']}",
                style={"fontWeight": "bold", "marginRight": "12px"},
            ),
            *status_note,
        ],
        style={"margin": "4px 0"},
    )
    return html.Div([summary, table])


# ----------------------------------------------------------------------
# 贈り物配分シミュレータ: 必要な贈り物選択ボックス数
# ----------------------------------------------------------------------


@callback(
    Output("gs-box-rank-target-wrap", "style"),
    Output("gs-box-status-target-wrap", "style"),
    Input("gs-box-target-mode", "value"),
)
def gs_toggle_box_target_inputs(mode):
    """目標指定方法の選択に応じて、対応する目標入力欄のみ表示する。"""
    if mode == "status":
        return (
            {**GS_BOX_RANK_WRAP_STYLE, "display": "none"},
            GS_BOX_STATUS_WRAP_STYLE,
        )
    return (
        GS_BOX_RANK_WRAP_STYLE,
        {**GS_BOX_STATUS_WRAP_STYLE, "display": "none"},
    )


@callback(
    Output("gs-box-calc-result", "children"),
    Input("gs-box-calc-btn", "n_clicks"),
    State("gs-loaded-preset", "data"),
    State("gs-box-target-mode", "value"),
    State("gs-box-target-status", "value"),
    State({"type": "gs-gift-use", "gift": ALL}, "value"),
    State({"type": "gs-gift-use", "gift": ALL}, "id"),
    State({"type": "gs-gift-qty", "gift": ALL}, "value"),
    State({"type": "gs-gift-qty", "gift": ALL}, "id"),
    State({"type": "gs-bond-rank", "index": ALL}, "value"),
    State({"type": "gs-bond-rank", "index": ALL}, "id"),
    State({"type": "gs-bond-remain", "index": ALL}, "value"),
    State({"type": "gs-bond-remain", "index": ALL}, "id"),
    State({"type": "gs-bond-target", "index": ALL}, "value"),
    State({"type": "gs-bond-target", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def gs_box_calculate(
    n_clicks,
    loaded,
    mode,
    target_status,
    use_values,
    use_ids,
    qty_values,
    qty_ids,
    rank_values,
    rank_ids,
    remain_values,
    remain_ids,
    target_values,
    target_ids,
):
    """目標（絆ランク or ステータス上昇量）達成に不足するボックス数を計算する。

    使用ONの所持贈り物（選択ボックス含む）を最適に配分した上で、
    それでも足りない分の贈り物選択ボックス数を最小化する。
    """
    if not loaded:
        return html.Span("先にプリセットを読み込んでください。", style={"color": "red"})

    costumes = loaded.get("costumes", [])
    if not costumes:
        return html.Span("衣装がありません。", style={"color": "red"})

    n = len(costumes)
    current_ranks = _gs_parse_current_ranks(rank_values, rank_ids, n)
    remaining_exp = _gs_parse_remaining_exp(remain_values, remain_ids, n)

    catalog = load_gifts()
    present = get_preset_present(loaded["student_name"], loaded["status_name"])
    type_by_id = {g["id"]: g["gift_type"] for g in catalog}
    box_values = _gs_box_values(costumes, present, type_by_id)
    (
        individual_gifts,
        value,
        gift_qty,
        pool_idx_normal,
        pool_idx_high,
    ) = _gs_build_gift_inputs(
        costumes, present, catalog, use_values, use_ids, qty_values, qty_ids
    )
    bond_bonuses = [c["bond_bonuses"] for c in costumes]

    target_ranks = None
    target_gain = None
    if mode == "status":
        try:
            target_gain = int(target_status)
        except (TypeError, ValueError):
            target_gain = 0
        if target_gain <= 0:
            return html.Span(
                "目標ステータス上昇量（1以上の整数）を入力してください。",
                style={"color": "red"},
            )
        max_gain = sum(
            bonus_gain(c["bond_bonuses"], current_ranks[i], 50)
            for i, c in enumerate(costumes)
        )
        if target_gain > max_gain:
            return html.Span(
                f"全衣装を絆50にしても上昇量は +{max_gain} が上限です。"
                "目標を下げてください。",
                style={"color": "red"},
            )
        target_desc = f"目標 +{target_gain}"
    else:
        # 目標絆ランクモード（衣装index順、未入力/不正は None = 対象外）
        target_by_idx = {tid["index"]: tv for tv, tid in zip(target_values, target_ids)}
        target_ranks = []
        for i in range(n):
            tv = target_by_idx.get(i)
            try:
                tv = min(50, max(1, int(tv)))
            except (TypeError, ValueError):
                tv = None
            target_ranks.append(tv)
        if all(tv is None for tv in target_ranks):
            return html.Span(
                "目標絆ランクを入力してください（空欄の衣装は計算対象外）。",
                style={"color": "red"},
            )
        target_desc = "目標: " + " / ".join(
            f"{c['costume_name']} 絆{target_ranks[i]}"
            for i, c in enumerate(costumes)
            if target_ranks[i] is not None
        )

    try:
        result = solve_required_boxes(
            current_ranks,
            bond_bonuses,
            gift_qty,
            value,
            box_values,
            target_ranks=target_ranks,
            target_gain=target_gain,
            remaining_exp=remaining_exp,
        )
    except Exception as e:
        return html.Span(f"計算エラー: {e}", style={"color": "red"})

    status = result["status"]
    if status not in ("optimal", "timelimit"):
        return html.Span(
            f"解を得られませんでした（SCIP: {status}）。",
            style={"color": "red"},
        )

    alloc = result["allocation"]
    n_ind = len(individual_gifts)
    other_normal_alloc = (
        list(alloc[pool_idx_normal]) if pool_idx_normal is not None else None
    )
    other_high_alloc = list(alloc[pool_idx_high]) if pool_idx_high is not None else None

    col_names = [c["costume_name"] for c in costumes]
    table = _gs_result_table(
        col_names,
        individual_gifts,
        alloc[:n_ind],
        result["final_ranks"],
        other_normal_alloc,
        other_high_alloc,
        extra_rows=[("追加ボックス（不足分）", result["boxes"])],
    )
    note = []
    if status == "timelimit":
        note.append(
            html.Span(
                "（時間制限到達: 暫定解。最小とは限りません）",
                style={"color": "#e67e22", "fontSize": "0.8rem"},
            )
        )
    summary = html.Div(
        [
            html.Span(
                f"不足分の贈り物選択ボックス: 合計 {result['total_boxes']} 個"
                f"（ステータス上昇 +{result['total_gain']} / {target_desc}）",
                style={"fontWeight": "bold", "marginRight": "12px"},
            ),
            *note,
        ],
        style={"margin": "4px 0"},
    )
    return html.Div([summary, table])


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
    Output("present-display", "children"),
    Input("add-student-btn", "n_clicks"),
    Input({"type": "remove-student", "index": ALL}, "n_clicks"),
    Input("load-preset-btn", "n_clicks"),
    State("student-indices", "data"),
    State("next-student-index", "data"),
    State("students-container", "children"),
    State("preset-dropdown", "value"),
    State("preset-status-radio", "value"),
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
    preset_dropdown_value,
    preset_status_value,
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
            no_update,
        )

    if trigger == "load-preset-btn":
        preset_name = _combined_preset_value(preset_dropdown_value, preset_status_value)
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
            _preset_present_children(preset_name, students),
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
_BOND_RANK_ERROR_STYLE = {
    **_BOND_RANK_BASE_STYLE,
    "border": "2px solid red",
    "color": "red",
}


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
    Input("preset-status-radio", "value"),
    State("student-indices", "data"),
    State("next-student-index", "data"),
    State({"type": "costume", "index": ALL}, "id"),
    State({"type": "bond-rank", "index": ALL}, "id"),
    State("autosave-ready", "data"),
    prevent_initial_call=True,
)
def save_autosave(
    costume_values,
    rank_values,
    priority_data,
    penalty,
    dropdown_value,
    status_value,
    indices,
    next_index,
    costume_ids,
    rank_ids,
    ready,
):
    # 復元前の保存は禁止。動的レイアウト挿入直後は prevent_initial_call が
    # 効かず初期値で発火するため、そのまま保存すると復元前のデータが潰れる。
    if not ready:
        raise PreventUpdate
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
        "preset_value": _combined_preset_value(dropdown_value, status_value),
    }


@callback(
    Output("students-container", "children", allow_duplicate=True),
    Output("student-indices", "data", allow_duplicate=True),
    Output("next-student-index", "data", allow_duplicate=True),
    Output("bond-rank-container", "children", allow_duplicate=True),
    Output("costume-priority-order", "data", allow_duplicate=True),
    Output("bond50-penalty", "value", allow_duplicate=True),
    Output("preset-dropdown", "value"),
    Output("present-display", "children", allow_duplicate=True),
    Output("autosave-ready", "data"),
    Input("autosave-init", "n_intervals"),
    State("autosave", "data"),
    prevent_initial_call=True,
)
def restore_autosave(_n, data):
    # 復元するものがなくても ready フラグは立てる（以降の保存を許可）
    if not data or not data.get("indices"):
        return (no_update,) * 8 + (True,)

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
                {"idx": i, "name": s["costume_name"]} for i, s in enumerate(students)
            ]
            return (
                student_children,
                indices,
                next_index,
                rank_children,
                priority,
                penalty if penalty is not None else 0,
                _dropdown_student(preset_value),
                _preset_present_children(preset_value, students),
                True,
            )

    # プリセット未選択: デフォルト状態（衣装1つ）
    return (no_update,) * 8 + (True,)


@callback(
    Output("favorites", "data"),
    Output("fav-toggle-btn", "children"),
    Input("fav-toggle-btn", "n_clicks"),
    Input("preset-dropdown", "value"),
    Input("preset-status-radio", "value"),
    State("favorites", "data"),
    prevent_initial_call=False,
)
def toggle_favorite(n_clicks, dropdown_value, status_value, favorites):
    favorites = list(favorites or [])
    preset_value = _combined_preset_value(dropdown_value, status_value)
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
    if not HAS_DB:
        # JSON フォールバック (旧形式キー)
        return _sort_options_with_favorites(
            get_all_presets_for_dropdown(), favorites or []
        )
    return get_favorite_options(favorites or []) + get_student_options()


@callback(
    Output("submit-feedback", "children"),
    Output("submit-preset-status", "data"),
    Input("submit-preset-btn", "submit_n_clicks"),
    State("submit-character-name", "value"),
    State("submit-status-name", "value"),
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
    status_name,
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
    if status_name not in VALID_STATUS_NAMES:
        return (
            html.Span("ステータス名を選択してください。", style={"color": "red"}),
            no_update,
        )

    char_name = char_name.strip()

    if preset_exists(char_name, status_name):
        return (
            html.Span(
                f"「{char_name}（{status_name}）」は登録済みです。"
                "データの修正依頼は、ページ上部の報告フォームからお願いします。",
                style={"color": "red"},
            ),
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

    register_costume_preset(char_name, status_name, costumes)
    return (
        html.Span(
            f"「{char_name}（{status_name}）」を投稿しました。",
            style={"color": "#27ae60"},
        ),
        {"submitted": True},
    )
