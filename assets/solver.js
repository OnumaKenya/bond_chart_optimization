/**
 * クライアントサイド DP ソルバー
 *
 * Python の chart_solver.py を JavaScript に移植したもの。
 * Dash の clientside_callback として登録される。
 */

/* ------------------------------------------------------------------ */
/*  定数                                                               */
/* ------------------------------------------------------------------ */

var _solver_BOND_EXP_PER_LEVEL = [
    15, 30, 30, 35, 35, 35, 40, 40, 40,
    60, 90, 105, 120, 140, 160, 180, 205, 230, 255,
    285, 315, 345, 375, 410, 445, 480, 520, 560, 600,
    645, 690, 735, 780, 830, 880, 930, 985, 1040, 1095,
    1155, 1215, 1275, 1335, 1400, 1465, 1530, 1600, 1670, 1740,
];

var _solver_BOND_RANGES = [
    [2, 5], [6, 10], [11, 15], [16, 20],
    [21, 30], [31, 40], [41, 50],
];

/* ------------------------------------------------------------------ */
/*  ユーティリティ                                                      */
/* ------------------------------------------------------------------ */

function _solver_arraysEqual(a, b) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

function _solver_defaultCostumeName(index) {
    return "\u8863\u88c5" + (index + 1);
}

/* ------------------------------------------------------------------ */
/*  累積ボーナス                                                        */
/* ------------------------------------------------------------------ */

function _solver_cumulativeBonus(bondBonuses) {
    var cum = new Array(51);
    cum[0] = 0;
    cum[1] = 0;
    for (var lv = 2; lv <= 50; lv++) {
        var bonus = 0;
        for (var idx = 0; idx < _solver_BOND_RANGES.length; idx++) {
            if (lv >= _solver_BOND_RANGES[idx][0] && lv <= _solver_BOND_RANGES[idx][1]) {
                bonus = bondBonuses[idx];
                break;
            }
        }
        cum[lv] = cum[lv - 1] + bonus;
    }
    return cum;
}

function _solver_getBonus(state, cumPerCostume) {
    var total = 0;
    for (var i = 0; i < state.length; i++) {
        total += cumPerCostume[i][state[i]];
    }
    return total;
}

/* ------------------------------------------------------------------ */
/*  DP ソルバー                                                        */
/* ------------------------------------------------------------------ */

function _solver_isBetterTie(stateKey, nextKey, movedCostume, state, dpMoved, dpPre) {
    var oldMoved = dpMoved.get(nextKey);
    if (oldMoved === undefined || oldMoved < 0) return true;

    var prevMoved = dpMoved.get(stateKey);

    // 1. 連続優先
    var newContinues = (movedCostume === prevMoved);
    var oldContinues = (oldMoved === prevMoved);
    if (newContinues !== oldContinues) return newContinues;

    // 2. バランス優先
    var newRank = state[movedCostume];
    var oldSrcKey = dpPre.get(nextKey);
    var oldRank = 50;
    if (oldSrcKey !== undefined) {
        var parts = oldSrcKey.split(",");
        oldRank = parseInt(parts[oldMoved], 10);
    }
    if (newRank !== oldRank) return newRank < oldRank;

    // 3. 固定順序
    return movedCostume < oldMoved;
}

