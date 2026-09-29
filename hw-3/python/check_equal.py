"""
Проверка, что физические варианты не изменили ни данные, ни результат отчёта.

1. Таблицы фактов: двустороннее сравнение через EXCEPT ALL со всеми колонками (учитывает повторы строк).
2. Оба запроса витрины: EXCEPT ALL результата варианта с результатом исходной таблицы в обе стороны,
   число строк, суммы мер и md5 упорядоченного результата.
3. Зерно результата: ключ (source_system, team_id, match_date) уникален в ответах обоих запросов.
Код возврата 1, если хоть одно расхождение найдено.
"""
import os
import sys
from pathlib import Path

import psycopg2

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
BASE = "dds.fact_shot"
OTHERS = ["dds.fact_shot_idx", "dds.fact_shot_part", "dds.fact_shot_part_idx", "dds.fact_shot_idx_rev"]
QUERY_FILES = {"narrow": "query_narrow.sql", "wide": "query_wide.sql"}


def query_text(filename, table):
    return (SQL_DIR / filename).read_text(encoding="utf-8").replace("{fact}", table).strip().rstrip(";")


def scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main():
    conn = psycopg2.connect(host="127.0.0.1", port=int(os.environ.get("MAIN_PORT", 5440)),
                            dbname=os.environ.get("MAIN_DB", "shots"), user="postgres")
    cur = conn.cursor()
    failures = 0

    print("== 1. таблицы фактов против исходной (EXCEPT ALL в обе стороны) ==")
    print(f"{'таблица':28} {'строк':>7} {'исх минус вар':>14} {'вар минус исх':>14}  итог")
    base_rows = scalar(cur, f"select count(*) from {BASE}")
    print(f"{BASE:28} {base_rows:>7} {'-':>14} {'-':>14}  эталон")
    for table in OTHERS:
        rows = scalar(cur, f"select count(*) from {table}")
        left = scalar(cur, f"select count(*) from (select * from {BASE} except all select * from {table}) d")
        right = scalar(cur, f"select count(*) from (select * from {table} except all select * from {BASE}) d")
        ok = rows == base_rows and left == 0 and right == 0
        failures += not ok
        print(f"{table:28} {rows:>7} {left:>14} {right:>14}  {'совпало' if ok else 'РАСХОЖДЕНИЕ'}")

    for name, filename in QUERY_FILES.items():
        print(f"\n== 2. запрос {name}: результат варианта против исходной таблицы ==")
        print(f"{'таблица':28} {'строк':>6} {'исх-вар':>8} {'вар-исх':>8} {'sum(shots)':>10} {'sum(goals)':>10} "
              f"{'sum(xg)':>14}  md5 упорядоченного результата  итог")
        reference = None
        for table in [BASE] + OTHERS:
            q = query_text(filename, table)
            base_q = query_text(filename, BASE)
            rows = scalar(cur, f"select count(*) from ({q}) r")
            left = scalar(cur, f"select count(*) from (({base_q}) except all ({q})) d")
            right = scalar(cur, f"select count(*) from (({q}) except all ({base_q})) d")
            cur.execute(f"""select sum(shots), sum(goals), sum(xg),
                                   md5(string_agg(r::text, E'\\n' order by r.match_date, r.team_id))
                            from ({q}) r""")
            shots, goals, xg, digest = cur.fetchone()
            if reference is None:
                reference = (shots, goals, xg, digest)
            ok = left == 0 and right == 0 and (shots, goals, xg, digest) == reference
            failures += not ok
            print(f"{table:28} {rows:>6} {left:>8} {right:>8} {shots:>10} {goals:>10} {xg:>14} "
                  f" {digest}  {'совпало' if ok else 'РАСХОЖДЕНИЕ'}")

    print("\n== 3. зерно результата: одна строка = команда x день ==")
    two_matches = scalar(cur, """
        select count(*) from (select 1 from dds.fact_shot where not is_shootout
                              group by source_system, team_id, match_date having count(distinct match_id) > 1) t""")
    team_days = scalar(cur, """
        select count(*) from (select 1 from dds.fact_shot where not is_shootout
                              group by source_system, team_id, match_date) t""")
    ok = two_matches == 0
    failures += not ok
    print(f"пар (команда, день) в игровое время: {team_days}, из них с двумя матчами в один день: {two_matches} - "
          f"{'совпало' if ok else 'РАСХОЖДЕНИЕ'}")
    for name, filename in QUERY_FILES.items():
        q = query_text(filename, BASE)
        rows, keys = (scalar(cur, f"select count(*) from ({q}) r"),
                      scalar(cur, f"select count(distinct (source_system, team_id, match_date)) from ({q}) r"))
        ok = rows == keys
        failures += not ok
        print(f"запрос {name}: строк {rows}, различных ключей (source_system, team_id, match_date) {keys} - "
              f"{'ключ уникален' if ok else 'РАСХОЖДЕНИЕ'}")

    print("\nИТОГ:", "все проверки пройдены" if not failures else f"расхождений: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
