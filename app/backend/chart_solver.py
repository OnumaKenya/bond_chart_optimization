"""チャート計算ロジック。"""

import numpy as np

from app.backend.bond_exp import BOND_EXP_PER_LEVEL
from app.backend.student import BOND_RANGES


def _cumulative_bonus(bond_bonuses: list[int]) -> list[int]:
    """絆ランク 1~50 それぞれでの累積ボーナスを返す (長さ 51、index 0 は未使用)。

    cumulative[lv] = 絆ランク lv 時点での累積ボーナス合計。
    ランク 1 はボーナスなし (0)。ランク 2 以降、そのランクに到達した分だけ加算。
    """
    cum = [0] * 51  # cum[0] は未使用、cum[1] = 0
    for lv in range(2, 51):
        # lv が属する区間のボーナスを加算
        bonus = 0
        for idx, (lo, hi) in enumerate(BOND_RANGES):
            if lo <= lv <= hi:
                bonus = bond_bonuses[idx]
                break
        cum[lv] = cum[lv - 1] + bonus
    return cum


def _build_bonus_table(all_bond_bonuses: list[list[int]]) -> np.ndarray:
    """全衣装・全状態でのボーナス合計テーブルを構築する。

    Parameters
    ----------
    all_bond_bonuses : list[list[int]]
        各衣装の bond_bonuses (長さ 7)

    Returns
    -------
    np.ndarray
        shape = (51,) * num_costumes, dtype=int64
        各要素は全衣装の累積ボーナス合計
    """
    num_costumes = len(all_bond_bonuses)
    # 各衣装の累積ボーナス (shape: (num_costumes, 51))
    cum_per_costume = [_cumulative_bonus(bb) for bb in all_bond_bonuses]

    # 各衣装の累積ボーナスを適切な軸に展開して合算
    total = np.zeros((51,) * num_costumes, dtype=np.int64)
    for i, cum in enumerate(cum_per_costume):
        shape = [1] * num_costumes
        shape[i] = 51
        total += np.array(cum, dtype=np.int64).reshape(shape)
    return total


def solve_dp(current_ranks: list[int], all_bond_bonuses: list[list[int]]):
    """動的計画法でチャートを計算する。

    Parameters
    ----------
    current_ranks : list[int]
        各衣装の現在の絆ランク (1~50)
    all_bond_bonuses : list[list[int]]
        各衣装の bond_bonuses (長さ 7)

    Returns
    -------
    dp : np.ndarray
        shape = (51,) * num_costumes, dtype=int64
    dp_pre : np.ndarray
        shape = (51,) * num_costumes, dtype=object
        各要素は遷移元のインデックスタプル（または None）
    """
    num_costumes = len(current_ranks)
    shape = (51,) * num_costumes
    dp = np.full(shape, np.iinfo(np.int64).min, dtype=np.int64)
    dp_pre = np.empty(shape, dtype=object)
    # 同点時タイブレーク用: どの衣装を上げてこの状態に来たか
    dp_moved = np.full(shape, -1, dtype=np.int8)

    # 初期状態
    initial = tuple(current_ranks)
    dp[initial] = 0

    # ボーナス合計テーブル
    bonus_table = _build_bonus_table(all_bond_bonuses)

    def _is_better_tie(state, next_state, moved_costume, new_val):
        """同点時に遷移を更新すべきか判定する。

        優先度:
        1. 同じ衣装を続ける（連続優先）
        2. 現在ランクが低い衣装を優先（バランス優先）
        3. 衣装番号が若い順（固定順序）
        """
        old_moved = dp_moved[next_state]
        if old_moved < 0:
            return True

        # 遷移元でどの衣装を上げたか
        prev_moved = dp_moved[state]

        # 1. 連続優先: 遷移元と同じ衣装を上げるほうを優先
        new_continues = (moved_costume == prev_moved)
        old_continues = (old_moved == prev_moved)
        if new_continues != old_continues:
            return new_continues

        # 2. バランス優先: ランクが低い衣装を優先
        new_rank = state[moved_costume]  # 上げる前のランク
        old_src = dp_pre[next_state]
        old_rank = old_src[old_moved] if old_src is not None else 50
        if new_rank != old_rank:
            return new_rank < old_rank

        # 3. 固定順序: 衣装番号が若い方を優先
        return moved_costume < old_moved

    # 全状態を列挙して遷移
    import itertools
    ranges = [range(r, 51) for r in current_ranks]
    for state in itertools.product(*ranges):
        val = dp[state]
        if val == np.iinfo(np.int64).min:
            continue
        bonus = bonus_table[state]
        # 各衣装のランクを1つ上げる遷移
        for i in range(num_costumes):
            if state[i] >= 50:
                continue
            exp = BOND_EXP_PER_LEVEL[state[i] - 1]
            new_val = val + exp * bonus
            next_state = list(state)
            next_state[i] += 1
            next_state = tuple(next_state)
            if new_val > dp[next_state] or (
                new_val == dp[next_state] and _is_better_tie(state, next_state, i, new_val)
            ):
                dp[next_state] = new_val
                dp_pre[next_state] = state
                dp_moved[next_state] = i

    return dp, dp_pre