function _solver_solve(currentRanks, allBondBonuses) {
    var n = currentRanks.length;
    var cumPerCostume = allBondBonuses.map(function (bb) {
        return _solver_cumulativeBonus(bb);
    });

    var dp = new Map();
    var dpPre = new Map();
    var dpMoved = new Map();

    var initialKey = currentRanks.join(",");
    dp.set(initialKey, 0);

    // 全状態を辞書順に列挙 (itertools.product 相当)
    var state = currentRanks.slice();

    while (true) {
        var key = state.join(",");
        var val = dp.get(key);

        if (val !== undefined) {
            var bonus = _solver_getBonus(state, cumPerCostume);

            for (var i = 0; i < n; i++) {
                if (state[i] >= 50) continue;

                var exp = _solver_BOND_EXP_PER_LEVEL[state[i] - 1];
                var newVal = val + exp * bonus;

                state[i]++;
                var nextKey = state.join(",");
                state[i]--;

                var oldVal = dp.get(nextKey);
                if (
                    oldVal === undefined ||
                    newVal > oldVal ||
                    (newVal === oldVal &&
                        _solver_isBetterTie(key, nextKey, i, state, dpMoved, dpPre))
                ) {
                    dp.set(nextKey, newVal);
                    dpPre.set(nextKey, key);
                    dpMoved.set(nextKey, i);
                }
            }
        }

        // オドメーター式インクリメント
        var dim = n - 1;
        while (dim >= 0) {
            state[dim]++;
            if (state[dim] <= 50) break;
            state[dim] = currentRanks[dim];
            dim--;
        }
        if (dim < 0) break;
    }

    var _goalKey = new Array(n).fill(50).join(",");
    console.debug("[DP] goal score:", dp.get(_goalKey));

    return { dp: dp, dpPre: dpPre };
}

/* ------------------------------------------------------------------ */
/*  経路復元                                                           */
/* ------------------------------------------------------------------ */

function _solver_reconstructPath(dp, dpPre, numCostumes) {
    var goalKey = new Array(numCostumes).fill(50).join(",");
    if (!dp.has(goalKey)) return null;

    var path = [];
    var key = goalKey;
    while (key !== undefined) {
        path.push(key.split(",").map(Number));
        key = dpPre.get(key);
    }
    path.reverse();
    return path;
}

/* ------------------------------------------------------------------ */
/*  経路要約                                                           */
/* ------------------------------------------------------------------ */

function _solver_summarizePath(path, costumeNames) {
    if (path.length <= 1) return [];

    // 各ステップでどの衣装が変わったか
    var changes = [];
    for (var i = 1; i < path.length; i++) {
        for (var c = 0; c < path[0].length; c++) {
            if (path[i][c] !== path[i - 1][c]) {
                changes.push(c);
                break;
            }
        }
    }

    // パターン検出・グループ化
    var groups = [];
    var ci = 0;
    while (ci < changes.length) {
        var bestPattern = [changes[ci]];
        var bestEnd = ci + 1;

        for (
            var patLen = 1;
            patLen <= Math.min(3, changes.length - ci);
            patLen++
        ) {
            var pattern = changes.slice(ci, ci + patLen);
            var j = ci + patLen;
            while (
                j + patLen <= changes.length &&
                _solver_arraysEqual(changes.slice(j, j + patLen), pattern)
            ) {
                j += patLen;
            }
            var remaining = changes.slice(
                j,
                Math.min(j + patLen, changes.length)
            );
            if (
                remaining.length > 0 &&
                _solver_arraysEqual(remaining, pattern.slice(0, remaining.length))
            ) {
                j += remaining.length;
            }
            if (j - ci > bestEnd - ci) {
                bestPattern = pattern.slice();
                bestEnd = j;
            }
        }

        if (bestPattern.length > 1 && bestEnd - ci <= bestPattern.length) {
            for (var k = ci; k < bestEnd; k++) {
                if (
                    groups.length > 0 &&
                    _solver_arraysEqual(groups[groups.length - 1][0], [changes[k]])
                ) {
                    var prev = groups[groups.length - 1];
                    groups[groups.length - 1] = [prev[0], prev[1], k + 1];
                } else {
                    groups.push([[changes[k]], k, k + 1]);
                }
            }
        } else {
            groups.push([bestPattern, ci, bestEnd]);
        }
        ci = bestEnd;
    }

    // 隣接する同一衣装の単一パターンをマージ
    var merged = [];
    for (var gi = 0; gi < groups.length; gi++) {
        var g = groups[gi];
        if (
            merged.length > 0 &&
            g[0].length === 1 &&
            merged[merged.length - 1][0].length === 1 &&
            g[0][0] === merged[merged.length - 1][0][0]
        ) {
            var mp = merged[merged.length - 1];
            merged[merged.length - 1] = [mp[0], mp[1], g[2]];
        } else {
            merged.push(g);
        }
    }

    // 要約行を生成
    var summary = [];
    for (var mi = 0; mi < merged.length; mi++) {
        var pat = merged[mi][0];
        var start = merged[mi][1];
        var end = merged[mi][2];
        var fromState = path[start];
        var toState = path[end];
        var desc;

        if (pat.length === 1) {
            var cc = pat[0];
            var name = costumeNames[cc];
            if (toState[cc] - fromState[cc] === 1) {
                desc = name + ": " + toState[cc];
            } else {
                desc = name + ": " + fromState[cc] + " \u2192 " + toState[cc];
            }
        } else {
            var names = pat.map(function (c) {
                return costumeNames[c];
            });
            var rotating = names.join("\u2192");
            var totalSteps = end - start;
            var fullRepeats = Math.floor(totalSteps / pat.length);
            var remainder = totalSteps % pat.length;
            var countStr = remainder === 0
                ? "x " + fullRepeats
                : "x " + fullRepeats + "+" + remainder;
            var parts = [];
            var seen = {};
            for (var pi = 0; pi < pat.length; pi++) {
                var pc = pat[pi];
                if (seen[pc]) continue;
                seen[pc] = true;
                if (fromState[pc] !== toState[pc]) {
                    if (toState[pc] - fromState[pc] === 1) {
                        parts.push(costumeNames[pc] + " " + toState[pc]);
                    } else {
                        parts.push(
                            costumeNames[pc] +
                                " " +
                                fromState[pc] +
                                " \u2192 " +
                                toState[pc]
                        );
                    }
                }
            }
            desc = "[" + rotating + "] " + countStr + " " + parts.join(", ");
        }

        summary.push({ description: desc, from: fromState, to: toState });
    }

    return summary;
}

