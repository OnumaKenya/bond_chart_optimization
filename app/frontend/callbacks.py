"""サーバーサイドコールバック。"""

from dash import html, dcc, callback, Input, Output, State, ALL, ctx, no_update
from dash.exceptions import PreventUpdate

from app.backend.student import BOND_RANGES
from app.backend.user_presets import (
    get_all_presets_for_dropdown,
    get_preset_data,
    preset_exists,
    register_costume_preset,
    VALID_STATUS_NAMES,
    load_gifts,
    gift_image_src,
    get_preset_preferred_gift_ids,
    get_preset_present,
    parse_preset_value,
    VALID_PRESENT_TIERS,
)
from app.backend.gift_exp import (
    gift_exp,
    gift_select_box_exp,
    GIFT_SELECT_BOX_ID,
)
from app.backend.gift_solver import solve_gift_distribution
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
# 贈り物配分シミュレータ: プリセット読み込み
# ----------------------------------------------------------------------


def _gs_costume_rows(
    costumes: list[dict], rank_by_index=None, remain_by_index=None
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


def _gs_build_view(preset_value, ranks=None, qty=None, use=None, remain=None):
    """プリセットから 衣装表示 / 好物表 / フィードバック / loaded-store /
    贈り物リスト を構築する。ranks/qty/use/remain は保存値の上書き（復元用）。

    Returns (costume_children, present_children, feedback, store_data,
    gift_list_children) または失敗時 (None, None, error_span, None, None)。
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
        )
    display_name, costumes = result
    student_name, status_name = parsed
    preferred = get_preset_preferred_gift_ids(student_name, status_name)

    gifts = load_gifts()
    gift_list_children = build_gs_gift_list(
        gifts,
        lambda g: gs_default_used(g, preferred),
        qty_by_gift=qty,
        use_by_gift=use,
    )
    present = get_preset_present(student_name, status_name)
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
    )


@callback(
    Output("gs-costume-display", "children"),
    Output("gs-present-display", "children"),
    Output("gs-load-feedback", "children"),
    Output("gs-loaded-preset", "data"),
    Output("gs-gift-list", "children"),
    Input("gs-load-preset-btn", "n_clicks"),
    State("gs-preset-dropdown", "value"),
    prevent_initial_call=True,
)
def gs_load_preset(n_clicks, preset_value):
    if not preset_value:
        return (
            no_update,
            no_update,
            html.Span("プリセットを選択してください。", style={"color": "red"}),
            no_update,
            no_update,
        )
    costume_children, present_children, feedback, store, gift_list = _gs_build_view(
        preset_value
    )
    if store is None:
        return (no_update, no_update, feedback, no_update, no_update)
    return (costume_children, present_children, feedback, store, gift_list)


# ----------------------------------------------------------------------
# 贈り物配分シミュレータ: 入力保存（localStorage autosave）
# ----------------------------------------------------------------------


@callback(
    Output("gs-autosave", "data"),
    Input("gs-preset-dropdown", "value"),
    Input({"type": "gs-bond-rank", "index": ALL}, "value"),
    Input({"type": "gs-bond-remain", "index": ALL}, "value"),
    Input({"type": "gs-gift-qty", "gift": ALL}, "value"),
    Input({"type": "gs-gift-use", "gift": ALL}, "value"),
    State({"type": "gs-bond-rank", "index": ALL}, "id"),
    State({"type": "gs-bond-remain", "index": ALL}, "id"),
    State({"type": "gs-gift-qty", "gift": ALL}, "id"),
    State({"type": "gs-gift-use", "gift": ALL}, "id"),
    prevent_initial_call=True,
)
def gs_save_autosave(
    preset_value,
    rank_values,
    remain_values,
    qty_values,
    use_values,
    rank_ids,
    remain_ids,
    qty_ids,
    use_ids,
):
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
        "preset_value": preset_value,
        "ranks": ranks,
        "remain": remain,
        "qty": qty,
        "use": use,
    }


@callback(
    Output("gs-preset-dropdown", "value"),
    Output("gs-costume-display", "children", allow_duplicate=True),
    Output("gs-present-display", "children", allow_duplicate=True),
    Output("gs-load-feedback", "children", allow_duplicate=True),
    Output("gs-loaded-preset", "data", allow_duplicate=True),
    Output("gs-gift-list", "children", allow_duplicate=True),
    Input("gs-autosave-init", "n_intervals"),
    State("gs-autosave", "data"),
    prevent_initial_call=True,
)
def gs_restore_autosave(_n, data):
    if not data:
        raise PreventUpdate
    preset_value = data.get("preset_value")
    qty = data.get("qty") or {}
    use = data.get("use") or {}
    ranks = data.get("ranks") or {}
    remain = data.get("remain") or {}

    if not preset_value:
        # プリセット未選択でも所持数・使用フラグは復元する
        gifts = load_gifts()
        gift_list = build_gs_gift_list(
            gifts,
            lambda g: gs_default_used(g),
            qty_by_gift=qty,
            use_by_gift=use,
        )
        return (None, no_update, no_update, no_update, no_update, gift_list)

    costume_children, present_children, feedback, store, gift_list = _gs_build_view(
        preset_value, ranks=ranks, qty=qty, use=use, remain=remain
    )
    if store is None:
        raise PreventUpdate
    return (
        preset_value,
        costume_children,
        present_children,
        feedback,
        store,
        gift_list,
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
) -> html.Table:
    """贈り物×衣装の配分マトリクス（MILP 解）。

    other_normal_alloc / other_high_alloc が list（衣装ごとの配分数）なら
    その他(通常)/その他(高級) の集約行として表示する。None なら非表示。
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

    # 現在の絆ランク（衣装index順）
    rank_by_idx = {rid["index"]: rv for rv, rid in zip(rank_values, rank_ids)}
    current_ranks = []
    for i in range(len(costumes)):
        v = rank_by_idx.get(i)
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = 20
        current_ranks.append(min(50, max(1, v)))

    # 次の絆上昇までの残り経験値（任意・衣装index順）。
    # 未入力/不正/0以下は None（= 通常どおりレベル満額を要求）。
    remain_by_idx = {rid["index"]: rv for rv, rid in zip(remain_values, remain_ids)}
    remaining_exp: list[int | None] = []
    for i in range(len(costumes)):
        rv = remain_by_idx.get(i)
        try:
            rv = int(rv)
        except (TypeError, ValueError):
            rv = None
        if rv is not None and rv <= 0:
            rv = None
        remaining_exp.append(rv)

    # 使用フラグ・所持数
    used_ids = {
        uid["gift"] for uid, val in zip(use_ids, use_values) if val and "use" in val
    }
    qty_by_gift = {}
    for qid, qv in zip(qty_ids, qty_values):
        try:
            qty_by_gift[qid["gift"]] = max(0, int(qv))
        except (TypeError, ValueError):
            qty_by_gift[qid["gift"]] = 0

    catalog = load_gifts()
    type_by_id = {g["id"]: g["gift_type"] for g in catalog}

    student = loaded["student_name"]
    status_name = loaded["status_name"]
    present = get_preset_present(student, status_name)  # 衣装名->{gift:tier}
    preferred = get_preset_preferred_gift_ids(student, status_name)
    ncol = len(costumes)

    # 使用ON贈り物を「個別」と「その他(集約)」に振り分ける。
    #  個別     : 好み(present) / all型 / 贈り物選択ボックス
    #  その他通常: 上記以外の素 normal（非好み=一律20EXP相当）
    #  その他高級: 上記以外の素 high （非好み=一律120EXP相当）
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
                {"idx": i, "name": s["costume_name"]} for i, s in enumerate(students)
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