def solve_beam(current_ranks: list[int], all_bond_bonuses: list[list[int]]):
    """ビームサーチ（経験値効率ソート）でチャートを計算する。

    各深さごとにビーム幅の上位状態を全展開し、
    score / total_exp（経験値効率）でソートして次の深さに進む。
    厳密解は保証しないが、衣装数が多い場合でも実用的な解を返す。

    Returns
    -------
    best_score : dict[tuple, int]
        各状態の最高スコア
    pre : dict[tuple, tuple]
        各状態の遷移元
    """
    num_costumes = len(current_ranks)
    # 衣装数に応じてビーム幅を自動調整 (計算量 ∝ width * n^2 を一定に保つ)
    beam_width = min(10000, 160000 // (num_costumes * num_costumes))
    cum_per_costume = [_cumulative_bonus(bb) for bb in all_bond_bonuses]

    total_steps = sum(50 - r for r in current_ranks)

    initial = tuple(current_ranks)
    best_score: dict[tuple, int] = {initial: 0}
    pre: dict[tuple, tuple] = {}

    # current_beam: list of (score, total_exp, state)
    current_beam = [(0, 0, initial)]

    for _depth in range(total_steps):
        # 候補生成: next_state -> (score, total_exp, prev_state)
        candidates: dict[tuple, tuple[int, int, tuple]] = {}

        for score, total_exp, state in current_beam:
            if score < best_score.get(state, 0):
                continue

            bonus = sum(cum_per_costume[i][state[i]] for i in range(num_costumes))

            for i in range(num_costumes):
                if state[i] >= 50:
                    continue

                exp = BOND_EXP_PER_LEVEL[state[i] - 1]
                new_score = score + exp * bonus
                new_total_exp = total_exp + exp

                next_state = list(state)
                next_state[i] += 1
                next_state = tuple(next_state)

                existing = candidates.get(next_state)
                if existing is None or new_score > existing[0]:
                    candidates[next_state] = (new_score, new_total_exp, state)

        # efficiency 降順でソートし上位 beam_width 個を保持
        sorted_cands = sorted(
            candidates.items(),
            key=lambda x: x[1][0] / x[1][1] if x[1][1] > 0 else 0,
            reverse=True,
        )[:beam_width]

        current_beam = []
        for ns, (sc, te, prev) in sorted_cands:
            old = best_score.get(ns)
            if old is None or sc > old:
                best_score[ns] = sc
                pre[ns] = prev
            current_beam.append((sc, te, ns))

    return best_score, pre


_SOLVERS = {
    "dp": solve_dp,
    "chokudai": solve_beam,
}


def solve(current_ranks: list[int], all_bond_bonuses: list[list[int]], *, solver_type: str = "dp"):
    """ソルバーを選択してチャートを計算する。"""
    solver = _SOLVERS.get(solver_type)
    if solver is None:
        raise ValueError(f"未知のソルバー: {solver_type}")
    return solver(current_ranks, all_bond_bonuses)


def summarize_path(path: list[tuple[int, ...]], costume_names: list[str]) -> list[dict]:
    """経路を要約する。

    連続して同じ衣装を上げる区間、および交互・ローテーションのパターンを検出してまとめる。

    Returns
    -------
    list[dict]
        各要素は {"description": str, "from": tuple, "to": tuple}
    """
    if len(path) <= 1:
        return []

    # 各ステップでどの衣装が変わったかを記録
    changes = []
    for i in range(1, len(path)):
        for c in range(len(path[0])):
            if path[i][c] != path[i - 1][c]:
                changes.append(c)
                break

    # 連続・ローテーションパターンを検出してグループ化
    groups: list[tuple[list[int], int, int]] = []  # (pattern, start_idx, end_idx)
    i = 0
    while i < len(changes):
        # 長さ 1~3 のパターンでローテーション検出を試みる
        best_pattern = [changes[i]]
        best_end = i + 1

        for pat_len in range(1, min(4, len(changes) - i + 1)):
            pattern = changes[i:i + pat_len]
            # このパターンが何回繰り返されるか
            j = i + pat_len
            while j + pat_len <= len(changes) and changes[j:j + pat_len] == pattern:
                j += pat_len
            # 末尾の不完全な繰り返しも含める
            remaining = changes[j:j + pat_len]
            if remaining == pattern[:len(remaining)] and len(remaining) > 0:
                j += len(remaining)
            total = j - i
            if total > best_end - i:
                best_pattern = pattern
                best_end = j

        # パターン長 > 1 で1ループしかしない場合は個別行にする
        if len(best_pattern) > 1 and best_end - i <= len(best_pattern):
            for k in range(i, best_end):
                # 直前のグループが同じ衣装の単一パターンならマージ
                if groups and groups[-1][0] == [changes[k]]:
                    prev = groups[-1]
                    groups[-1] = (prev[0], prev[1], k + 1)
                else:
                    groups.append(([changes[k]], k, k + 1))
        else:
            groups.append((best_pattern, i, best_end))
        i = best_end

    # 隣接する同一衣装の単一パターンをマージ
    merged: list[tuple[list[int], int, int]] = []
    for g in groups:
        if merged and len(g[0]) == 1 and len(merged[-1][0]) == 1 and g[0] == merged[-1][0]:
            prev = merged[-1]
            merged[-1] = (prev[0], prev[1], g[2])
        else:
            merged.append(g)
    groups = merged

    # グループから要約行を生成
    summary = []
    for pattern, start, end in groups:
        from_state = path[start]
        to_state = path[end]

        if len(pattern) == 1:
            c = pattern[0]
            name = costume_names[c]
            if to_state[c] - from_state[c] == 1:
                desc = f"{name}: {to_state[c]}"
            else:
                desc = f"{name}: {from_state[c]} → {to_state[c]}"
        else:
            names = [costume_names[c] for c in pattern]
            rotating = "→".join(names)
            total_steps = end - start
            full_repeats = total_steps // len(pattern)
            remainder = total_steps % len(pattern)
            if remainder == 0:
                count_str = f"x {full_repeats}"
            else:
                count_str = f"x {full_repeats}+{remainder}"
            parts = []
            for c in dict.fromkeys(pattern):
                if from_state[c] != to_state[c]:
                    if to_state[c] - from_state[c] == 1:
                        parts.append(f"{costume_names[c]} {to_state[c]}")
                    else:
                        parts.append(f"{costume_names[c]} {from_state[c]} → {to_state[c]}")
            desc = f"[{rotating}] {count_str} " + ", ".join(parts)

        summary.append({"description": desc, "from": from_state, "to": to_state})

    return summary