/* ------------------------------------------------------------------ */
/*  Dash コンポーネント生成ヘルパー                                      */
/* ------------------------------------------------------------------ */

function _solver_h(type, props) {
    return {
        namespace: "dash_html_components",
        type: type,
        props: props || {},
    };
}

function _solver_dataTable(props) {
    return { namespace: "dash_table", type: "DataTable", props: props };
}

/* ------------------------------------------------------------------ */
/*  スピナーコンポーネント                                                */
/* ------------------------------------------------------------------ */

function _solver_spinnerComponent() {
    return _solver_h("Div", {
        children: _solver_h("Div", {
            style: {
                width: "40px",
                height: "40px",
                border: "4px solid #e0e0e0",
                borderTopColor: "#4a90d9",
                borderRadius: "50%",
                animation: "solver-spin .8s linear infinite",
            },
        }),
        style: {
            display: "flex",
            justifyContent: "center",
            padding: "40px",
        },
    });
}

/* ------------------------------------------------------------------ */
/*  ビームサーチソルバー                                                  */
/* ------------------------------------------------------------------ */

/**
 * ビームサーチ（経験値効率ソート）。
 *
 * 各深さ（レベルアップ回数）ごとにビーム幅の上位状態を保持し、
 * 全て展開して次の深さの候補を生成する。
 * ソートキーは score / totalExp（経験値効率）。
 *
 * 厳密解は保証しないが、衣装数が多い場合でも実用的な解を返す。
 */
