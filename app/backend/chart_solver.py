"""チャート計算ロジック。"""

import functools

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


def _build_bonus_table(all_bond_bonuses: list[list[int]]):
    """全衣装・全状態でのボーナス合計テーブルを構築する (テスト用)。"""
    import numpy as np

    num_costumes = len(all_bond_bonuses)
    cum_per_costume = [_cumulative_bonus(bb) for bb in all_bond_bonuses]
    total = np.zeros((51,) * num_costumes, dtype=np.int64)
    for i, cum in enumerate(cum_per_costume):
        shape = [1] * num_costumes
        shape[i] = 51
        total += np.array(cum, dtype=np.int64).reshape(shape)
    return total


def solve_dp(current_ranks: list[int], all_bond_bonuses: list[list[int]]):
    """動的計画法でチャートを計算する (テスト用)。"""
    import itertools
    import numpy as np

    num_costumes = len(current_ranks)
    shape = (51,) * num_costumes
    dp = np.full(shape, np.iinfo(np.int64).min, dtype=np.int64)
    dp[tuple(current_ranks)] = 0

    bonus_table = _build_bonus_table(all_bond_bonuses)

    ranges = [range(r, 51) for r in current_ranks]
    for state in itertools.product(*ranges):
        val = dp[state]
        if val == np.iinfo(np.int64).min:
            continue
        bonus = bonus_table[state]
        for i in range(num_costumes):
            if state[i] >= 50:
                continue
            exp = BOND_EXP_PER_LEVEL[state[i] - 1]
            new_val = val + exp * bonus
            next_state = list(state)
            next_state[i] += 1
            next_state = tuple(next_state)
            if new_val > dp[next_state]:
                dp[next_state] = new_val

    return dp


def solve(
    current_ranks: list[int],
    all_bond_bonuses: list[list[int]],
    *,
    costume_priority: list[int] | None = None,
    bond50_penalty: float = 0,
):
    """Sidney 分解でチャートを計算する。

    問題を 1|chains|max Σw_jC_j に帰着し、Sidney 分解により
    O(T log T) で厳密な最適解を求める（T = 総ステップ数）。

    Parameters
    ----------
    costume_priority : list[int] | None
        衣装インデックスの優先順リスト（タイブレーク用）
    bond50_penalty : int
        絆50到達時のペナルティ値

    Returns
    -------
    path : list[tuple[int, ...]]
        初期状態から最終状態 (50, ..., 50) までの経路
    total_score : int
        最適スコア
    """
    num_costumes = len(current_ranks)
    cum_per_costume = [_cumulative_bonus(bb) for bb in all_bond_bonuses]

    # 衣装優先度マップ
    priority_map: dict[int, int] = {}
    if costume_priority:
        priority_map = {ci: pos for pos, ci in enumerate(costume_priority)}

    # 絆50ペナルティ: 全衣装の絆50ボーナスの最大値から減算量を決定
    penalty50 = 0
    if bond50_penalty > 0:
        max_p50 = max(
            cum_per_costume[i][50] - cum_per_costume[i][49] for i in range(num_costumes)
        )
        penalty50 = round(max_p50 * bond50_penalty)

    # 各衣装のジョブチェーンを構築
    # ジョブ: (w=exp, p=δ, costume_idx, rank)
    chains: list[list[tuple[int, int, int, int]]] = []
    for i in range(num_costumes):
        chain = []
        for r in range(current_ranks[i], 50):
            w = BOND_EXP_PER_LEVEL[r - 1]
            p = cum_per_costume[i][r + 1] - cum_per_costume[i][r]
            # 絆50ペナルティ: ランク49→50のジョブに一律減算（負にならない）
            if r == 49 and penalty50 > 0:
                p = max(0, p - penalty50)
            chain.append((w, p, i, r))
        chains.append(chain)

    # Sidney 分解: 各チェーン内で p/w 比が非増加になるようブロックをマージ
    # max Σw_jC_j では高 p/w ブロックを先にスケジュールする
    all_blocks: list[tuple[int, int, list[tuple[int, int, int, int]]]] = []

    for chain in chains:
        stack: list[tuple[int, int, list]] = []  # (total_p, total_w, jobs)
        for job in chain:
            w, p, ci, r = job
            new_block: tuple[int, int, list] = (p, w, [job])
            while stack:
                top_p, top_w, top_jobs = stack[-1]
                new_p, new_w = new_block[0], new_block[1]
                # top の p/w <= new の p/w ならマージ (等価も含めて同衣装を連続させる)
                if top_p * new_w <= new_p * top_w:
                    stack.pop()
                    new_block = (top_p + new_p, top_w + new_w, top_jobs + new_block[2])
                else:
                    break
            stack.append(new_block)
        all_blocks.extend(stack)

    # ブロックを p/w 比の降順でソート (整数比較)
    def cmp_blocks(a, b):
        lhs = a[0] * b[1]  # a.p * b.w
        rhs = b[0] * a[1]  # b.p * a.w
        if lhs > rhs:
            return -1
        if lhs < rhs:
            return 1
        # タイブレーク: 衣装優先度順
        if priority_map:
            a_pri = priority_map.get(a[2][0][2], len(priority_map))
            b_pri = priority_map.get(b[2][0][2], len(priority_map))
            if a_pri != b_pri:
                return -1 if a_pri < b_pri else 1
        return 0

    all_blocks.sort(key=functools.cmp_to_key(cmp_blocks))

    # スケジュールに従って経路とスコアを構築
    state = list(current_ranks)
    path: list[tuple[int, ...]] = [tuple(state)]
    total_score = 0
    current_bonus = sum(cum_per_costume[i][state[i]] for i in range(num_costumes))

    for _block_p, _block_w, jobs in all_blocks:
        for _w, _p, ci, r in jobs:
            exp = BOND_EXP_PER_LEVEL[r - 1]
            # スコア計算には実際のボーナス値を使用（ペナルティの影響を受けない）
            delta = cum_per_costume[ci][r + 1] - cum_per_costume[ci][r]
            total_score += exp * current_bonus
            state[ci] = r + 1
            current_bonus += delta
            path.append(tuple(state))

    return path, total_score


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
            pattern = changes[i : i + pat_len]
            # このパターンが何回繰り返されるか
            j = i + pat_len
            while j + pat_len <= len(changes) and changes[j : j + pat_len] == pattern:
                j += pat_len
            # 末尾の不完全な繰り返しも含める
            remaining = changes[j : j + pat_len]
            if remaining == pattern[: len(remaining)] and len(remaining) > 0:
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
        if (
            merged
            and len(g[0]) == 1
            and len(merged[-1][0]) == 1
            and g[0] == merged[-1][0]
        ):
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
                        parts.append(
                            f"{costume_names[c]} {from_state[c]} → {to_state[c]}"
                        )
            desc = f"[{rotating}] {count_str} " + ", ".join(parts)

        summary.append({"description": desc, "from": from_state, "to": to_state})

    return summary
