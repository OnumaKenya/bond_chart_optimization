"""生徒情報モデル。"""

from dataclasses import dataclass, field


# 絆ボーナスの区間定義
BOND_RANGES = [
    (2, 5),
    (6, 10),
    (11, 15),
    (16, 20),
    (21, 30),
    (31, 40),
    (41, 50),
]


@dataclass
class Student:
    """生徒1人分の情報。"""

    costume_name: str = ""
    bond_bonuses: list[int] = field(default_factory=lambda: [0] * len(BOND_RANGES))

    def bond_bonus_label(self, idx: int) -> str:
        """idx 番目の絆ボーナス区間のラベルを返す。"""
        lo, hi = BOND_RANGES[idx]
        return f"絆{lo}~{hi}ボーナス"