function _solver_solveBeam(currentRanks, allBondBonuses) {
    var n = currentRanks.length;
    // 衣装数に応じてビーム幅を自動調整 (計算量 ∝ width * n^2 を一定に保つ)
    var BEAM_WIDTH = Math.min(10000, Math.floor(160000 / (n * n)));
    var cumPerCostume = allBondBonuses.map(function (bb) {
        return _solver_cumulativeBonus(bb);
    });

    var totalSteps = 0;
    for (var i = 0; i < n; i++) totalSteps += 50 - currentRanks[i];

    var initialKey = currentRanks.join(",");

    var bestScore = new Map();
    bestScore.set(initialKey, 0);
    var dp = new Map();
    dp.set(initialKey, 0);
    var dpPre = new Map();

    // currentBeam: [{ score, totalExp, state, key }]
    var currentBeam = [{ score: 0, totalExp: 0, state: currentRanks.slice(), key: initialKey }];

    for (var depth = 0; depth < totalSteps; depth++) {
        // 候補を生成: nextKey -> { score, totalExp, state, prevKey }
        var candidates = new Map();

        for (var bi = 0; bi < currentBeam.length; bi++) {
            var item = currentBeam[bi];
            var score = item.score;
            var totalExp = item.totalExp;
            var state = item.state;
            var key = item.key;

            if (score < bestScore.get(key)) continue;

            var bonus = _solver_getBonus(state, cumPerCostume);

            for (var ci = 0; ci < n; ci++) {
                if (state[ci] >= 50) continue;

                var exp = _solver_BOND_EXP_PER_LEVEL[state[ci] - 1];
                var newScore = score + exp * bonus;
                var newTotalExp = totalExp + exp;

                state[ci]++;
                var newKey = state.join(",");
                state[ci]--;

                var existing = candidates.get(newKey);
                if (!existing || newScore > existing.score) {
                    candidates.set(newKey, {
                        score: newScore,
                        totalExp: newTotalExp,
                        prevKey: key,
                    });
                }
            }
        }

        // efficiency (score / totalExp) 降順でソートし上位 BEAM_WIDTH 個を保持
        var arr = [];
        candidates.forEach(function (val, nk) {
            arr.push({ key: nk, score: val.score, totalExp: val.totalExp, prevKey: val.prevKey });
        });
        arr.sort(function (a, b) {
            return (b.score / b.totalExp) - (a.score / a.totalExp);
        });
        if (arr.length > BEAM_WIDTH) arr.length = BEAM_WIDTH;

        currentBeam = [];
        for (var ai = 0; ai < arr.length; ai++) {
            var e = arr[ai];
            var oldBest = bestScore.get(e.key);
            if (oldBest === undefined || e.score > oldBest) {
                bestScore.set(e.key, e.score);
                dp.set(e.key, e.score);
                dpPre.set(e.key, e.prevKey);
            }
            currentBeam.push({
                score: e.score,
                totalExp: e.totalExp,
                state: e.key.split(",").map(Number),
                key: e.key,
            });
        }
    }

    var _goalKey = new Array(n).fill(50).join(",");
    console.debug("[BeamSearch] goal score:", dp.get(_goalKey));

    return { dp: dp, dpPre: dpPre };
}

/* ------------------------------------------------------------------ */
/*  ソルバ��レジストリ                                                    */
/* ------------------------------------------------------------------ */

var _solver_registry = {
    dp: _solver_solve,
    chokudai: _solver_solveBeam,
};

function _solver_dispatch(solverType, currentRanks, allBondBonuses) {
    var solver = _solver_registry[solverType];
    if (!solver) {
        throw new Error("未知のソルバー: " + solverType);
    }
    return solver(currentRanks, allBondBonuses);
}

/* ------------------------------------------------------------------ */
/*  メイン計算ロジック                                                   */
/* ------------------------------------------------------------------ */

