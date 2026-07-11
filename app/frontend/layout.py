import sys
from pathlib import Path

from dash import html, dcc

from app.backend.student import BOND_RANGES
from app.backend.user_presets import (
    get_all_presets_for_dropdown,
    gift_image_src,
    load_gifts,
)

# PyInstaller バンドル時は _MEIPASS、通常時はプロジェクトルート
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent.parent

_MANUAL_MD = (_BASE_DIR / "docs" / "manual.md").read_text(encoding="utf-8")
_PRIVACY_MD = (_BASE_DIR / "docs" / "privacy.md").read_text(encoding="utf-8")

LABEL_STYLE = {"fontSize": "1rem", "whiteSpace": "nowrap"}


def _default_costume_name(index: int) -> str:
    return f"衣装{index + 1}"


def make_student_card(
    index: int,
    *,
    costume_name: str = "",
    bond_bonuses: list[int] | None = None,
) -> html.Div:
    """生徒入力カードを1つ生成する。"""
    if bond_bonuses is None:
        bond_bonuses = [0] * len(BOND_RANGES)

    bond_fields = []
    for i, (lo, hi) in enumerate(BOND_RANGES):
        bond_fields.append(
            html.Div(
                [
                    html.Label(f"絆{lo}~{hi}", style=LABEL_STYLE),
                    dcc.Input(
                        id={"type": "bond", "range_idx": i, "index": index},
                        type="number",
                        value=bond_bonuses[i],
                        min=0,
                        debounce=True,
                        autoComplete="off",
                        style={"width": "72px", "textAlign": "center"},
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                },
            )
        )

    return html.Div(
        [
            # ヘッダー行
            html.Div(
                [
                    html.Strong(f"衣装 {index + 1}"),
                    dcc.Input(
                        id={"type": "costume", "index": index},
                        type="text",
                        placeholder="衣装名",
                        value=costume_name or _default_costume_name(index),
                        style={"marginLeft": "8px", "flex": "1", "fontSize": "0.85rem"},
                    ),
                    html.Button(
                        "✕",
                        id={"type": "remove-student", "index": index},
                        n_clicks=0,
                        className="remove-student-btn",
                        style={
                            "marginLeft": "auto",
                            "background": "none",
                            "border": "none",
                            "cursor": "pointer",
                            "fontSize": "1.1rem",
                        },
                    ),
                ],
                className="student-card-header",
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "8px",
                },
            ),
            # 絆ボーナス入力行
            html.Div(
                bond_fields,
                className="bond-fields",
                style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
            ),
        ],
        id={"type": "student-card", "index": index},
        className="student-card",
        style={
            "border": "1px solid #ccc",
            "borderRadius": "8px",
            "padding": "12px",
            "marginBottom": "10px",
            "background": "#fafafa",
        },
    )


