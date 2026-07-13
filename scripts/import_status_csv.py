#!/usr/bin/env python3
"""生徒ステータスCSVの絆ランクボーナスをプリセットDBへ取り込む。

デフォルトはドライラン（差分の表示のみ）。--apply を付けると書き込む。
取り込んだ (生徒, ステータス) は公式データとして承認済みにする。
DBにあってCSVに無いプリセットは削除しない。

使い方:
    python scripts/import_status_csv.py                    # ドライラン
    python scripts/import_status_csv.py --apply            # ローカルDBへ書き込み
    python scripts/import_status_csv.py --env-var PROD_DATABASE_URL --apply
    python scripts/import_status_csv.py --keep-existing --apply  # 既存値は変更しない
"""

import argparse
import os
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE_DIR))

from app.backend.status_csv import parse_status_csv  # noqa: E402

_DEFAULT_CSV = _BASE_DIR / "data" / "生徒ステータスまとめ (仮) 公開用 - ステータス .csv"
_ENV_PATH = _BASE_DIR / ".env"

# DB側の旧表記 -> CSV(正)表記。取り込み前にDBの衣装名をリネームする。
_COSTUME_RENAMES = {
    ("トキ", "バニー"): "バニーガール",
    ("ネル", "バニー"): "バニーガール",
}

_DEFAULT_COSTUME = "通常"


def _load_env():
    if _ENV_PATH.exists():
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _load_db_state(cur):
    """DBの現状を読み込む。

    Returns
    -------
    costumes: {(student, costume): {"id": int, "sort_order": int}}
    bonuses: {(student, costume, status): [int]}
    approvals: {(student, status): bool}
    """
    cur.execute("SELECT id, student_name, costume_name, sort_order FROM costume")
    costumes = {
        (r[1], r[2]): {"id": r[0], "sort_order": r[3]} for r in cur.fetchall()
    }
    cur.execute(
        "SELECT c.student_name, c.costume_name, bb.status_name, bb.bond_bonuses "
        "FROM bond_bonus bb JOIN costume c ON c.id = bb.costume_id"
    )
    bonuses = {(r[0], r[1], r[2]): list(r[3]) for r in cur.fetchall()}
    cur.execute("SELECT student_name, status_name, approved FROM preset_approval")
    approvals = {(r[0], r[1]): r[2] for r in cur.fetchall()}
    return costumes, bonuses, approvals


def _apply_renames(costumes, bonuses):
    """DB側の旧衣装名をCSV表記に読み替え、実行するリネームを返す。"""
    renames = []
    for (student, old_name), new_name in _COSTUME_RENAMES.items():
        key = (student, old_name)
        if key not in costumes:
            continue
        if (student, new_name) in costumes:
            raise RuntimeError(
                f"リネーム先が既に存在します: {student} / {old_name} -> {new_name}"
            )
        costumes[(student, new_name)] = costumes.pop(key)
        for bkey in [k for k in bonuses if k[0] == student and k[1] == old_name]:
            bonuses[(student, new_name, bkey[2])] = bonuses.pop(bkey)
        renames.append((student, old_name, new_name))
    return renames


def _desired_costume_order(csv_names: list[str], db_names: list[str]) -> list[str]:
    """生徒1人分の衣装の表示順を決める。

    通常を先頭に、CSVの衣装を実装順で並べ、CSVに無いDB衣装は
    現在の並びのまま末尾に置く。
    """
    db_only = [n for n in db_names if n not in csv_names]
    ordered = [n for n in csv_names if n != _DEFAULT_COSTUME]
    if _DEFAULT_COSTUME in csv_names or _DEFAULT_COSTUME in db_only:
        ordered.insert(0, _DEFAULT_COSTUME)
    ordered += [n for n in db_only if n != _DEFAULT_COSTUME]
    return ordered


def _build_plan(presets, costumes, bonuses, approvals, keep_existing):
    """CSV内容とDB現状の差分から実行計画を作る。"""
    plan = {
        "new_costumes": [],  # (student, costume, sort_order)
        "reorder_costumes": [],  # (student, costume, old_so, new_so)
        "new_bonuses": [],  # (student, costume, status, values)
        "changed_bonuses": [],  # (student, costume, status, old, new)
        "kept_bonuses": [],  # keep_existing で保持した差分
        "approvals": [],  # (student, status, old(None=なし))
    }

    # 生徒ごとの衣装の表示順（同一生徒の全プリセットで衣装リストは共通）
    csv_names_by_student: dict[str, list[str]] = {}
    for p in presets:
        csv_names_by_student.setdefault(
            p["student_name"], [c["costume_name"] for c in p["costumes"]]
        )
    db_names_by_student: dict[str, list[str]] = {}
    for (student, costume), info in sorted(
        costumes.items(), key=lambda kv: kv[1]["sort_order"]
    ):
        db_names_by_student.setdefault(student, []).append(costume)

    for student, csv_names in csv_names_by_student.items():
        ordered = _desired_costume_order(
            csv_names, db_names_by_student.get(student, [])
        )
        for so, costume in enumerate(ordered):
            existing = costumes.get((student, costume))
            if existing is None:
                if costume in csv_names:
                    plan["new_costumes"].append((student, costume, so))
            elif existing["sort_order"] != so:
                plan["reorder_costumes"].append(
                    (student, costume, existing["sort_order"], so)
                )

    for p in presets:
        student = p["student_name"]
        status = p["status_name"]
        for c in p["costumes"]:
            costume = c["costume_name"]
            values = c["bond_bonuses"]
            bkey = (student, costume, status)
            old = bonuses.get(bkey)
            if old is None:
                plan["new_bonuses"].append((student, costume, status, values))
            elif old != values:
                if keep_existing:
                    plan["kept_bonuses"].append((student, costume, status, old, values))
                else:
                    plan["changed_bonuses"].append(
                        (student, costume, status, old, values)
                    )
        akey = (student, status)
        if approvals.get(akey) is not True:
            plan["approvals"].append((student, status, approvals.get(akey)))
    return plan