function _solver_calcChartSync(
    rankValues, rankIds, bondValues, bondIds, costumeValues, costumeIds,
    solverType
) {
    // --- データ組み立て ---
    var idxOrder = costumeIds.map(function (id) {
        return id.index;
    });

    var costumeNames = costumeValues.map(function (v, i) {
        return v || _solver_defaultCostumeName(costumeIds[i].index);
    });

    var rankMap = {};
    rankIds.forEach(function (id, i) {
        rankMap[id.index] = rankValues[i];
    });
    var currentRanks = idxOrder.map(function (idx) {
        return rankMap[idx];
    });

    var bondMap = {};
    idxOrder.forEach(function (idx) {
        bondMap[idx] = new Array(_solver_BOND_RANGES.length).fill(0);
    });
    bondIds.forEach(function (id, i) {
        bondMap[id.index][id.range_idx] = bondValues[i] || 0;
    });
    var allBondBonuses = idxOrder.map(function (idx) {
        return bondMap[idx];
    });

    // --- ソルバー実行 ---
    var result = _solver_dispatch(solverType || "dp", currentRanks, allBondBonuses);
    var dp = result.dp;
    var dpPre = result.dpPre;

    // --- 経路復元 ---
    var path = _solver_reconstructPath(dp, dpPre, idxOrder.length);
    if (!path) {
        return _solver_h("P", {
            children: "\u7d4c\u8def\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002",
            style: { color: "red" },
        });
    }

    // --- 要約 ---
    var summary = _solver_summarizePath(path, costumeNames);

    // --- 要約表 ---
    var summaryColumns = costumeNames.map(function (name, i) {
        return { name: name, id: "c" + i };
    });
    summaryColumns.push({
        name: "\u7d46\u4e0a\u3052\u512a\u5148\u5ea6",
        id: "description",
    });

    var summaryData = summary.map(function (s) {
        var row = { description: s.description };
        for (var ci = 0; ci < costumeNames.length; ci++) {
            row["c" + ci] = s.to[ci];
        }
        return row;
    });

    var summaryStyleCond = [
        { if: { row_index: "odd" }, backgroundColor: "#f9f9f9" },
    ];
    // 最初の行: 初期状態 (from) との比較
    for (var ci = 0; ci < costumeNames.length; ci++) {
        if (summary.length > 0 && summary[0].to[ci] !== summary[0].from[ci]) {
            summaryStyleCond.push({
                if: { row_index: 0, column_id: "c" + ci },
                backgroundColor: "#fff3cd",
                fontWeight: "bold",
            });
        }
    }
    for (var ri = 1; ri < summary.length; ri++) {
        for (var ci = 0; ci < costumeNames.length; ci++) {
            if (summary[ri].to[ci] !== summary[ri - 1].to[ci]) {
                summaryStyleCond.push({
                    if: { row_index: ri, column_id: "c" + ci },
                    backgroundColor: "#fff3cd",
                    fontWeight: "bold",
                });
            }
        }
    }

    var summaryTable = _solver_dataTable({
        columns: summaryColumns,
        data: summaryData,
        fixed_rows: { headers: true },
        style_table: {
            overflowX: "auto",
            maxHeight: "70vh",
            overflowY: "auto",
        },
        style_cell: {
            textAlign: "center",
            padding: "4px 8px",
            fontSize: "0.9rem",
        },
        style_cell_conditional: [
            {
                if: { column_id: "description" },
                textAlign: "left",
                minWidth: "200px",
            },
        ],
        style_header: {
            fontWeight: "bold",
            background: "#2ecc71",
            color: "white",
            position: "sticky",
            top: 0,
        },
        style_data_conditional: summaryStyleCond,
        page_size: 200,
    });

    // --- 詳細表 ---
    var detailColumns = costumeNames.map(function (name, i) {
        return { name: name, id: "c" + i };
    });
    var detailData = path.map(function (step) {
        var row = {};
        for (var i = 0; i < costumeNames.length; i++) {
            row["c" + i] = step[i];
        }
        return row;
    });

    var detailStyleCond = [
        { if: { row_index: "odd" }, backgroundColor: "#f9f9f9" },
    ];
    for (var dri = 1; dri < path.length; dri++) {
        for (var dci = 0; dci < costumeNames.length; dci++) {
            if (path[dri][dci] !== path[dri - 1][dci]) {
                detailStyleCond.push({
                    if: { row_index: dri, column_id: "c" + dci },
                    backgroundColor: "#fff3cd",
                    fontWeight: "bold",
                });
            }
        }
    }

    var detailTable = _solver_dataTable({
        columns: detailColumns,
        data: detailData,
        fixed_rows: { headers: true },
        style_table: {
            overflowX: "auto",
            maxHeight: "50vh",
            overflowY: "auto",
        },
        style_cell: {
            textAlign: "center",
            padding: "4px 8px",
            fontSize: "0.9rem",
        },
        style_header: {
            fontWeight: "bold",
            background: "#2ecc71",
            color: "white",
            position: "sticky",
            top: 0,
        },
        style_data_conditional: detailStyleCond,
        page_size: 200,
    });

    // --- CSV 用データをグローバルに保持 ---
    var csvHeader = costumeNames.slice();
    csvHeader.push("\u7d46\u4e0a\u3052\u512a\u5148\u5ea6");
    var csvRows = summary.map(function (s) {
        var row = costumeNames.map(function (_, ci) {
            return String(s.to[ci]);
        });
        row.push(s.description);
        return row;
    });
    window._bondChartCsvData = JSON.stringify({
        header: csvHeader,
        rows: csvRows,
    });

    // --- 結果コンポーネント ---
    var btnStyle = {
        padding: "6px 16px",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
        fontSize: "0.85rem",
        color: "white",
    };

    return _solver_h("Div", {
        children: [
            _solver_h("Div", {
                children: [
                    _solver_h("H3", {
                        children: "\u8981\u7d04\u30c1\u30e3\u30fc\u30c8",
                        style: { marginBottom: "0" },
                    }),
                    _solver_h("Div", {
                        children: [
                            _solver_h("Button", {
                                children: "\u753b\u50cf\u4fdd\u5b58",
                                id: "save-image-btn",
                                n_clicks: 0,
                                style: Object.assign({}, btnStyle, {
                                    background: "#e67e22",
                                }),
                            }),
                            _solver_h("Button", {
                                children: "CSV\u4fdd\u5b58",
                                id: "save-csv-btn",
                                n_clicks: 0,
                                style: Object.assign({}, btnStyle, {
                                    background: "#8e44ad",
                                }),
                            }),
                        ],
                        style: {
                            display: "flex",
                            gap: "8px",
                            marginLeft: "auto",
                        },
                    }),
                ],
                style: {
                    display: "flex",
                    alignItems: "center",
                    marginBottom: "8px",
                },
            }),
            _solver_h("Div", {
                children: summaryTable,
                id: "summary-table-container",
            }),
            _solver_h("Details", {
                children: [
                    _solver_h("Summary", {
                        children:
                            "\u8a73\u7d30\u30c1\u30e3\u30fc\u30c8\uff08\u5168\u30b9\u30c6\u30c3\u30d7\uff09",
                        style: {
                            cursor: "pointer",
                            marginTop: "16px",
                            marginBottom: "8px",
                            fontWeight: "bold",
                        },
                    }),
                    detailTable,
                ],
            }),
        ],
    });
}

