"""プリセット定義。

data/presets.json から読み込む。
各プリセットは生徒リスト。
各生徒は {"costume_name": str, "bond_bonuses": [int x7]} の辞書。
bond_bonuses の順序: 絆2~5, 6~10, 11~15, 16~20, 21~30, 31~40, 41~50
"""

import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent.parent

_PRESETS_PATH = _BASE_DIR / "data" / "presets.json"


def _load_presets() -> dict[str, list[dict]]:
    """data/presets.json を読み込む。

    data/ は .gitignore 対象のローカル専用ディレクトリのため、
    CI などファイルが無い環境では空辞書を返す。アプリのプリセットは
    DB (user_presets) 側で管理しており、ここは検証用データの入口。
    """
    if not _PRESETS_PATH.exists():
        return {}
    with open(_PRESETS_PATH, encoding="utf-8") as f:
        return json.load(f)


PRESETS: dict[str, list[dict]] = _load_presets()
