"""
Проверка восстановленной базы против исходной. Сравнивается всё, что должно пережить pg_dump/pg_restore:
схемы, таблицы и секции, индексы, ограничения, число строк, заполненность колонок, уникальность ключей,
точное содержимое таблиц (md5 по упорядоченным строкам), контрольные строки и результаты двух запросов.
Код возврата 1, если найдено хоть одно расхождение.
"""
import argparse
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
FACT_TABLES = ["dds.fact_shot", "dds.fact_shot_idx", "dds.fact_shot_part", "dds.fact_shot_part_idx",
               "dds.fact_shot_idx_rev"]
ALL_TABLES = ["dds.match"] + FACT_TABLES + ["stage.matches", "stage.shots"]
FACT_COLUMNS = ["match_date", "source_system", "event_id", "match_id", "team_id", "player_id", "period",
                "minute", "second", "shot_type", "outcome", "is_shootout", "is_penalty", "is_on_target",
                "is_goal", "xg"]
failures = 0


def check(title, ok, detail=""):
    global failures
    failures += not ok
    print(f"[{'ок' if ok else 'ОШИБКА'}] {title}" + (f": {detail}" if detail else ""))


def fetch(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def query_text(name, table):
    return (SQL_DIR / name).read_text(encoding="utf-8").replace("{fact}", table).strip().rstrip(";")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--restored", required=True)
    parser.add_argument("--port", type=int, default=5440)
    args = parser.parse_args()
    src = psycopg2.connect(host="127.0.0.1", port=args.port, dbname=args.source, user="postgres").cursor()
    dst = psycopg2.connect(host="127.0.0.1", port=args.port, dbname=args.restored, user="postgres")
    dst_cur = dst.cursor()

    # структура
    catalog = {
        "схемы": "select nspname from pg_namespace where nspname in ('stage', 'dds') order by 1",
        "таблицы и секции": """select n.nspname || '.' || c.relname || ' ' || c.relkind::text || ' ' ||
                                      coalesce(pg_get_expr(c.relpartbound, c.oid), '')
                               from pg_class c join pg_namespace n on n.oid = c.relnamespace
                               where n.nspname in ('stage', 'dds') and c.relkind in ('r', 'p') order by 1""",
        "индексы": "select schemaname || '.' || indexname || ' ' || indexdef from pg_indexes where schemaname in ('stage', 'dds') order by 1",
        "ограничения": """select conrelid::regclass || ' ' || conname || ' ' || pg_get_constraintdef(oid)
                          from pg_constraint where connamespace in ('stage'::regnamespace, 'dds'::regnamespace) order by 1""",
    }
    print("== структура: исходная база и восстановленная ==")
    for title, sql in catalog.items():
        a, b = fetch(src, sql), fetch(dst_cur, sql)
        check(f"{title}: {len(a)} в исходной, {len(b)} в восстановленной", a == b)

    print("\n== число строк, заполненность колонок, уникальность ключей ==")
    for table in ALL_TABLES:
        a = fetch(src, f"select count(*) from {table}")[0][0]
        b = fetch(dst_cur, f"select count(*) from {table}")[0][0]
        check(f"{table}: строк {a} / {b}", a == b and b > 0)
    for table in FACT_TABLES:
        nulls = fetch(dst_cur, "select " + ", ".join(f"count(*) - count({c})" for c in FACT_COLUMNS) + f" from {table}")[0]
        check(f"{table}: пустых значений во всех {len(FACT_COLUMNS)} колонках", not any(nulls), str(sum(nulls)))
        total, keys = fetch(dst_cur, f"select count(*), count(distinct (source_system, event_id)) from {table}")[0]
        check(f"{table}: ключ (source_system, event_id) уникален", total == keys, f"{total} строк, {keys} ключей")

    print("\n== точное содержимое таблиц (md5 по строкам, упорядоченным по тексту строки) ==")
    for table in ["dds.match"] + FACT_TABLES:
        sql = f"select md5(string_agg(t::text, E'\\n' order by t::text)) from {table} t"
        a, b = fetch(src, sql)[0][0], fetch(dst_cur, sql)[0][0]
        check(f"{table}: {b}", a == b)

    print("\n== контрольные строки (31 матч, 866 ударов): сравнение построчно ==")
    ids = [int(line.split(",")[0]) for line in (DATA_DIR / "control_matches.csv").read_text(encoding="utf-8").splitlines()[1:]]
    sql = "select * from dds.fact_shot where match_id = any(%s) order by source_system, event_id"
    a, b = fetch(src, sql, (ids,)), fetch(dst_cur, sql, (ids,))
    check(f"dds.fact_shot: {len(a)} строк исходной, {len(b)} восстановленной, все значения равны", a == b and len(b) == 866)

    print("\n== результаты двух запросов витрины на восстановленной базе ==")
    for name, filename in [("narrow", "query_narrow.sql"), ("wide", "query_wide.sql")]:
        for table in FACT_TABLES[:4]:
            sql = f"select count(*), sum(shots), sum(goals), sum(xg), md5(string_agg(r::text, E'\\n' order by r.match_date, r.team_id)) from ({query_text(filename, table)}) r"
            a, b = fetch(src, sql)[0], fetch(dst_cur, sql)[0]
            check(f"{name:6} {table:24} строк {b[0]}, sum(xg) {b[3]}, md5 {b[4]}", a == b)

    print("\n== ограничения действуют в восстановленной базе (нарушающие вставки внутри транзакции с откатом) ==")
    template = ("insert into dds.fact_shot select match_date, source_system, {event}, match_id, team_id, player_id, period, "
                "minute, second, shot_type, outcome, is_shootout, is_penalty, is_on_target, is_goal, {xg} "
                "from dds.fact_shot limit 1")
    cases = [
        ("повтор ключа (source_system, event_id)", template.format(event="event_id", xg="xg"), "unique"),
        ("xG вне [0; 1]", template.format(event="gen_random_uuid()", xg="1.5"), "check"),
        ("матч отсутствует в dds.match", template.replace("match_id,", "-1,", 1).format(event="gen_random_uuid()", xg="xg"), "foreign"),
    ]
    for title, sql, expected in cases:
        try:
            dst_cur.execute(sql)
            check(f"{title}: вставка отклонена", False, "вставка прошла")
        except psycopg2.Error as e:
            check(f"{title}: вставка отклонена", expected in str(e).lower() or expected in (e.pgcode or ""),
                  str(e).splitlines()[0])
        dst.rollback()

    print("\nИТОГ:", "все проверки пройдены" if not failures else f"расхождений: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