def _make_bond_rank_input(
    index: int, *, costume_name: str = "", value: int = 20
) -> html.Div:
    """衣装ごとの現在の絆ランク入力欄を1つ生成する。"""
    btn_style = {
        "width": "24px",
        "height": "14px",
        "border": "1px solid #ccc",
        "background": "#f5f5f5",
        "cursor": "pointer",
        "fontSize": "0.65rem",
        "lineHeight": "1",
        "padding": "0",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
    }
    return html.Div(
        [
            html.Label(
                costume_name or _default_costume_name(index),
                id={"type": "bond-rank-label", "index": index},
                style={**LABEL_STYLE, "textAlign": "center"},
            ),
            html.Div(
                [
                    dcc.Input(
                        id={"type": "bond-rank", "index": index},
                        type="number",
                        value=value,
                        debounce=True,
                        style={"width": "50px", "textAlign": "center"},
                    ),
                    html.Div(
                        [
                            html.Button(
                                "▲",
                                id={"type": "bond-rank-inc", "index": index},
                                n_clicks=0,
                                style={**btn_style, "borderRadius": "3px 3px 0 0"},
                            ),
                            html.Button(
                                "▼",
                                id={"type": "bond-rank-dec", "index": index},
                                n_clicks=0,
                                style={**btn_style, "borderRadius": "0 0 3px 3px"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "flexDirection": "column",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "1px"},
            ),
        ],
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "4px",
        },
    )


def _contact_span(nowrap: bool = True) -> html.Span:
    """不具合・要望報告の連絡先（フォーム / X アカウント）。"""
    link_style = {"color": "#4a90d9", "textDecoration": "underline"}
    style = {"fontSize": "0.85rem"}
    if nowrap:
        style["whiteSpace"] = "nowrap"
    return html.Span(
        [
            "不具合・要望報告は外部サービスの",
            html.A(
                "フォーム",
                href="https://forms.gle/yxJYDAY55TPDkMr39",
                target="_blank",
                rel="noopener noreferrer",
                style=link_style,
            ),
            "か",
            html.A(
                "Xアカウント",
                href="https://x.com/yankeiori",
                target="_blank",
                rel="noopener noreferrer",
                style=link_style,
            ),
            "まで",
        ],
        style=style,
    )


def _footer() -> html.Div:
    """全ページ共通フッター。プライバシーポリシーへのリンクを置く。"""
    return html.Div(
        [
            dcc.Link(
                "プライバシーポリシー",
                href="/privacy",
                style={"color": "#4a90d9", "textDecoration": "underline"},
            ),
        ],
        style={
            "marginTop": "32px",
            "paddingTop": "12px",
            "borderTop": "1px solid #ddd",
            "textAlign": "center",
            "fontSize": "0.8rem",
            "color": "#888",
        },
    )


def create_privacy_layout() -> html.Div:
    """プライバシーポリシー表示ページ。"""
    return html.Div(
        [
            html.Div(
                [
                    dcc.Link(
                        "← 計算機に戻る",
                        href="/chart-opt",
                        style={
                            "color": "#4a90d9",
                            "textDecoration": "none",
                            "fontSize": "0.9rem",
                        },
                    ),
                ],
                style={"marginBottom": "16px"},
            ),
            dcc.Markdown(
                _PRIVACY_MD,
                style={
                    "background": "#fff",
                    "padding": "24px",
                    "borderRadius": "8px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
                    "lineHeight": "1.7",
                },
            ),
            _footer(),
        ],
        style={
            "maxWidth": "820px",
            "margin": "24px auto",
            "padding": "0 20px",
        },
    )


def _page_switch_link(current_path: str) -> dcc.Link:
    """現在のページ以外のページへ切り替えるリンク（タイトル横に配置）。"""
    target_path, target_label = next(
        (path, label) for path, (label, _) in PAGES.items() if path != current_path
    )
    return dcc.Link(
        f"🔀 {target_label}",
        href=target_path,
        className="page-switch-link",
        style={
            "fontSize": "0.9rem",
            "color": "#4a90d9",
            "fontWeight": "bold",
            "textDecoration": "none",
            "border": "1px solid #4a90d9",
            "borderRadius": "6px",
            "padding": "6px 14px",
            "background": "#fff",
            "whiteSpace": "nowrap",
        },
    )


def create_layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("絆上げ優先度計算機", style={"margin": "0"}),
                            _page_switch_link("/chart-opt"),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "gap": "16px",
                            "flexWrap": "wrap",
                        },
                    ),
                    html.Div(
                        [
                            _contact_span(),
                            html.Button(
                                "📖 マニュアル",
                                id="open-manual-btn",
                                n_clicks=0,
                                style={
                                    "background": "#4a90d9",
                                    "color": "white",
                                    "border": "none",
                                    "borderRadius": "4px",
                                    "padding": "6px 16px",
                                    "cursor": "pointer",
                                    "fontSize": "0.9rem",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                        ],
                        className="page-header-right",
                        style={
                            "marginLeft": "auto",
                            "display": "flex",
                            "alignItems": "center",
                            "gap": "12px",
                        },
                    ),
                ],
                className="page-header",
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "16px",
                },
            ),
            # マニュアルモーダル
            html.Div(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Strong("マニュアル", style={"fontSize": "1.2rem"}),
                                html.Button(
                                    "✕",
                                    id="close-manual-btn",
                                    n_clicks=0,
                                    style={
                                        "marginLeft": "auto",
                                        "background": "none",
                                        "border": "none",
                                        "cursor": "pointer",
                                        "fontSize": "1.3rem",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "borderBottom": "1px solid #ddd",
                                "paddingBottom": "8px",
                                "marginBottom": "12px",
                            },
                        ),
                        dcc.Markdown(
                            _MANUAL_MD, style={"overflowY": "auto", "flex": "1"}
                        ),
                    ],
                    className="manual-modal-content",
                ),
                id="manual-modal",
                className="manual-modal-overlay",
                style={"display": "none"},
            ),
            html.Div(
                [
                    # サイドバー
                    html.Div(
                        [
                            # プリセット読み込み
                            html.Div(
                                [
                                    html.Strong("プリセット"),
                                    html.Div(
                                        [
                                            html.Div(
                                                dcc.Dropdown(
                                                    id="preset-dropdown",
                                                    options=get_all_presets_for_dropdown(),
                                                    placeholder="選択...",
                                                ),
                                                style={"flex": "1", "minWidth": "0"},
                                            ),
                                            html.Button(
                                                "☆",
                                                id="fav-toggle-btn",
                                                n_clicks=0,
                                                title="お気に入りに追加/解除",
                                                style={
                                                    "flexShrink": "0",
                                                    "background": "none",
                                                    "border": "1px solid #ccc",
                                                    "borderRadius": "4px",
                                                    "cursor": "pointer",
                                                    "fontSize": "1.1rem",
                                                    "padding": "4px 10px",
                                                    "lineHeight": "1",
                                                },
                                            ),
                                        ],
                                        style={
                                            "display": "flex",
                                            "gap": "6px",
                                            "alignItems": "stretch",
                                            "marginTop": "6px",
                                        },
                                    ),
                                    html.Button(
                                        "読み込み",
                                        id="load-preset-btn",
                                        n_clicks=0,
                                        style={
                                            "marginTop": "8px",
                                            "width": "100%",
                                            "background": "#27ae60",
                                            "color": "white",
                                            "border": "none",
                                            "borderRadius": "4px",
                                            "padding": "6px 16px",
                                            "cursor": "pointer",
                                        },
                                    ),
                                ],
                                className="preset-section",
                                style={
                                    "padding": "10px",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "8px",
                                    "background": "#f5f5ff",
                                },
                            ),
                            # プリセット投稿
                            html.Details(
                                [
                                    html.Summary(
                                        "プリセット投稿",
                                        style={
                                            "cursor": "pointer",
                                            "fontWeight": "bold",
                                        },
                                    ),
                                    html.Div(
                                        [
                                            html.P(
                                                "現在の絆ボーナスの入力内容を、全ユーザーが利用できるプリセットとして共有します。"
                                                "保存機能ではありません。",
                                                style={
                                                    "fontSize": "0.8rem",
                                                    "color": "#666",
                                                    "margin": "0 0 8px 0",
                                                },
                                            ),
                                            dcc.Input(
                                                id="submit-character-name",
                                                type="text",
                                                placeholder="生徒名を入力...",
                                                style={
                                                    "width": "100%",
                                                    "marginTop": "6px",
                                                    "fontSize": "0.85rem",
                                                },
                                            ),
                                            dcc.Dropdown(
                                                id="submit-status-name",
                                                options=[
                                                    {"label": s, "value": s}
                                                    for s in (
                                                        "攻撃",
                                                        "HP",
                                                        "治癒力",
                                                        "防御",
                                                    )
                                                ],
                                                placeholder="ステータス名を選択...",
                                                style={
                                                    "marginTop": "6px",
                                                    "fontSize": "0.85rem",
                                                },
                                            ),
                                            dcc.ConfirmDialogProvider(
                                                html.Button(
                                                    "投稿",
                                                    style={
                                                        "marginTop": "8px",
                                                        "width": "100%",
                                                        "background": "#e67e22",
                                                        "color": "white",
                                                        "border": "none",
                                                        "borderRadius": "4px",
                                                        "padding": "6px 16px",
                                                        "cursor": "pointer",
                                                    },
                                                ),
                                                id="submit-preset-btn",
                                                message="プリセットを投稿しますか？",
                                            ),
                                            html.Div(
                                                id="submit-feedback",
                                                style={
                                                    "marginTop": "6px",
                                                    "fontSize": "0.8rem",
                                                },
                                            ),
                                        ],
                                        style={"marginTop": "8px"},
                                    ),
                                ],
                                className="submit-section",
                                style={
                                    "padding": "10px",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "8px",
                                    "background": "#fff8f0",
                                    "marginTop": "12px",
                                },
                            ),
                        ],
                        className="sidebar",
                        style={
                            "width": "220px",
                            "flexShrink": "0",
                            "position": "sticky",
                            "top": "20px",
                            "alignSelf": "flex-start",
                            "zIndex": "10",
                        },
                    ),
                    # メインコンテンツ
                    html.Div(
                        [
                            html.Div(
                                id="students-container",
                                children=[make_student_card(0)],
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        "+ 衣装追加",
                                        id="add-student-btn",
                                        className="add-student-btn",
                                        n_clicks=0,
                                        style={
                                            "padding": "8px 16px",
                                            "cursor": "pointer",
                                            "borderRadius": "6px",
                                            "border": "1px solid #ccc",
                                            "background": "#fff",
                                            "fontSize": "0.95rem",
                                        },
                                    ),
                                ],
                                style={"marginBottom": "16px"},
                            ),
                            # 現在の絆ランク入力
                            html.Div(
                                [
                                    html.Strong(
                                        "現在の絆ランク",
                                        style={
                                            "marginBottom": "8px",
                                            "display": "block",
                                        },
                                    ),
                                    html.Div(
                                        id="bond-rank-container",
                                        children=[_make_bond_rank_input(0)],
                                        className="bond-rank-row",
                                        style={
                                            "display": "flex",
                                            "gap": "8px",
                                            "flexWrap": "wrap",
                                        },
                                    ),
                                ],
                                className="bond-rank-section",
                                style={
                                    "padding": "12px",
                                    "border": "1px solid #ccc",
                                    "borderRadius": "8px",
                                    "background": "#f0f8f0",
                                    "marginBottom": "16px",
                                },
                            ),
                            # 高度な設定（折りたたみ）
                            html.Details(
                                [
                                    html.Summary(
                                        "高度な設定",
                                        style={
                                            "cursor": "pointer",
                                            "fontWeight": "bold",
                                            "marginBottom": "8px",
                                        },
                                    ),
                                    html.Div(
                                        [
                                            # 衣装優先度
                                            html.Div(
                                                [
                                                    html.Strong(
                                                        "衣装優先度（タイブレーク）",
                                                        style={
                                                            "display": "block",
                                                            "marginBottom": "6px",
                                                        },
                                                    ),
                                                    html.P(
                                                        "上が高優先。同スコア時に優先度が高い衣装を先にします。",
                                                        style={
                                                            "fontSize": "0.8rem",
                                                            "color": "#666",
                                                            "margin": "0 0 8px 0",
                                                        },
                                                    ),
                                                    html.Div(
                                                        id="costume-priority-container",
                                                        style={
                                                            "display": "flex",
                                                            "flexDirection": "column",
                                                            "gap": "4px",
                                                        },
                                                    ),
                                                ],
                                                style={"marginBottom": "16px"},
                                            ),
                                            # 絆50ペナルティ
                                            html.Div(
                                                [
                                                    html.Strong(
                                                        "絆50到達ペナルティ",
                                                        style={
                                                            "display": "block",
                                                            "marginBottom": "6px",
                                                        },
                                                    ),
                                                    html.P(
                                                        "絆50到達時のボーナス減衰率。1に近いほど50到達を後回しにします。",
                                                        style={
                                                            "fontSize": "0.8rem",
                                                            "color": "#666",
                                                            "margin": "0 0 8px 0",
                                                        },
                                                    ),
                                                    dcc.Slider(
                                                        id="bond50-penalty",
                                                        min=0,
                                                        max=1,
                                                        step=0.05,
                                                        value=0,
                                                        marks={
                                                            0: "0",
                                                            0.25: "0.25",
                                                            0.5: "0.5",
                                                            0.75: "0.75",
                                                            1: "1",
                                                        },
                                                        tooltip={
                                                            "placement": "bottom",
                                                            "always_visible": True,
                                                        },
                                                    ),
                                                ],
                                            ),
                                        ],
                                        style={
                                            "padding": "12px",
                                            "border": "1px solid #ddd",
                                            "borderRadius": "8px",
                                            "background": "#f9f9ff",
                                        },
                                    ),
                                ],
                                style={"marginBottom": "16px"},
                            ),
                            # チャート計算ボタン
                            html.Div(
                                html.Button(
                                    "チャート計算",
                                    id="calc-chart-btn",
                                    n_clicks=0,
                                    style={
                                        "width": "100%",
                                        "padding": "12px 24px",
                                        "fontSize": "1.1rem",
                                        "fontWeight": "bold",
                                        "background": "#4a90d9",
                                        "color": "white",
                                        "border": "none",
                                        "borderRadius": "6px",
                                        "cursor": "pointer",
                                    },
                                ),
                                className="calc-btn-wrapper",
                            ),
                            # 計算結果表示エリア
                            html.Div(
                                id="chart-result",
                                className="chart-result-area",
                                style={"marginTop": "16px"},
                            ),
                        ],
                        style={"flex": "1", "minWidth": "0"},
                    ),
                ],
                className="main-columns",
                style={"display": "flex", "gap": "20px", "alignItems": "flex-start"},
            ),
            # 非表示 Store 群
            dcc.Store(id="student-indices", data=[0]),
            dcc.Store(id="next-student-index", data=1),
            dcc.Store(id="solver-inputs"),
            dcc.Store(id="submit-preset-status"),
            dcc.Store(id="costume-priority-order", data=[{"idx": 0, "name": "衣装1"}]),
            dcc.Store(id="autosave", storage_type="local"),
            dcc.Store(id="favorites", storage_type="local", data=[]),
            dcc.Interval(id="autosave-init", max_intervals=1, interval=200),
            _footer(),
        ],
        className="page-container",
        style={
            "maxWidth": "1200px",
            "margin": "0 auto",
            "padding": "20px",
            "fontFamily": "sans-serif",
        },
    )


