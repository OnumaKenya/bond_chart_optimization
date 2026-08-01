"""gift_solver のテスト。

exp_to_reach_rank / bonus_gain / solve_required_boxes を検証する。
"""

import pytest

from app.backend.gift_solver import (
    exp_to_reach_rank,
    bonus_gain,
    boxes_to_reach_rank,
    solve_required_boxes,
)


# ---------------------------------------------------------------------------
# exp_to_reach_rank
# ---------------------------------------------------------------------------


class TestExpToReachRank:
    def test_one_rank(self):
        # 1 -> 2 は 15
        assert exp_to_reach_rank(1, 2) == 15

    def test_two_ranks(self):
        # 1 -> 3 は 15 + 30
        assert exp_to_reach_rank(1, 3) == 45

    def test_target_not_above_current(self):
        assert exp_to_reach_rank(10, 10) == 0
        assert exp_to_reach_rank(10, 5) == 0

    def test_remaining_exp_overrides_first_rankup(self):
        # 最初の 1 -> 2 のみ残りEXPで置き換え
        assert exp_to_reach_rank(1, 2, remaining_exp=5) == 5
        assert exp_to_reach_rank(1, 3, remaining_exp=5) == 35

    def test_remaining_exp_clamped_to_full(self):
        # 満額超えは満額にクランプ
        assert exp_to_reach_rank(1, 2, remaining_exp=999) == 15

    def test_remaining_exp_zero_or_none_is_full(self):
        assert exp_to_reach_rank(1, 2, remaining_exp=0) == 15
        assert exp_to_reach_rank(1, 2, remaining_exp=None) == 15

    def test_target_capped_at_50(self):
        assert exp_to_reach_rank(49, 60) == exp_to_reach_rank(49, 50)


# ---------------------------------------------------------------------------
# boxes_to_reach_rank
# ---------------------------------------------------------------------------


