import sys
from pathlib import Path

from dash import Dash

# PyInstaller バンドル時は _MEIPASS、通常時はプロジェクトルート
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent

app = Dash(
    __name__,
    assets_folder=str(_BASE_DIR / "assets"),
    suppress_callback_exceptions=True,
    title="絆上げ優先度計算機",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