# ======================================================================
# 贈り物配分シミュレータ（ページ）
# ======================================================================

# プリセットの好み/all 型に関わらず、常にデフォルト使用可とする贈り物。
_GS_ALWAYS_USED = {"gift-select-box"}


def gs_default_used(gift: dict, preferred: set | frozenset = frozenset()) -> bool:
    """贈り物の使用フラグ既定値。

    好み(preferred) に入る / type に all を含む / 常時使用対象 のとき可。
    """
    return (
        gift["id"] in _GS_ALWAYS_USED
        or gift["id"] in preferred
        or "all" in gift["gift_type"]
    )


def _gs_gift_card(gift: dict, default_use: bool, qty: int = 0) -> html.Div:
    """贈り物1件のコンパクトカード（アイコン・所持数・使用可否）。

    名前は非表示で、マウスオーバー時に title で表示する。
    """
    gid = gift["id"]
    is_high = gift["gift_type"] in ("high", "high-all")
    return html.Div(
        [
            html.Img(
                src=gift_image_src(gift),
                style={"width": "34px", "height": "26px", "objectFit": "contain"},
            ),
            html.Div(
                [
                    dcc.Checklist(
                        id={"type": "gs-gift-use", "gift": gid},
                        options=[{"label": "", "value": "use"}],
                        value=["use"] if default_use else [],
                        style={"margin": "0"},
                    ),
                    dcc.Input(
                        id={"type": "gs-gift-qty", "gift": gid},
                        type="number",
                        min=0,
                        value=qty,
                        debounce=True,
                        style={
                            "width": "38px",
                            "textAlign": "center",
                            "fontSize": "0.7rem",
                            "padding": "1px",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "2px"},
            ),
        ],
        className="gs-gift-card",
        title=gift["name"],
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "2px",
            "padding": "3px",
            "border": "1px solid #ccc",
            "borderRadius": "4px",
            "background": "#ede7f6" if is_high else "#fafafa",
        },
    )


def _gs_gift_grid(cards: list) -> html.Div:
    return html.Div(
        cards,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(56px, 1fr))",
            "gap": "4px",
        },
    )