def _print_plan(result, plan):
    if result.skipped:
        print(f"◆ 取り込み対象外の行: {len(result.skipped)}")
        for name, reason in result.skipped:
            print(f"    {name}: {reason}")
        print()

    print(f"◆ 衣装名の変更（表記統一）: {len(plan['renames'])}")
    for student, old, new in plan["renames"]:
        print(f"    ~ {student} / {old} -> {new}")
    print(f"◆ 新規衣装: {len(plan['new_costumes'])}")
    for student, costume, so in plan["new_costumes"]:
        print(f"    + {student} / {costume} (sort_order={so})")
    print(f"◆ 衣装の表示順変更: {len(plan['reorder_costumes'])}")
    for student, costume, old, new in plan["reorder_costumes"]:
        print(f"    ~ {student} / {costume}: sort_order {old} -> {new}")
    print(f"◆ 新規絆ボーナス: {len(plan['new_bonuses'])}")
    for student, costume, status, values in plan["new_bonuses"]:
        print(f"    + {student} / {costume} ({status}): {values}")
    print(f"◆ 既存と異なる絆ボーナス（上書き）: {len(plan['changed_bonuses'])}")
    for student, costume, status, old, new in plan["changed_bonuses"]:
        print(f"    ! {student} / {costume} ({status}): DB {old} -> CSV {new}")
    if plan["kept_bonuses"]:
        print(f"◆ 既存と異なるがDB値を保持 (--keep-existing): {len(plan['kept_bonuses'])}")
        for student, costume, status, old, new in plan["kept_bonuses"]:
            print(f"    = {student} / {costume} ({status}): DB {old} (CSV {new})")
    print(f"◆ 承認済みに変更: {len(plan['approvals'])}")
    for student, status, old in plan["approvals"]:
        state = "未登録" if old is None else "未承認"
        print(f"    + {student} ({status}): {state} -> 承認済み")


def _apply_plan(conn, plan):
    with conn.cursor() as cur:
        for student, old, new in plan["renames"]:
            cur.execute(
                "UPDATE costume SET costume_name = %s "
                "WHERE student_name = %s AND costume_name = %s",
                (new, student, old),
            )
        for student, costume, so in plan["new_costumes"]:
            cur.execute(
                "INSERT INTO costume (student_name, costume_name, sort_order) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (student_name, costume_name) "
                "DO UPDATE SET sort_order = EXCLUDED.sort_order",
                (student, costume, so),
            )
        for student, costume, _old, new in plan["reorder_costumes"]:
            cur.execute(
                "UPDATE costume SET sort_order = %s "
                "WHERE student_name = %s AND costume_name = %s",
                (new, student, costume),
            )
        for student, costume, status, values in plan["new_bonuses"]:
            cur.execute(
                "INSERT INTO bond_bonus (costume_id, status_name, bond_bonuses) "
                "SELECT c.id, %s, %s FROM costume c "
                "WHERE c.student_name = %s AND c.costume_name = %s "
                "ON CONFLICT (costume_id, status_name) "
                "DO UPDATE SET bond_bonuses = EXCLUDED.bond_bonuses",
                (status, values, student, costume),
            )
        for student, costume, status, _old, new in plan["changed_bonuses"]:
            cur.execute(
                "UPDATE bond_bonus SET bond_bonuses = %s "
                "FROM costume c "
                "WHERE bond_bonus.costume_id = c.id "
                "AND c.student_name = %s AND c.costume_name = %s "
                "AND bond_bonus.status_name = %s",
                (new, student, costume, status),
            )
        for student, status, _old in plan["approvals"]:
            cur.execute(
                "INSERT INTO preset_approval (student_name, status_name, approved) "
                "VALUES (%s, %s, TRUE) "
                "ON CONFLICT (student_name, status_name) "
                "DO UPDATE SET approved = TRUE",
                (student, status),
            )


def main():
    parser = argparse.ArgumentParser(
        description="生徒ステータスCSVの絆ボーナスをプリセットDBへ取り込む"
    )
    parser.add_argument("csv_path", nargs="?", default=str(_DEFAULT_CSV))
    parser.add_argument(
        "--apply", action="store_true", help="実際にDBへ書き込む（既定はドライラン）"
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="既にDBにある絆ボーナスはCSVと異なっていても変更しない",
    )
    parser.add_argument(
        "--env-var",
        default="DATABASE_URL",
        help="接続先URLを持つ環境変数名（既定: DATABASE_URL）",
    )
    args = parser.parse_args()

    _load_env()
    db_url = os.environ.get(args.env_var)
    if not db_url:
        print(f"エラー: {args.env_var} が設定されていません")
        return 1

    result = parse_status_csv(args.csv_path)
    print(f"CSV: {len(result.presets)} プリセット "
          f"({len({p['student_name'] for p in result.presets})} 生徒)\n")

    import psycopg2

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            costumes, bonuses, approvals = _load_db_state(cur)
        renames = _apply_renames(costumes, bonuses)
        plan = _build_plan(
            result.presets, costumes, bonuses, approvals, args.keep_existing
        )
        plan["renames"] = renames
        _print_plan(result, plan)
        if not args.apply:
            print("\nドライランです。書き込むには --apply を付けてください。")
            return 0
        _apply_plan(conn, plan)
        conn.commit()
        target = db_url.split("@")[-1] if "@" in db_url else "(unknown)"
        print(f"\n書き込み完了: {target}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
