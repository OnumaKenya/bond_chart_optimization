"""贈り物配分の最適化（MILP / SCIP）。

各衣装の現在絆ランクから、使用可能な贈り物を配分して
全衣装の絆ボーナス上昇量の合計を最大化する。

定式化:
  x[g][c] >= 0 整数      … 贈り物 g を衣装 c に配る個数
  delta[c][r] in {0,1}   … 衣装 c が r-1 -> r のランクアップを達成
  s.t.
    sum_c x[g][c] <= qty[g]                          (所持数)
    delta[c][r] <= delta[c][r-1]                     (連続性)
    sum_r e(r) delta[c][r] <= sum_g v[g][c] x[g][c]  (消費EXP <= 獲得EXP)
  max sum_c sum_r b_c(r) delta[c][r]
"""

from app.backend.bond_exp import BOND_EXP_PER_LEVEL
from app.backend.student import BOND_RANGES

_MAX_RANK = 50

# SCIP の制限時間（秒）。実データ規模では数ミリ秒で解けるが、
# 想定外の重い入力で UI が固まらないための保険。
# 到達時は status="timelimit" で暫定（最良実行可能）解を返す。
DEFAULT_TIME_LIMIT = 15.0


def _range_bonus(bond_bonuses: list[int], rank: int) -> int:
    """rank（2..50）が属する区間の絆ボーナス。"""
    for idx, (lo, hi) in enumerate(BOND_RANGES):
        if lo <= rank <= hi:
            return bond_bonuses[idx]
    return 0


def _level_exp(rank: int) -> int:
    """(rank-1) -> rank に必要な EXP。rank は 2..50。"""
    return BOND_EXP_PER_LEVEL[rank - 2]


def solve_gift_distribution(
    current_ranks: list[int],
    bond_bonuses: list[list[int]],
    gift_qty: list[int],
    value: list[list[int]],
    time_limit: float = DEFAULT_TIME_LIMIT,
    remaining_exp: list[int | None] | None = None,
) -> dict:
    """贈り物配分 MILP を解く。

    Parameters
    ----------
    current_ranks : list[int]
        衣装ごとの現在絆ランク (1..50)。
    bond_bonuses : list[list[int]]
        衣装ごとの絆ボーナス（各 7 要素、BOND_RANGES 対応）。
    gift_qty : list[int]
        贈り物ごとの所持数。
    value : list[list[int]]
        value[g][c] = 贈り物 g を衣装 c に 1 個使ったときの獲得EXP。
    time_limit : float
        SCIP の制限時間（秒）。
    remaining_exp : list[int | None] | None
        衣装ごとの「次の絆上昇までの残り経験値」。指定された衣装は
        最初のランクアップ (r0 -> r0+1) の必要EXPをこの値で上書きする
        （途中まで経験値が貯まっているケース）。None / 該当要素が
        None・0以下 の場合は通常どおりレベル満額を要求する。値は
        [1, 満額] にクランプする。

    Returns
    -------
    dict
        {
          "allocation": list[list[int]]  # allocation[g][c]
          "final_ranks": list[int]
          "total_gain": int
          "status": str
        }
    """
    from pyscipopt import Model, quicksum

    n = len(current_ranks)
    m = len(gift_qty)

    model = Model("gift_distribution")
    model.hideOutput()
    model.setParam("limits/time", time_limit)

    # x[g][c]
    x = {}
    for g in range(m):
        ub = max(0, int(gift_qty[g]))
        for c in range(n):
            x[g, c] = model.addVar(vtype="I", lb=0, ub=ub, name=f"x_{g}_{c}")

    # delta[c][r] : r = current_rank+1 .. 50
    delta = {}
    for c in range(n):
        r0 = current_ranks[c]
        for r in range(r0 + 1, _MAX_RANK + 1):
            delta[c, r] = model.addVar(vtype="B", name=f"d_{c}_{r}")

    # 所持数
    for g in range(m):
        if n > 0:
            model.addCons(
                quicksum(x[g, c] for c in range(n)) <= max(0, int(gift_qty[g]))
            )

    for c in range(n):
        r0 = current_ranks[c]
        # 連続性: 上位ランクアップは下位を前提
        for r in range(r0 + 2, _MAX_RANK + 1):
            model.addCons(delta[c, r] <= delta[c, r - 1])
        # 各ランクアップの必要EXP。最初の r0 -> r0+1 のみ「次の絆上昇
        # までの残り経験値」で上書きできる（途中まで貯まっている場合）。
        rem = (
            remaining_exp[c]
            if remaining_exp is not None and c < len(remaining_exp)
            else None
        )
        cost = {}
        for r in range(r0 + 1, _MAX_RANK + 1):
            base = _level_exp(r)
            if r == r0 + 1 and rem is not None and int(rem) > 0:
                base = max(1, min(int(rem), base))
            cost[r] = base
        # 消費EXP <= 獲得EXP
        consumed = quicksum(cost[r] * delta[c, r] for r in range(r0 + 1, _MAX_RANK + 1))
        gained = quicksum(value[g][c] * x[g, c] for g in range(m))
        model.addCons(consumed <= gained)

    # 目的: 絆ボーナス上昇量の合計を最大化（主目的）。
    # 同点時は使用贈り物の総数を最小化（無駄な配分を避ける二次目的）。
    # W は「贈り物を1個節約するより絆ボーナス1点が常に優先」される十分大の重み。
    bonus_term = quicksum(
        _range_bonus(bond_bonuses[c], r) * delta[c, r]
        for c in range(n)
        for r in range(current_ranks[c] + 1, _MAX_RANK + 1)
    )
    used_term = quicksum(x[g, c] for g in range(m) for c in range(n))
    weight = sum(max(0, int(q)) for q in gift_qty) + 1
    model.setObjective(weight * bonus_term - used_term, "maximize")

    model.optimize()
    status = model.getStatus()

    allocation = [[0] * n for _ in range(m)]
    final_ranks = list(current_ranks)
    total_gain = 0

    if model.getNSols() > 0:
        sol = model.getBestSol()
        for g in range(m):
            for c in range(n):
                allocation[g][c] = int(round(model.getSolVal(sol, x[g, c])))
        for c in range(n):
            r0 = current_ranks[c]
            cnt = 0
            for r in range(r0 + 1, _MAX_RANK + 1):
                if model.getSolVal(sol, delta[c, r]) > 0.5:
                    cnt += 1
            final_ranks[c] = r0 + cnt
        # 目的値は重み付き式なので、絆ボーナス上昇量は実ランクから再計算
        total_gain = sum(
            _range_bonus(bond_bonuses[c], r)
            for c in range(n)
            for r in range(current_ranks[c] + 1, final_ranks[c] + 1)
        )

    return {
        "allocation": allocation,
        "final_ranks": final_ranks,
        "total_gain": total_gain,
        "status": status,
    }
