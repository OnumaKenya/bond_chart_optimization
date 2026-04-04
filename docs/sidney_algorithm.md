# Sidney 分解による絆チャート最適化

## 問題設定

$n$ 個の衣装があり、それぞれ現在の絆ランク $r_i$ から 50 まで上げる。各ステップでは 1 つの衣装を 1 ランク上げ、そのときのスコア寄与は

$$\text{score} = \text{exp}(r) \times \text{bonus}_{\text{total}}$$

- $\text{exp}(r)$: ランク $r \to r+1$ に必要な経験値 (`BOND_EXP_PER_LEVEL[r-1]`)
- $\text{bonus}_{\text{total}}$: 全衣装の累積ボーナスの合計（ステップ実行**前**の値）

**目的**: 全衣装をランク 50 にする順序を選び、スコアの総和を最大化する。

## スケジューリング問題への帰着

### ジョブとチェーンの定義

各ランクアップを「ジョブ」として定義する。衣装 $i$ のランク $r \to r+1$ に対応するジョブ $j$ は:

- **重み** $w_j = \text{exp}(r)$（経験値）
- **処理時間** $p_j = \delta_j = \text{cum}_i(r+1) - \text{cum}_i(r)$（ボーナス増分）

各衣装内ではランクを順に上げる必要があるため、**チェーン順序制約**が存在する:

$$j_{i,r_i} \to j_{i,r_i+1} \to \cdots \to j_{i,49}$$

### 目的関数の変換

ステップ $t$ 実行時のボーナスは初期ボーナス $B_0$ に、それまでに実行されたジョブの $\delta$ の累積を加えたものである:

$$S = \sum_t w_t \cdot \left(B_0 + \sum_{s < t} \delta_s \right)$$

完了時刻 $C_j = \sum_{k \leq j} p_k$ を用いると $\sum_{s<t} \delta_s = C_t - p_t$ なので:

$$S = \underbrace{B_0 \sum w_t + \sum w_t \cdot C_t - \sum w_t \cdot p_t}_{= \text{定数} + \sum w_t C_t}$$

したがって:

$$\max S \iff \max \sum_j w_j C_j$$

これは **1|chains|max $\sum w_j C_j$** というスケジューリング問題に一致する。

### max から min への変換

任意のスケジュール $\sigma$ とその逆順 $\sigma^R$ について、各ジョブの完了時刻は

$$C_j(\sigma) + C_j(\sigma^R) = P + p_j \quad (P = \sum_j p_j)$$

を満たす。よって

$$\max \sum w_j C_j \;\text{(元のチェーン)} = \text{定数} - \min \sum w_j C_j \;\text{(逆順チェーン)}$$

逆順チェーンもチェーンなので、既知の **1|chains|min $\sum w_j C_j$** の多項式時間アルゴリズムが適用できる。

## Sidney 分解アルゴリズム

### 交換論法

隣接する 2 ステップ A, B（異なる衣装）の順序を入れ替えたときのスコア差は:

$$\Delta = w_B \cdot p_A - w_A \cdot p_B$$

$\max \sum w_j C_j$ では $\Delta > 0$、すなわち $p_A / w_A > p_B / w_B$ のとき A を先にすべきである。

しかし、チェーン制約がある場合、単純に $p/w$ 比でソートするだけでは最適にならない（後述の反例参照）。

### ブロック分解（スタックベース）

各チェーン内で、$p/w$ 比が**非増加**になるようブロックをマージする。

```
チェーン [j1, j2, ..., jk] を左から処理:
  スタック = []
  各ジョブ j について:
    新ブロック = {j}
    while スタック先頭ブロックの p/w < 新ブロックの p/w:
      新ブロック = スタック先頭とマージ (p, w をそれぞれ加算)
    スタックに push
```

**マージの意味**: 後続ジョブの $p/w$ が高い場合、そのジョブは「先に実行したい」がチェーン制約で前のジョブを越えられない。両者を一体のブロックとして扱うことで、全体の中での正しい配置が決まる。

### グローバルソート

全チェーンから得られたブロックを $p/w$ **降順**にソートし、その順にスケジュールする。ブロック内のジョブはチェーン順（ランク昇順）で実行する。

## 非凸ボーナスでの反例

単純貪欲法（毎ステップ $\delta/\text{exp}$ 比最大を選ぶ）が失敗する例:

| ジョブ | $w$ (exp) | $p$ ($\delta$) | $p/w$ |
|--------|-----------|----------------|-------|
| A1     | 1         | 0              | 0     |
| A2     | 1         | 100            | 100   |
| B1     | 1         | 1              | 1     |

チェーン: A1 $\to$ A2、B1 は独立。

- **貪欲法**: B1 ($p/w=1$) を A1 ($p/w=0$) より先に選択 $\to$ B1, A1, A2: スコア = 2
- **Sidney 分解**: A1 と A2 をマージ $\to$ ブロック(A1+A2) の $p/w = 100/2 = 50 > 1$ $\to$ A1, A2, B1: スコア = **100**

Sidney 分解はマージにより「A1 の先に高 $\delta$ の A2 が控えている」ことを反映できる。

## 計算量

| 処理 | 計算量 |
|------|--------|
| ジョブ構築 | $O(T)$ |
| チェーン内マージ | $O(T)$（各ジョブは高々 1 回 push/pop） |
| ブロックのソート | $O(T \log T)$ |
| 経路構築 | $O(T)$ |
| **合計** | $O(T \log T)$ |

$T = \sum_i (50 - r_i)$: 総ステップ数。衣装数 $n$ に対し指数的だった DP ($O(51^n)$) と比べ、$n$ に依存しない。

## 前提条件

- $p_j = \delta_j \geq 0$: 各ランクアップでのボーナス増分が非負であること。ゲームの絆ボーナスは常に非負のため成立する。

## 参考文献

- W. E. Smith, "Various optimizers for single-stage production," *Naval Research Logistics Quarterly*, vol. 3, pp. 59--66, 1956.
- J. B. Sidney, "Decomposition algorithms for single-machine sequencing with precedence relations and deferral costs," *Operations Research*, vol. 23, no. 2, pp. 283--298, 1975.
- E. L. Lawler, "Sequencing jobs to minimize total weighted completion time subject to precedence constraints," *Annals of Discrete Mathematics*, vol. 2, pp. 75--90, 1978.