class TestBoxesToReachRank:
    def test_exact_division(self):
        # 1 -> 2 は 15 EXP。box_exp=15 なら 1 個
        assert boxes_to_reach_rank(1, 2, 15) == 1

    def test_ceil(self):
        # 15 EXP を 20/box で 1 個、10/box で 2 個
        assert boxes_to_reach_rank(1, 2, 20) == 1
        assert boxes_to_reach_rank(1, 2, 10) == 2

    def test_multi_rank(self):
        # 1 -> 3 は 45 EXP。20/box -> 3 個
        assert boxes_to_reach_rank(1, 3, 20) == 3

    def test_target_not_above_current(self):
        assert boxes_to_reach_rank(10, 10, 20) == 0
        assert boxes_to_reach_rank(10, 5, 20) == 0

    def test_zero_box_exp(self):
        assert boxes_to_reach_rank(1, 50, 0) == 0

    def test_remaining_exp(self):
        # 最初のランクアップのみ残りEXPで置き換え（1->2 が 5 EXP になる）
        assert boxes_to_reach_rank(1, 2, 20, remaining_exp=5) == 1
        assert boxes_to_reach_rank(1, 3, 20, remaining_exp=5) == 2  # 5+30=35

    def test_full_1_to_50(self):
        # 絆1->50 の総EXPを 80/box で切り上げ
        total = exp_to_reach_rank(1, 50)
        assert boxes_to_reach_rank(1, 50, 80) == -(-total // 80)


# ---------------------------------------------------------------------------
# bonus_gain
# ---------------------------------------------------------------------------


class TestBonusGain:
    BONUSES = [1, 2, 3, 4, 5, 6, 7]  # BOND_RANGES 対応

    def test_within_first_range(self):
        # 絆2..5 は区間1（+1）
        assert bonus_gain(self.BONUSES, 1, 5) == 4

    def test_cross_range(self):
        # 絆6 は区間2（+2）
        assert bonus_gain(self.BONUSES, 5, 6) == 2

    def test_no_gain(self):
        assert bonus_gain(self.BONUSES, 10, 10) == 0
        assert bonus_gain(self.BONUSES, 10, 8) == 0

    def test_last_rank(self):
        assert bonus_gain(self.BONUSES, 49, 50) == 7


# ---------------------------------------------------------------------------
# solve_required_boxes
# ---------------------------------------------------------------------------

BONUS_FIRST = [1, 0, 0, 0, 0, 0, 0]  # 区間1（絆2~5）のみ +1


def _solve(current_ranks, bond_bonuses, box_values, *, gifts=None, **kwargs):
    """gifts: (qty, value行) のリスト。省略時は所持贈り物なし。"""
    gifts = gifts or []
    gift_qty = [q for q, _ in gifts]
    value = [v for _, v in gifts]
    return solve_required_boxes(
        current_ranks, bond_bonuses, gift_qty, value, box_values, **kwargs
    )


class TestSolveRequiredBoxesGainTarget:
    """target_gain（ステータス上昇量）指定。"""

    def test_zero_target_needs_no_boxes(self):
        result = _solve([1], [BONUS_FIRST], [20], target_gain=0)
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 0
        assert result["final_ranks"] == [1]

    def test_no_gifts_single_rankup(self):
        # 1 -> 2 に 15 EXP、ボックス 20 EXP -> 1個
        result = _solve([1], [BONUS_FIRST], [20], target_gain=1)
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 1

    def test_no_gifts_full_first_range(self):
        # 1 -> 5 に 15+30+30+35 = 110 EXP -> ceil(110/20) = 6個
        result = _solve([1], [BONUS_FIRST], [20], target_gain=4)
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 6
        assert result["total_gain"] == 4
        assert result["final_ranks"] == [5]

    def test_owned_gifts_reduce_boxes(self):
        # 所持 20 EXP ×3 で 60 EXP 分を賄い、残り 50 EXP -> ボックス3個
        result = _solve([1], [BONUS_FIRST], [20], gifts=[(3, [20])], target_gain=4)
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 3
        assert sum(result["allocation"][0]) == 3

    def test_owned_gifts_sufficient_means_zero_boxes(self):
        result = _solve([1], [BONUS_FIRST], [20], gifts=[(10, [20])], target_gain=1)
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 0
        # 同点時は所持贈り物の使用も最少（15 EXP に 1個で足りる）
        assert sum(result["allocation"][0]) == 1

    def test_remaining_exp_reduces_boxes(self):
        # 残り 5 EXP なら ボックス 20 EXP 1個で 1 -> 2
        result = _solve([1], [BONUS_FIRST], [20], target_gain=1, remaining_exp=[5])
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 1

    def test_unreachable_target_is_infeasible(self):
        # 区間1しかボーナスが無いので上限は +4
        result = _solve([1], [BONUS_FIRST], [20], target_gain=5)
        assert result["status"] == "infeasible"
        assert result["total_boxes"] == 0

    @pytest.mark.parametrize("box_value", [0, -10])
    def test_nonpositive_box_value_is_infeasible(self, box_value):
        result = _solve([1], [BONUS_FIRST], [box_value], target_gain=1)
        assert result["status"] == "infeasible"


class TestSolveRequiredBoxesRankTarget:
    """target_ranks（衣装ごとの目標絆ランク）指定。"""

    def test_no_target_needs_no_boxes(self):
        result = _solve([1], [BONUS_FIRST], [20], target_ranks=[None])
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 0

    def test_target_not_above_current_needs_no_boxes(self):
        result = _solve([10], [BONUS_FIRST], [20], target_ranks=[10])
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 0

    def test_no_gifts_rank_target(self):
        # 1 -> 5 に 110 EXP -> 6個
        result = _solve([1], [BONUS_FIRST], [20], target_ranks=[5])
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 6
        assert result["final_ranks"][0] >= 5

    def test_owned_gifts_reduce_boxes(self):
        # 110 EXP のうち 40 EXP を所持 20 EXP ×2 で賄う -> ceil(70/20) = 4個
        result = _solve([1], [BONUS_FIRST], [20], gifts=[(2, [20])], target_ranks=[5])
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 4
        assert sum(result["allocation"][0]) == 2

    def test_shared_gift_goes_to_one_costume(self):
        # 両衣装とも 1 -> 2 (15 EXP)。所持 15 EXP ×1 は片方にしか使えず、
        # もう片方はボックス1個で埋める。
        result = _solve(
            [1, 1],
            [BONUS_FIRST, BONUS_FIRST],
            [20, 20],
            gifts=[(1, [15, 15])],
            target_ranks=[2, 2],
        )
        assert result["status"] == "optimal"
        assert result["total_boxes"] == 1
        assert sum(result["allocation"][0]) == 1

    def test_untargeted_costume_gets_nothing(self):
        # 目標のない衣装2には贈り物もボックスも配らない
        result = _solve(
            [1, 1],
            [BONUS_FIRST, BONUS_FIRST],
            [20, 20],
            gifts=[(10, [20, 20])],
            target_ranks=[2, None],
        )
        assert result["status"] == "optimal"
        assert result["boxes"][1] == 0
        assert result["allocation"][0][1] == 0

    def test_combined_with_gain_target(self):
        # ランク目標（衣装1: 絆2）に加えて合計 +2 -> 衣装のどれかで追加1ランク
        result = _solve(
            [1, 1],
            [BONUS_FIRST, BONUS_FIRST],
            [20, 20],
            target_ranks=[2, None],
            target_gain=2,
        )
        assert result["status"] == "optimal"
        assert result["total_gain"] >= 2
        assert result["final_ranks"][0] >= 2
