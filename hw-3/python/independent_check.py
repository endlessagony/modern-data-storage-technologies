"""
Независимая проверка контрольного среза (31 матч плей-офф ЧМ-2022 и Евро-2024, 866 ударов из ДЗ-2).

Витрина «команда x день» считается прямо из control_shots.csv обычным Python (без SQL и без нашей схемы),
затем сравнивается с результатом SQL на каждой таблице фактов. Дополнительно сверяются итоги, известные
из ДЗ-2: финал ЧМ-2022, число ударов в игровое время и голы против счёта матчей.

Запуск: python independent_check.py [--port 5440] [--db shots] [--tables dds.fact_shot,dds.fact_shot_idx]
"""
import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import psycopg2

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ON_TARGET = {"Goal", "Saved", "Saved to Post"}
ALL_TABLES = "dds.fact_shot,dds.fact_shot_idx,dds.fact_shot_part,dds.fact_shot_part_idx"

CONTROL_SQL = """
select team_id, match_date::text, count(*), count(*) filter (where is_on_target),
       count(*) filter (where is_goal), count(*) filter (where is_goal and is_penalty), sum(xg)
from {table}
where source_system = 'statsbomb' and not is_shootout and match_id = any(%s)
group by team_id, match_date
"""


def read_csv(name):
    with open(DATA_DIR / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def expected_from_csv(shots):
    """Собственный расчёт витрины: ключ (team_id, дата) -> (удары, в створ, голы, голы с пенальти, xG)."""
    acc = defaultdict(lambda: [0, 0, 0, 0, Decimal(0)])
    for s in shots:
        if s["period"] == "5":          # серия пенальти в игровую статистику не входит
            continue
        row = acc[(int(s["team_id"]), s["match_date"])]
        goal = s["outcome"] == "Goal"
        row[0] += 1
        row[1] += s["outcome"] in ON_TARGET
        row[2] += goal
        row[3] += goal and s["shot_type"] == "Penalty"
        row[4] += Decimal(s["xg"])
    return {k: tuple(v) for k, v in acc.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5440)
    parser.add_argument("--db", default="shots")
    parser.add_argument("--tables", default=ALL_TABLES)
    args = parser.parse_args()

    matches = read_csv("control_matches.csv")
    shots = read_csv("control_shots.csv")
    match_ids = [int(m["match_id"]) for m in matches]
    expected = expected_from_csv(shots)
    failures = 0

    in_play = [s for s in shots if s["period"] != "5"]
    goals = sum(s["outcome"] == "Goal" for s in in_play)
    score_sum = sum(int(m["home_score"]) + int(m["away_score"]) for m in matches)
    print("== независимый расчёт из control_shots.csv ==")
    print(f"матчей: {len(matches)}, ударов всего: {len(shots)}, серия пенальти: {len(shots) - len(in_play)}, "
          f"в игровое время: {len(in_play)}")
    print(f"строк витрины (команда x день): {len(expected)}, голов из ударов: {goals}, "
          f"сумма счетов: {score_sum} (разница = автоголы, они ударами не считаются)")
    for team_id, day, name in [(779, "2022-12-18", "Argentina"), (771, "2022-12-18", "France")]:
        row = expected[(team_id, day)]
        print(f"финал ЧМ-2022, {name}: удары {row[0]}, в створ {row[1]}, голы {row[2]}, "
              f"с пенальти {row[3]}, xG {row[4].quantize(Decimal('0.0001'))}")
    final = {name: expected[(tid, "2022-12-18")] for tid, name in [(779, "ARG"), (771, "FRA")]}
    known = {"ARG": (20, 10, 3, 1, Decimal("2.7583")), "FRA": (10, 5, 3, 2, Decimal("2.2726"))}   # ДЗ-2, запрос Q1
    for name, values in known.items():
        got = final[name][:4] + (final[name][4].quantize(Decimal("0.0001")),)
        ok = got == values
        failures += not ok
        print(f"  сверка с ДЗ-2 ({name}): ожидалось {values}, получено {got} - {'совпало' if ok else 'РАСХОЖДЕНИЕ'}")
    ok = (len(shots), len(in_play), goals, score_sum) == (866, 801, 84, 88)
    failures += not ok
    print(f"  сверка итогов среза с ДЗ-2 (866 / 801 / 84 голов / счета 88): {'совпало' if ok else 'РАСХОЖДЕНИЕ'}")

    conn = psycopg2.connect(host="127.0.0.1", port=args.port, dbname=args.db, user="postgres")
    cur = conn.cursor()
    print("\n== SQL на таблицах против независимого расчёта (точное сравнение, включая xG) ==")
    for table in args.tables.split(","):
        cur.execute(CONTROL_SQL.format(table=table), (match_ids,))
        actual = {(r[0], r[1]): (r[2], r[3], r[4], r[5], r[6]) for r in cur.fetchall()}
        missing = set(expected) - set(actual)
        extra = set(actual) - set(expected)
        different = [k for k in expected if k in actual and actual[k] != expected[k]]
        ok = not (missing or extra or different) and len(actual) == len(expected)
        failures += not ok
        print(f"{table:28} строк {len(actual):>4} из {len(expected)}, "
              f"нет в SQL: {len(missing)}, лишних: {len(extra)}, отличий в мерах: {len(different)} - "
              f"{'совпало' if ok else 'РАСХОЖДЕНИЕ'}")

    print("\nИТОГ:", "все проверки пройдены" if not failures else f"расхождений: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