def build_gs_gift_list(
    gifts: list[dict],
    is_used,
    qty_by_gift: dict | None = None,
    use_by_gift: dict | None = None,
) -> list:
    """使用フラグONの贈り物のみ表示し、残りは折りたたみに格納する。

    qty_by_gift / use_by_gift が与えられた場合は所持数・使用フラグの
    保存値で上書きする（入力復元用）。

    gs-gift-list の children として使う要素リストを返す。
    """
    qty_by_gift = qty_by_gift or {}
    use_by_gift = use_by_gift or {}
    used, unused = [], []
    for g in gifts:
        gid = g["id"]
        if gid in use_by_gift:
            u = bool(use_by_gift[gid])
        else:
            u = bool(is_used(g))
        qty = qty_by_gift.get(gid, 0)
        (used if u else unused).append(_gs_gift_card(g, u, qty))
    children = []
    if used:
        children.append(_gs_gift_grid(used))
    else:
        children.append(
            html.P(
                "使用する贈り物がありません。",
                style={"color": "#888", "fontSize": "0.8rem", "margin": "4px 0"},
            )
        )
    if unused:
        children.append(
            html.Details(
                [
                    html.Summary(
                        f"使用しない贈り物 ({len(unused)})",
                        style={
                            "cursor": "pointer",
                            "fontSize": "0.85rem",
                            "margin": "10px 0 4px",
                            "color": "#666",
                        },
                    ),
                    html.P(
                        "使用する場合はチェックを付けて所持数を入力してください。",
                        style={
                            "fontSize": "0.78rem",
                            "color": "#888",
                            "margin": "4px 0 8px",
                        },
                    ),
                    _gs_gift_grid(unused),
                ]
            )
        )
    return children


