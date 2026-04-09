import os

from dash import ALL, ClientsideFunction, Input, Output, State
from flask import request
from app import app as application
from app.frontend.layout import create_layout
import app.frontend.callbacks  # noqa: F401 - コールバック登録
import app.backend.api  # noqa: F401 - API エンドポイント登録

application.layout = create_layout


# Dash 内部エンドポイント (/_dash-layout 等) のキャッシュを無効化
# CDN/ブラウザが古いレイアウトを返すのを防ぐ
@application.server.after_request
def _no_cache_dash_endpoints(response):
    if "/_dash-" in (request.path or ""):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ===========================================================================
# クライアントサイドコールバック
# ===========================================================================


# --- チャート計算: ステップ1 スピナー表示 + 入力データ収集 ---
application.clientside_callback(
    ClientsideFunction("solver", "collect_inputs"),
    Output("chart-result", "children"),
    Output("solver-inputs", "data"),
    Input("calc-chart-btn", "n_clicks"),
    State({"type": "bond-rank", "index": ALL}, "value"),
    State({"type": "bond-rank", "index": ALL}, "id"),
    State({"type": "bond", "range_idx": ALL, "index": ALL}, "value"),
    State({"type": "bond", "range_idx": ALL, "index": ALL}, "id"),
    State({"type": "costume", "index": ALL}, "value"),
    State({"type": "costume", "index": ALL}, "id"),
    State("costume-priority-order", "data"),
    State("bond50-penalty", "value"),
    prevent_initial_call=True,
)

# --- チャート計算: ステップ2 DP 実行 + 結果表示 ---
application.clientside_callback(
    ClientsideFunction("solver", "calc_chart"),
    Output("chart-result", "children", allow_duplicate=True),
    Input("solver-inputs", "data"),
    prevent_initial_call=True,
)

# --- マニュアルモーダル開閉 ---
application.clientside_callback(
    """
    function(openClicks, closeClicks) {
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || triggered.length === 0) return window.dash_clientside.no_update;
        const id = triggered[0].prop_id.split('.')[0];
        if (id === 'open-manual-btn') return {display: 'flex'};
        return {display: 'none'};
    }
    """,
    Output("manual-modal", "style"),
    Input("open-manual-btn", "n_clicks"),
    Input("close-manual-btn", "n_clicks"),
    prevent_initial_call=True,
)

# gunicorn から参照される WSGI サーバー (gunicorn main:server)
server = application.server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = "PORT" not in os.environ
    application.run(host="0.0.0.0", port=port, debug=debug)
