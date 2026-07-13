"""生徒ステータスCSVパーサーのテスト。"""

import csv

import pytest

from app.backend.status_csv import (
    ParseResult,
    parse_status_csv,
    split_student_costume,
)

# CSVの列数（絆ボーナス第2の合計列まで含める）
_NUM_COLS = 88


def _make_row(
    name: str,
    stat1: str = "",
    values1: list | None = None,
    total1: str = "",
    stat2: str = "",
    values2: list | None = None,
    total2: str = "",
) -> list[str]:
    row = [""] * _NUM_COLS
    row[1] = name
    row[51] = stat1
    if values1:
        for i, v in enumerate(values1):
            row[52 + i] = str(v)
    row[59] = total1
    row[60] = stat2
    if values2:
        for i, v in enumerate(values2):
            row[61 + i] = str(v)
    row[66] = total2
    return row


def _write_csv(tmp_path, data_rows: list[list[str]]):
    path = tmp_path / "status.csv"
    header = [[""] * _NUM_COLS for _ in range(4)]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(header + data_rows)
    return path


# アル相当: 攻撃力(第1) + 最大HP(第2)
_ARU = dict(
    stat1="攻撃力",
    values1=[4, 6, 7, 9, 2, 4, 6],
    total1="246",
    stat2="最大HP",
    values2=[48, 58, 10, 15, 25],
    total2="1030",
)


class TestSplitStudentCostume:
    def test_no_paren(self):
        assert split_student_costume("アル") == ("アル", "通常")

    def test_fullwidth_paren(self):
        assert split_student_costume("アル（正月）") == ("アル", "正月")

    def test_halfwidth_paren(self):
        assert split_student_costume("アル(正月)") == ("アル", "正月")

    def test_form_suffix(self):
        assert split_student_costume("ホシノ（臨戦）#1") == ("ホシノ", "臨戦")

    def test_name_with_symbol(self):
        assert split_student_costume("シロコ＊テラー") == ("シロコ＊テラー", "通常")


class TestParseStatusCsv:
    def test_basic_two_status(self, tmp_path):
        path = _write_csv(tmp_path, [_make_row("アル", **_ARU)])
        result = parse_status_csv(path)
        assert isinstance(result, ParseResult)
        assert result.skipped == []
        assert len(result.presets) == 2
        atk = next(p for p in result.presets if p["status_name"] == "攻撃")
        hp = next(p for p in result.presets if p["status_name"] == "HP")
        assert atk["student_name"] == "アル"
        assert atk["costumes"] == [
            {"costume_name": "通常", "bond_bonuses": [4, 6, 7, 9, 2, 4, 6]}
        ]
        # 第2は絆11からなので先頭2区間は0
        assert hp["costumes"] == [
            {"costume_name": "通常", "bond_bonuses": [0, 0, 48, 58, 10, 15, 25]}
        ]

    def test_costume_grouping_and_zero_fill(self, tmp_path):
        # 通常=治癒力/HP、体操服=攻撃力/HP → 攻撃プリセットでは通常が全0
        rows = [
            _make_row(
                "ハナコ",
                stat1="治癒力",
                values1=[7, 11, 14, 18, 5, 7, 12],
                total1="483",
                stat2="最大HP",
                values2=[48, 57, 10, 15, 25],
                total2="1025",
            ),
            _make_row("ハナコ（体操服）", **_ARU),
        ]
        path = _write_csv(tmp_path, rows)
        result = parse_status_csv(path)
        by_status = {p["status_name"]: p for p in result.presets}
        assert set(by_status) == {"攻撃", "HP", "治癒力"}
        atk = by_status["攻撃"]
        assert [c["costume_name"] for c in atk["costumes"]] == ["通常", "体操服"]
        assert atk["costumes"][0]["bond_bonuses"] == [0] * 7
        assert atk["costumes"][1]["bond_bonuses"] == [4, 6, 7, 9, 2, 4, 6]
        heal = by_status["治癒力"]
        assert heal["costumes"][1]["bond_bonuses"] == [0] * 7

    def test_default_costume_first(self, tmp_path):
        # 通常がCSVで後ろにあっても先頭に並ぶ
        rows = [
            _make_row("アル（正月）", **_ARU),
            _make_row("アル", **_ARU),
        ]
        path = _write_csv(tmp_path, rows)
        result = parse_status_csv(path)
        atk = next(p for p in result.presets if p["status_name"] == "攻撃")
        assert [c["costume_name"] for c in atk["costumes"]] == ["通常", "正月"]

    def test_form_rows_merged(self, tmp_path):
        rows = [
            _make_row("ホシノ（臨戦）#1", **_ARU),
            _make_row("ホシノ（臨戦）#2", **_ARU),
        ]
        path = _write_csv(tmp_path, rows)
        result = parse_status_csv(path)
        assert result.skipped == []
        atk = next(p for p in result.presets if p["status_name"] == "攻撃")
        assert [c["costume_name"] for c in atk["costumes"]] == ["臨戦"]

    def test_form_rows_conflict_reported(self, tmp_path):
        other = dict(_ARU, values1=[1, 1, 1, 1, 1, 1, 1], total1="49")
        rows = [
            _make_row("ホシノ（臨戦）#1", **_ARU),
            _make_row("ホシノ（臨戦）#2", **other),
        ]
        path = _write_csv(tmp_path, rows)
        result = parse_status_csv(path)
        assert len(result.skipped) == 1
        assert "不一致" in result.skipped[0][1]

    def test_empty_bonus_skipped(self, tmp_path):
        path = _write_csv(tmp_path, [_make_row("初音ミク")])
        result = parse_status_csv(path)
        assert result.presets == []
        assert result.skipped == [("初音ミク", "絆ボーナス未入力")]

    def test_total_mismatch_skipped(self, tmp_path):
        bad = dict(_ARU, total1="999")
        path = _write_csv(tmp_path, [_make_row("アル", **bad)])
        result = parse_status_csv(path)
        assert result.presets == []
        assert len(result.skipped) == 1
        assert "合計不一致" in result.skipped[0][1]

    def test_missing_value_skipped(self, tmp_path):
        bad = dict(_ARU, values1=[4, 6, 7, 9, 2, 4])  # 6値しかない
        path = _write_csv(tmp_path, [_make_row("アル", **bad)])
        result = parse_status_csv(path)
        assert result.presets == []
        assert "欠損" in result.skipped[0][1]

    def test_real_csv(self):
        """リポジトリ内の実CSVが読めることの回帰テスト。"""
        path = (
            "data/生徒ステータスまとめ (仮) 公開用 - ステータス .csv"
        )
        try:
            result = parse_status_csv(path)
        except FileNotFoundError:
            pytest.skip("実CSVなし")
        assert len(result.presets) > 250
        # ワカモ(攻撃) は既知の値
        wakamo = next(
            p
            for p in result.presets
            if p["student_name"] == "ワカモ" and p["status_name"] == "攻撃"
        )
        normal = next(
            c for c in wakamo["costumes"] if c["costume_name"] == "通常"
        )
        assert normal["bond_bonuses"] == [3, 5, 7, 9, 2, 3, 6]