def create_gift_simulator_layout() -> html.Div:
    """贈り物配分シミュレータページ（入力部）。"""
    gifts = load_gifts()
    # プリセット未読込時は好み無し（all 型・常時使用対象のみ可）
    gift_list_children = build_gs_gift_list(gifts, lambda g: gs_default_used(g))
    return html.Div(
        [
            html.Div(
                [
                    html.H1("贈り物配分シミュレータ", style={"margin": "0"}),
                    _page_switch_link("/gift-simulation"),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "16px",
                    "flexWrap": "wrap",
                    "marginBottom": "4px",
                },
            ),
            html.Div(
                _contact_span(nowrap=False),
                style={"marginBottom": "16px"},
            ),
            # プリセット読み込み
            html.Div(
                [
                    html.Strong("プリセット"),
                    html.P(
                        [
                            "プリセットの追加は",
                            dcc.Link(
                                "絆上げ優先度計算機",
                                href="/chart-opt",
                                style={
                                    "color": "#4a90d9",
                                    "textDecoration": "underline",
                                },
                            ),
                            "から行ってください。",
                        ],
                        style={
                            "fontSize": "0.8rem",
                            "color": "#666",
                            "margin": "6px 0 0 0",
                        },
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id="gs-preset-dropdown",
                            options=get_all_presets_for_dropdown(),
                            placeholder="選択...",
                        ),
                        style={"marginTop": "6px"},
                    ),
                    html.Button(
                        "読み込み",
                        id="gs-load-preset-btn",
                        n_clicks=0,
                        style={
                            "marginTop": "8px",
                            "background": "#27ae60",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "6px 16px",
                            "cursor": "pointer",
                        },
                    ),
                    html.Div(
                        id="gs-load-feedback",
                        style={"marginTop": "6px", "fontSize": "0.85rem"},
                    ),
                ],
                style={
                    "padding": "12px",
                    "border": "1px solid #ccc",
                    "borderRadius": "8px",
                    "background": "#f5f5ff",
                    "marginBottom": "16px",
                    "maxWidth": "420px",
                },
            ),
            # 衣装・上昇量（表示のみ）＋ 現在の絆ランク入力
            html.Div(
                [
                    html.Strong("衣装 / 現在の絆ランク / 絆ボーナス"),
                    html.Div(
                        id="gs-costume-display",
                        children=html.P(
                            "プリセットを読み込んでください。",
                            style={"color": "#888", "margin": "8px 0"},
                        ),
                        style={"marginTop": "8px"},
                    ),
                ],
                style={
                    "padding": "12px",
                    "border": "1px solid #ccc",
                    "borderRadius": "8px",
                    "marginBottom": "16px",
                },
            ),
            # 衣装ごとの好物（normal 以外を 衣装×リアクション の表で表示）
            html.Div(
                [
                    html.Strong("衣装ごとの好物"),
                    html.Div(
                        id="gs-present-display",
                        children=html.P(
                            "プリセットを読み込んでください。",
                            style={"color": "#888", "margin": "8px 0"},
                        ),
                        style={"marginTop": "8px"},
                    ),
                ],
                style={
                    "padding": "12px",
                    "border": "1px solid #ccc",
                    "borderRadius": "8px",
                    "marginBottom": "16px",
                },
            ),
            # 贈り物リスト
            html.Div(
                [
                    html.Strong("贈り物（所持数・使用可否）"),
                    html.Div(
                        gift_list_children,
                        id="gs-gift-list",
                        style={"marginTop": "8px"},
                    ),
                ],
                style={
                    "padding": "12px",
                    "border": "1px solid #ccc",
                    "borderRadius": "8px",
                },
            ),
            # 計算開始
            html.Div(
                [
                    html.Button(
                        "計算開始",
                        id="gs-calc-btn",
                        n_clicks=0,
                        style={
                            "background": "#4a90d9",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "10px 32px",
                            "fontSize": "1rem",
                            "cursor": "pointer",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        children=html.Div(
                            id="gs-calc-result",
                            style={"marginTop": "12px", "minHeight": "24px"},
                        ),
                    ),
                ],
                style={"marginTop": "16px"},
            ),
            dcc.Store(id="gs-loaded-preset"),
            dcc.Store(id="gs-autosave", storage_type="local"),
            dcc.Interval(id="gs-autosave-init", max_intervals=1, interval=300),
            _footer(),
        ],
        className="page-container",
        style={
            "maxWidth": "1200px",
            "margin": "0 auto",
            "padding": "20px",
            "fontFamily": "sans-serif",
        },
    )


# ======================================================================
# ルートレイアウト（URL ルーティング）
# ======================================================================

# ページ切り替えリンクに出す主要ページ。
PAGES = {
    "/chart-opt": ("絆上げ優先度計算機", create_layout),
    "/gift-simulation": ("贈り物配分シミュレータ", create_gift_simulator_layout),
}

# 主要ページ以外のページ（フッター等からのみアクセス）。
EXTRA_PAGES = {
    "/privacy": ("プライバシーポリシー", create_privacy_layout),
}

# 旧ルート互換 / ルートからのリダイレクト先。
ROOT_REDIRECT = "/chart-opt"


def create_root_layout() -> html.Div:
    """dcc.Location によるページ切り替えのルートシェル。"""
    return html.Div(
        [
            dcc.Location(id="url"),
            html.Div(id="page-content"),
        ]
    )
