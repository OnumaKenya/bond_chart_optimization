import sys
from pathlib import Path

import dash_daq as daq
from dash import html, dcc

from app.backend.student import BOND_RANGES
from app.backend.user_presets import get_all_presets_for_dropdown

# PyInstaller バンドル時は _MEIPASS、通常時はプロジェクトルート
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent.parent

_MANUAL_MD = (_BASE_DIR / "docs" / "manual.md").read_text(encoding="utf-8")

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
                    daq.NumericInput(
                        id={"type": "bond", "range_idx": i, "index": index},
                        value=bond_bonuses[i],
                        min=0,
                        max=9999,
                        size=72,
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
    return html.Div(
        [
            html.Label(
                costume_name or _default_costume_name(index),
                id={"type": "bond-rank-label", "index": index},
                style={**LABEL_STYLE, "textAlign": "center"},
            ),
            daq.NumericInput(
                id={"type": "bond-rank", "index": index},
                value=value,
                min=1,
                max=50,
                size=80,
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
                            html.Span(
                                [
                                    "不具合・要望報告は",
                                    html.A(
                                        "フォーム",
                                        href="https://forms.gle/yxJYDAY55TPDkMr39",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                        style={
                                            "color": "#4a90d9",
                                            "textDecoration": "underline",
                                        },
                                    ),
                                    "か",
                                    html.A(
                                        "Xアカウント",
                                        href="https://x.com/yankeiori",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                        style={
                                            "color": "#4a90d9",
                                            "textDecoration": "underline",
                                        },
                                    ),
                                    "まで",
                                ],
                                style={
                                    "fontSize": "0.85rem",
                                    "whiteSpace": "nowrap",
                                },
                            ),
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
                                    dcc.Dropdown(
                                        id="preset-dropdown",
                                        options=get_all_presets_for_dropdown(),
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
                                className="preset-section",
                                style={
                                    "padding": "10px",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "8px",
                                    "background": "#f5f5ff",
                                },
                            ),
                            # プリセット投稿
                            html.Div(
                                [
                                    html.Strong(
                                        "現在の入力データをプリセットとして投稿"
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
                                    html.Button(
                                        "投稿",
                                        id="submit-preset-btn",
                                        n_clicks=0,
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
                                    html.Div(
                                        id="submit-feedback",
                                        style={
                                            "marginTop": "6px",
                                            "fontSize": "0.8rem",
                                        },
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
        ],
        className="page-container",
        style={
            "maxWidth": "1200px",
            "margin": "0 auto",
            "padding": "20px",
            "fontFamily": "sans-serif",
        },
    )
