import sys
from pathlib import Path

from dash import html, dcc

from app.backend.student import BOND_RANGES
from app.backend.presets import PRESETS

# PyInstaller バンドル時は _MEIPASS、通常時はプロジェクトルート
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent.parent

_MANUAL_MD = (_BASE_DIR / "docs" / "manual.md").read_text(encoding="utf-8")

LABEL_STYLE = {"fontSize": "0.85rem", "whiteSpace": "nowrap"}


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
                        step=1,
                        style={"width": "100%"},
                    ),
                ],
                style={"flex": "1", "minWidth": "70px"},
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
                        style={
                            "marginLeft": "auto",
                            "background": "none",
                            "border": "none",
                            "cursor": "pointer",
                            "fontSize": "1.1rem",
                        },
                    ),
                ],
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
    return html.Div(
        [
            html.Label(
                costume_name or _default_costume_name(index),
                id={"type": "bond-rank-label", "index": index},
                style={**LABEL_STYLE, "textAlign": "center"},
            ),
            dcc.Input(
                id={"type": "bond-rank", "index": index},
                type="number",
                value=value,
                min=1,
                max=50,
                step=1,
                style={"width": "60px", "textAlign": "center"},
            ),
        ],
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "4px",
        },
    )


def create_layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H1("絆上げ優先度計算機", style={"marginBottom": "0"}),
                    html.Div(
                        [
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
                                    dcc.Dropdown(
                                        id="preset-dropdown",
                                        options=[
                                            {"label": name, "value": name}
                                            for name in PRESETS
                                        ],
                                        placeholder="選択...",
                                        style={"marginTop": "6px"},
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
                                style={
                                    "padding": "10px",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "8px",
                                    "background": "#f5f5ff",
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
                                        "+ 衣装追加", id="add-student-btn", n_clicks=0
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
                                style={
                                    "padding": "12px",
                                    "border": "1px solid #ccc",
                                    "borderRadius": "8px",
                                    "background": "#f0f8f0",
                                    "marginBottom": "16px",
                                },
                            ),
                            # チャート計算ボタン
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
        ],
        className="page-container",
        style={
            "maxWidth": "1200px",
            "margin": "0 auto",
            "padding": "20px",
            "fontFamily": "sans-serif",
        },
    )
