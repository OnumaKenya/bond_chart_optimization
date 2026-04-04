"""chart_solver のテスト。

Sidney 分解ソルバーの正しさを DP ソルバーとの比較で検証する。
"""

import pytest

from app.backend.bond_exp import BOND_EXP_PER_LEVEL
from app.backend.chart_solver import (
    _cumulative_bonus,
    solve,
    solve_dp,
    summarize_path,
)
from app.backend.presets import PRESETS


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _compute_score_from_path(path, all_bond_bonuses):
    """経路からスコアを再計算する。"""
    num = len(path[0])
    cum_per_costume = [_cumulative_bonus(bb) for bb in all_bond_bonuses]
    score = 0
    for i in range(1, len(path)):
        prev, cur = path[i - 1], path[i]
        for c in range(num):
            if cur[c] != prev[c]:
                exp = BOND_EXP_PER_LEVEL[prev[c] - 1]
                bonus = sum(cum_per_costume[j][prev[j]] for j in range(num))
                score += exp * bonus
                break
    return score


# ---------------------------------------------------------------------------
# テストケース定義
# ---------------------------------------------------------------------------

# (説明, current_ranks, all_bond_bonuses)
SMALL_CASES = [
    (
        "1衣装・全ランク1",
        [1],
        [[3, 5, 7, 9, 3, 4, 7]],
    ),
    (
        "1衣装・途中開始",
        [20],
        [[1, 2, 3, 4, 5, 6, 7]],
    ),
    (
        "2衣装・均一ボーナス",
        [1, 1],
        [[5, 5, 5, 5, 5, 5, 5], [5, 5, 5, 5, 5, 5, 5]],
    ),
    (
        "2衣装・非凸ボーナス",
        [1, 1],
        [[10, 1, 20, 1, 30, 1, 50], [1, 20, 1, 30, 1, 50, 1]],
    ),
    (
        "2衣装・途中開始",
        [30, 40],
        [[3, 5, 7, 9, 3, 4, 7], [7, 4, 3, 9, 7, 5, 3]],
    ),
    (
        "2衣装・片方ゼロボーナス",
        [40, 40],
        [[0, 0, 0, 0, 0, 0, 10], [0, 0, 0, 0, 0, 0, 5]],
    ),
    (
        "3衣装・途中開始",
        [40, 42, 45],
        [[3, 5, 7, 9, 3, 4, 7], [7, 4, 3, 9, 7, 5, 3], [1, 2, 3, 4, 5, 6, 7]],
    ),
    (
        "3衣装・全ランク1",
        [1, 1, 1],
        [[5, 0, 5, 0, 5, 0, 5], [0, 5, 0, 5, 0, 5, 0], [3, 3, 3, 3, 3, 3, 3]],
    ),
    (
        "2衣装・全ボーナスゼロ",
        [45, 45],
        [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
    ),
    (
        "2衣装・ランク49開始",
        [49, 49],
        [[3, 5, 7, 9, 3, 4, 7], [7, 4, 3, 9, 7, 5, 3]],
    ),
]


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

class TestSidneyVsDp:
    """Sidney ソルバーのスコアが DP の厳密解と一致することを検証する。"""

    @pytest.mark.parametrize(
        "desc, current_ranks, all_bond_bonuses",
        SMALL_CASES,
        ids=[c[0] for c in SMALL_CASES],
    )
    def test_score_matches_dp(self, desc, current_ranks, all_bond_bonuses):
        dp = solve_dp(current_ranks, all_bond_bonuses)
        goal = tuple([50] * len(current_ranks))
        dp_score = int(dp[goal])

        path, sidney_score = solve(current_ranks, all_bond_bonuses)

        assert sidney_score == dp_score, (
            f"{desc}: Sidney={sidney_score}, DP={dp_score}"
        )

    @pytest.mark.parametrize(
        "desc, current_ranks, all_bond_bonuses",
        SMALL_CASES,
        ids=[c[0] for c in SMALL_CASES],
    )
    def test_path_score_consistent(self, desc, current_ranks, all_bond_bonuses):
        """経路からスコアを再計算して返却スコアと一致することを確認。"""
        path, sidney_score = solve(current_ranks, all_bond_bonuses)
        recomputed = _compute_score_from_path(path, all_bond_bonuses)
        assert recomputed == sidney_score

    @pytest.mark.parametrize(
        "desc, current_ranks, all_bond_bonuses",
        SMALL_CASES,
        ids=[c[0] for c in SMALL_CASES],
    )
    def test_path_valid(self, desc, current_ranks, all_bond_bonuses):
        """経路が有効（各ステップで1衣装が1ランク上昇）であることを確認。"""
        path, _ = solve(current_ranks, all_bond_bonuses)
        assert path[0] == tuple(current_ranks)
        assert path[-1] == tuple([50] * len(current_ranks))
        for i in range(1, len(path)):
            diffs = [path[i][c] - path[i - 1][c] for c in range(len(path[0]))]
            assert sum(diffs) == 1, f"step {i}: 複数衣装が同時変化"
            assert all(d >= 0 for d in diffs), f"step {i}: ランクが減少"


class TestSidneyEdgeCases:
    """Sidney ソルバーのエッジケース。"""

    def test_single_costume_at_50(self):
        """既にランク50の衣装のみ。"""
        path, score = solve([50], [[1, 2, 3, 4, 5, 6, 7]])
        assert path == [(50,)]
        assert score == 0

    def test_all_at_50(self):
        """全衣装がランク50。"""
        path, score = solve(
            [50, 50],
            [[1, 2, 3, 4, 5, 6, 7], [7, 6, 5, 4, 3, 2, 1]],
        )
        assert path == [(50, 50)]
        assert score == 0

    def test_single_step(self):
        """1ステップのみ。"""
        path, score = solve([49], [[1, 2, 3, 4, 5, 6, 7]])
        assert len(path) == 2
        assert path[0] == (49,)
        assert path[-1] == (50,)


class TestSidneyNonConvex:
    """非凸ボーナスでの Sidney ソルバーの正しさ。"""

    def test_non_convex_2_costumes_high_start(self):
        """高ランク開始で非凸ボーナスパターン。"""
        ranks = [35, 38]
        bonuses = [[0, 0, 0, 0, 0, 20, 1], [0, 0, 0, 0, 0, 1, 20]]
        dp = solve_dp(ranks, bonuses)
        dp_score = int(dp[(50, 50)])
        _, sidney_score = solve(ranks, bonuses)
        assert sidney_score == dp_score

    def test_non_convex_spike_pattern(self):
        """ボーナスが中間区間で跳ね上がるパターン。"""
        ranks = [40, 40]
        bonuses = [[0, 0, 0, 0, 0, 0, 100], [0, 0, 0, 0, 0, 100, 0]]
        dp = solve_dp(ranks, bonuses)
        dp_score = int(dp[(50, 50)])
        _, sidney_score = solve(ranks, bonuses)
        assert sidney_score == dp_score


class TestSummarizePath:
    """summarize_path が Sidney の出力を処理できることを確認。"""

    def test_sidney_path_summarizable(self):
        ranks = [45, 45]
        bonuses = [[3, 5, 7, 9, 3, 4, 7], [7, 4, 3, 9, 7, 5, 3]]
        path, _ = solve(ranks, bonuses)
        summary = summarize_path(path, ["衣装A", "衣装B"])
        assert len(summary) > 0
        assert summary[0]["from"] == path[0]
        assert summary[-1]["to"] == path[-1]


class TestCumulativeBonus:
    """_cumulative_bonus の基本テスト。"""

    def test_rank1_is_zero(self):
        cum = _cumulative_bonus([10, 20, 30, 40, 50, 60, 70])
        assert cum[1] == 0

    def test_monotonic(self):
        cum = _cumulative_bonus([5, 5, 5, 5, 5, 5, 5])
        for lv in range(2, 51):
            assert cum[lv] >= cum[lv - 1]

    def test_zero_bonuses(self):
        cum = _cumulative_bonus([0, 0, 0, 0, 0, 0, 0])
        assert all(c == 0 for c in cum)


# ---------------------------------------------------------------------------
# プリセットを使ったテスト
# ---------------------------------------------------------------------------

def _preset_params():
    """PRESETS から (名前, ranks, bonuses) のパラメータリストを生成する。"""
    params = []
    for name, students in PRESETS.items():
        bonuses = [s["bond_bonuses"] for s in students]
        n = len(students)
        ranks = [1] * n
        params.append((name, ranks, bonuses))
    return params


PRESET_CASES = _preset_params()


class TestPresets:
    """全プリセットで Sidney と DP のスコアが一致することを検証する。"""

    @pytest.mark.parametrize(
        "name, current_ranks, all_bond_bonuses",
        PRESET_CASES,
        ids=[c[0] for c in PRESET_CASES],
    )
    def test_score_matches_dp(self, name, current_ranks, all_bond_bonuses):
        dp = solve_dp(current_ranks, all_bond_bonuses)
        goal = tuple([50] * len(current_ranks))
        dp_score = int(dp[goal])

        path, sidney_score = solve(current_ranks, all_bond_bonuses)

        assert sidney_score == dp_score, (
            f"{name}: Sidney={sidney_score}, DP={dp_score}"
        )

    @pytest.mark.parametrize(
        "name, current_ranks, all_bond_bonuses",
        PRESET_CASES,
        ids=[c[0] for c in PRESET_CASES],
    )
    def test_path_valid(self, name, current_ranks, all_bond_bonuses):
        path, _ = solve(current_ranks, all_bond_bonuses)
        assert path[0] == tuple(current_ranks)
        assert path[-1] == tuple([50] * len(current_ranks))
        for i in range(1, len(path)):
            diffs = [path[i][c] - path[i - 1][c] for c in range(len(path[0]))]
            assert sum(diffs) == 1
            assert all(d >= 0 for d in diffs)
