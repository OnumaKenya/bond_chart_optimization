"""生徒ステータスまとめCSV（絆ランクボーナス列）のパーサー。

CSVの絆ランクボーナスは1行（=1衣装）につき2ステータス:
  - 第1: 絆2から上昇。区間 2~5, 6~10, 11~15, 16~20, 21~30, 31~40, 41~50 の7値
  - 第2: 絆11から上昇。区間 11~15 以降の5値（先頭2区間は0として扱う）
どちらも「区間ごとの1ランクあたり上昇量」で、合計列と検算できる。

同一生徒の別衣装は「生徒名（衣装名）」の行として並ぶ。フォーム違いで
絆ボーナスが同一の行は「生徒名（衣装名）#1」のように枝番が付く。
"""

import csv
import re
from dataclasses import dataclass, field

from app.backend.student import BOND_RANGES

# CSV列 (0-indexed)
_COL_NAME = 1
_COL_STAT1 = 51  # 第1ステータス名。52~58 が7区間、59 が合計
_COL_STAT2 = 60  # 第2ステータス名。61~65 が5区間、66 が合計
_MIN_COLS = 67
_HEADER_ROWS = 4

# 各区間のランク数（合計列の検算用）
_WIDTHS1 = (4, 5, 5, 5, 10, 10, 10)
_WIDTHS2 = (5, 5, 10, 10, 10)

NUM_RANGES = len(BOND_RANGES)

# CSVのステータス表記 -> プリセットのステータス名
STATUS_NAME_MAP = {
    "攻撃力": "攻撃",
    "最大HP": "HP",
    "治癒力": "治癒力",
    "防御力": "防御",
}

# プリセットのステータス表示順
STATUS_ORDER = ("攻撃", "HP", "治癒力", "防御")

# 「生徒名（衣装名）」の分解。半角括弧も許容。
_PAREN_RE = re.compile(r"^(.+?)[（(](.+?)[）)]$")
# フォーム違いの枝番 (#1, ＃2 など)
_FORM_SUFFIX_RE = re.compile(r"\s*[#＃]\d+$")

DEFAULT_COSTUME_NAME = "通常"


@dataclass
class CostumeBonuses:
    """1衣装分の絆ボーナス。bonuses は {ステータス名: [int x7]}。"""

    student_name: str
    costume_name: str
    bonuses: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class ParseResult:
    """パース結果。

    presets: [{student_name, status_name, costumes: [{costume_name, bond_bonuses}]}]
        生徒×ステータスごとに全衣装を含む（該当ステータスの上昇が無い
        衣装は全0）。プリセットDBの1レコードに対応する。
    skipped: [(行の生徒名, 理由)] 取り込めなかった行。
    """

    presets: list[dict]
    skipped: list[tuple[str, str]]


def split_student_costume(raw_name: str) -> tuple[str, str]:
    """「生徒名（衣装名）」を (生徒名, 衣装名) に分解する。枝番は除去。"""
    name = _FORM_SUFFIX_RE.sub("", raw_name.strip())
    m = _PAREN_RE.match(name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return name, DEFAULT_COSTUME_NAME


def _parse_ints(row: list[str], cols: range) -> list[int] | None:
    """指定列を整数リストとして読む。欠損・非数値なら None。"""
    out = []
    for c in cols:
        cell = row[c].strip().replace(",", "")
        if not cell or cell in ("-", "#DIV/0!"):
            return None
        try:
            out.append(int(cell))
        except ValueError:
            return None
    return out


def _parse_row_bonuses(row: list[str]) -> dict[str, list[int]] | str:
    """1行の絆ボーナスを {ステータス名: [int x7]} にする。

    取り込めない場合は理由の文字列を返す。
    """
    stat1_raw = row[_COL_STAT1].strip()
    stat2_raw = row[_COL_STAT2].strip()
    if not stat1_raw and not stat2_raw:
        return "絆ボーナス未入力"

    bonuses: dict[str, list[int]] = {}

    # 第1 (絆2から、7区間)
    if stat1_raw:
        status = STATUS_NAME_MAP.get(stat1_raw)
        if status is None:
            return f"未知のステータス名: {stat1_raw}"
        values = _parse_ints(row, range(_COL_STAT1 + 1, _COL_STAT1 + 8))
        total = _parse_ints(row, range(_COL_STAT1 + 8, _COL_STAT1 + 9))
        if values is None or total is None:
            return "第1ボーナスの値が欠損"
        if sum(v * w for v, w in zip(values, _WIDTHS1)) != total[0]:
            return f"第1ボーナスの合計不一致 (期待 {total[0]})"
        bonuses[status] = values

    # 第2 (絆11から、5区間。先頭2区間は0)
    if stat2_raw:
        status = STATUS_NAME_MAP.get(stat2_raw)
        if status is None:
            return f"未知のステータス名: {stat2_raw}"
        if status in bonuses:
            return f"第1と第2が同一ステータス: {stat2_raw}"
        values = _parse_ints(row, range(_COL_STAT2 + 1, _COL_STAT2 + 6))
        total = _parse_ints(row, range(_COL_STAT2 + 6, _COL_STAT2 + 7))
        if values is None or total is None:
            return "第2ボーナスの値が欠損"
        if sum(v * w for v, w in zip(values, _WIDTHS2)) != total[0]:
            return f"第2ボーナスの合計不一致 (期待 {total[0]})"
        bonuses[status] = [0, 0] + values

    return bonuses


def parse_status_csv(path) -> ParseResult:
    """CSVを読み、プリセットDBに対応する形へ変換する。"""
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    skipped: list[tuple[str, str]] = []
    # 生徒 -> {衣装名: CostumeBonuses}。出現順を保つ。
    students: dict[str, dict[str, CostumeBonuses]] = {}

    for row in rows[_HEADER_ROWS:]:
        if len(row) < _MIN_COLS:
            continue
        raw_name = row[_COL_NAME].strip()
        if not raw_name:
            continue
        result = _parse_row_bonuses(row)
        if isinstance(result, str):
            skipped.append((raw_name, result))
            continue
        student_name, costume_name = split_student_costume(raw_name)
        costumes = students.setdefault(student_name, {})
        existing = costumes.get(costume_name)
        if existing is not None:
            # 枝番違いのフォーム行。値が一致していれば同一衣装として扱う。
            if existing.bonuses != result:
                skipped.append((raw_name, "同名衣装で絆ボーナスが不一致"))
            continue
        costumes[costume_name] = CostumeBonuses(student_name, costume_name, result)

    presets: list[dict] = []
    for student_name, costumes in students.items():
        ordered = _order_costumes(list(costumes.values()))
        status_names = {s for c in ordered for s in c.bonuses}
        for status in STATUS_ORDER:
            if status not in status_names:
                continue
            presets.append(
                {
                    "student_name": student_name,
                    "status_name": status,
                    "costumes": [
                        {
                            "costume_name": c.costume_name,
                            "bond_bonuses": c.bonuses.get(status, [0] * NUM_RANGES),
                        }
                        for c in ordered
                    ],
                }
            )
    return ParseResult(presets=presets, skipped=skipped)


def _order_costumes(costumes: list[CostumeBonuses]) -> list[CostumeBonuses]:
    """通常を先頭に、それ以外はCSV出現順のまま返す。"""
    return sorted(
        costumes,
        key=lambda c: (c.costume_name != DEFAULT_COSTUME_NAME,),
    )