/* ------------------------------------------------------------------ */
/*  Dash clientside_callback 登録                                      */
/* ------------------------------------------------------------------ */

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.solver = {
    /**
     * ステップ1: スピナー表示 + 入力データを Store に格納
     */
    collect_inputs: function (
        n_clicks,
        rankValues,
        rankIds,
        bondValues,
        bondIds,
        costumeValues,
        costumeIds,
        solverType
    ) {
        if (!n_clicks) return [
            window.dash_clientside.no_update,
            window.dash_clientside.no_update,
        ];

        var inputs = {
            rankValues: rankValues,
            rankIds: rankIds,
            bondValues: bondValues,
            bondIds: bondIds,
            costumeValues: costumeValues,
            costumeIds: costumeIds,
            solverType: solverType,
        };

        return [_solver_spinnerComponent(), inputs];
    },

    /**
     * ステップ2: DP 実行 + 結果表示
     */
    calc_chart: function (solverInputs) {
        if (!solverInputs) return window.dash_clientside.no_update;

        return new Promise(function (resolve) {
            setTimeout(function () {
                resolve(
                    _solver_calcChartSync(
                        solverInputs.rankValues,
                        solverInputs.rankIds,
                        solverInputs.bondValues,
                        solverInputs.bondIds,
                        solverInputs.costumeValues,
                        solverInputs.costumeIds,
                        solverInputs.solverType
                    )
                );
            }, 50);
        });
    },
};
