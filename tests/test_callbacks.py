"""callbacks のヘルパー関数のテスト。

コールバック本体はDashサーバーが必要なため、純粋関数のみ検証する。
"""

from app.frontend.callbacks import (
    _gift_inputs_to_maps,
    _rb_costume_rows,
    _rb_int_keys,
    _rb_merge_use_flags,
    _rb_shift_indices,
    _rb_values_by_index,
)


class TestRbMergeUseFlags:
    CATALOG = [
        {"id": "gift-select-box", "gift_type": "normal"},
        {"id": "cake", "gift_type": "normal"},
        {"id": "doll", "gift_type": "high"},
        {"id": "flower-all", "gift_type": "high-all"},
    ]

    def test_new_favorite_turns_on(self):
        # 衣装追加で cake が好物になった → 既定値のままだった cake はONに
        out = _rb_merge_use_flags(self.CATALOG, {}, set(), {"cake"})
        assert out["cake"] is True
        assert out["doll"] is False
        assert out["gift-select-box"] is True  # 常時使用
        assert out["flower-all"] is True  # all 型

    def test_user_override_kept(self):
        # ユーザーが明示的にONにした doll は、好物でなくても保持
        use = {"doll": True}
        out = _rb_merge_use_flags(self.CATALOG, use, set(), {"cake"})
        assert out["doll"] is True

    def test_user_off_kept_when_still_favorite(self):
        # 好物だがユーザーがOFFにした cake は、衣装追加後もOFFのまま
        use = {"cake": False}
        out = _rb_merge_use_flags(self.CATALOG, use, {"cake"}, {"cake", "doll"})
        assert out["cake"] is False
        assert out["doll"] is True

    def test_removed_favorite_turns_off(self):
        # 衣装削除で doll が好物でなくなった → 既定値のままならOFFに
        use = {"doll": True}
        out = _rb_merge_use_flags(self.CATALOG, use, {"doll"}, set())
        assert out["doll"] is False


class TestGiftInputsToMaps:
    def test_maps(self):
        qty, use = _gift_inputs_to_maps(
            [3, None, "bad"],
            [{"gift": "a"}, {"gift": "b"}, {"gift": "c"}],
            [["use"], []],
            [{"gift": "a"}, {"gift": "b"}],
        )
        assert qty == {"a": 3, "b": 0, "c": 0}
        assert use == {"a": True, "b": False}


class TestRbIntKeys:
    def test_str_keys(self):
        assert _rb_int_keys({"0": 20, "2": 50}) == {0: 20, 2: 50}

    def test_none(self):
        assert _rb_int_keys(None) == {}


class TestRbValuesByIndex:
    def test_maps_by_index(self):
        values = [10, None, 30]
        ids = [{"index": 0}, {"index": 1}, {"index": 2}]
        assert _rb_values_by_index(values, ids) == {0: 10, 2: 30}

    def test_empty(self):
        assert _rb_values_by_index([], []) == {}


class TestRbShiftIndices:
    def test_remove_middle(self):
        # 行1を削除 → 行2以降が1つ繰り上がる
        assert _rb_shift_indices({0: "a", 1: "b", 2: "c"}, 1) == {0: "a", 1: "c"}

    def test_remove_first(self):
        assert _rb_shift_indices({0: "a", 1: "b"}, 0) == {0: "b"}

    def test_remove_last(self):
        assert _rb_shift_indices({0: "a", 1: "b"}, 1) == {0: "a"}

    def test_removed_index_absent(self):
        # 削除行に入力値が無くても他の行は正しく詰める
        assert _rb_shift_indices({0: "a", 2: "c"}, 1) == {0: "a", 1: "c"}


class TestRbCostumeRows:
    ENTRIES = [
        {"costume_id": 1, "label": "生徒A（通常）"},
        {"costume_id": 2, "label": "生徒A（水着）"},
    ]

    def test_empty_returns_message(self):
        rows = _rb_costume_rows([])
        assert getattr(rows, "children", None) == "生徒（衣装）を追加してください。"

    def test_row_count(self):
        rows = _rb_costume_rows(self.ENTRIES)
        assert len(rows) == 2

    def test_defaults(self):
        rows = _rb_costume_rows(self.ENTRIES)
        inputs = {
            (c.id["type"], c.id["index"]): c
            for row in rows
            for c in row.children
            if isinstance(getattr(c, "id", None), dict)
        }
        assert inputs[("rb-bond-rank", 0)].value == 20
        assert inputs[("rb-bond-target", 0)].value == 50
        assert inputs[("rb-bond-remain", 0)].value is None

    def test_value_carryover(self):
        rows = _rb_costume_rows(
            self.ENTRIES, ranks={1: 33}, remains={1: 100}, targets={1: 40}
        )
        inputs = {
            (c.id["type"], c.id["index"]): c
            for row in rows
            for c in row.children
            if isinstance(getattr(c, "id", None), dict)
        }
        assert inputs[("rb-bond-rank", 1)].value == 33
        assert inputs[("rb-bond-remain", 1)].value == 100
        assert inputs[("rb-bond-target", 1)].value == 40
