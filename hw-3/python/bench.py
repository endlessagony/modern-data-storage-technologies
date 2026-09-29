"""
Измерение двух запросов витрины на четырёх вариантах таблицы фактов (плюс побочный вариант idx_rev).

Для каждого запроса:
  1. ANALYZE всех таблиц - статистика обновляется перед сравнением;
  2. один прогревочный запуск каждого варианта (в результат не входит);
  3. REPEATS повторов; внутри повтора варианты идут по очереди, чтобы дрейф машины действовал на всех одинаково.
     В каждом повторе для каждого варианта:
       - EXPLAIN (ANALYZE, BUFFERS): серверное время, время планирования, cost верхнего узла, буферы, строки;
       - EXPLAIN (ANALYZE, TIMING OFF): серверное время без накладных расходов на замер каждого узла;
       - сам запрос с чтением результата клиентом: время «клиент - сервер - клиент».

Это измерение после прогрева (данные уже в shared_buffers), а не тест холодного диска.
Результаты (папка results): bench_results.json, bench_plans.txt, result_narrow.csv, result_wide.csv.
"""
import csv
import json
import os
import re
import statistics
import time
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
RESULTS_DIR = ROOT / "results"
REPEATS = 9

VARIANTS = [
    ("plain", "dds.fact_shot", "исходная таблица (куча + PK)"),
    ("idx", "dds.fact_shot_idx", "таблица + составной B-tree"),
    ("part", "dds.fact_shot_part", "секции по году, без доп. индексов"),
    ("part_idx", "dds.fact_shot_part_idx", "секции + тот же составной B-tree"),
    ("idx_rev", "dds.fact_shot_idx_rev", "побочный: индекс с team_id на первом месте"),
]
QUERIES = [("narrow", "query_narrow.sql"), ("wide", "query_wide.sql")]


def connect():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"), port=int(os.environ.get("MAIN_PORT", 5440)),
        dbname=os.environ.get("MAIN_DB", "shots"), user="postgres")


def read_query(filename, table):
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    return text.replace("{fact}", table).strip().rstrip(";")


def explain(cur, sql):
    cur.execute("explain (analyze, buffers) " + sql)
    return "\n".join(row[0] for row in cur.fetchall())


def execution_without_timing(cur, sql):
    """Серверное время EXPLAIN ANALYZE без замеров времени по узлам: показывает вклад самой инструментации."""
    cur.execute("explain (analyze, timing off) " + sql)
    text = "\n".join(row[0] for row in cur.fetchall())
    return float(re.search(r"Execution Time: ([\d.]+) ms", text).group(1))


def buffer_count(line, kind):
    found = re.search(rf"{kind}=(\d+)", line)
    return int(found.group(1)) if found else 0


def parse_plan(text):
    first_line = text.splitlines()[0]
    cost = re.search(r"cost=([\d.]+)\.\.([\d.]+) rows=(\d+)", first_line)
    buffers_line = next(line for line in text.splitlines() if "Buffers:" in line)
    scans = re.findall(
        r"(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan) (?:using (\S+) )?on (\S+)", text)
    return {
        "execution_ms": float(re.search(r"Execution Time: ([\d.]+) ms", text).group(1)),
        "planning_ms": float(re.search(r"Planning Time: ([\d.]+) ms", text).group(1)),
        "cost_startup": float(cost.group(1)),
        "cost_total": float(cost.group(2)),
        "rows_estimated": int(cost.group(3)),
        "rows_actual": int(re.search(r"actual time=[\d.]+\.\.[\d.]+ rows=(\d+)", first_line).group(1)),
        "buffers_hit": buffer_count(buffers_line, "hit"),
        "buffers_read": buffer_count(buffers_line, "read"),
        "scans": sorted({f"{kind} on {rel}" + (f" using {idx}" if idx else "") for kind, idx, rel in scans}),
        "relations": sorted({rel for _, _, rel in scans}),
    }


def settings(cur):
    names = ["server_version", "shared_buffers", "work_mem", "effective_cache_size", "random_page_cost",
             "max_parallel_workers_per_gather", "jit", "enable_seqscan", "enable_indexscan",
             "enable_bitmapscan", "enable_partition_pruning", "default_statistics_target"]
    result = {}
    for name in names:
        cur.execute("select current_setting(%s)", (name,))
        result[name] = cur.fetchone()[0]
    return result


def filter_shares(cur):
    cur.execute("""
        select count(*),
               count(*) filter (where not is_shootout),
               count(*) filter (where match_date >= date '2024-06-14' and match_date < date '2024-06-24'),
               count(*) filter (where not is_shootout and match_date >= date '2024-06-14' and match_date < date '2024-06-24'),
               count(*) filter (where match_date >= date '2016-01-01' and match_date < date '2025-01-01'),
               count(*) filter (where not is_shootout and match_date >= date '2016-01-01' and match_date < date '2025-01-01'),
               min(match_date), max(match_date)
        from dds.fact_shot""")
    total, no_so, n_date, n_both, w_date, w_both, dmin, dmax = cur.fetchone()
    return {"rows_total": total, "date_min": str(dmin), "date_max": str(dmax),
            "not_shootout": no_so,
            "narrow_date_only": n_date, "narrow_all_filters": n_both,
            "wide_date_only": w_date, "wide_all_filters": w_both}


def sizes(cur):
    result = {}
    for key, table, _ in VARIANTS:
        cur.execute("""
            select pg_relation_size(%(t)s::regclass), pg_indexes_size(%(t)s::regclass), pg_total_relation_size(%(t)s::regclass)
        """, {"t": table})
        heap, indexes, total = cur.fetchone()
        if key.startswith("part"):   # для секционированной таблицы размеры считаются по секциям
            cur.execute("""
                select coalesce(sum(pg_relation_size(c.oid)), 0), coalesce(sum(pg_indexes_size(c.oid)), 0),
                       coalesce(sum(pg_total_relation_size(c.oid)), 0)
                from pg_inherits i join pg_class c on c.oid = i.inhrelid
                where i.inhparent = %s::regclass""", (table,))
            heap, indexes, total = cur.fetchone()
        result[key] = {"heap_bytes": int(heap), "indexes_bytes": int(indexes), "total_bytes": int(total)}
    return result


def partition_rows(cur):
    cur.execute("""
        select c.relname, pg_get_expr(c.relpartbound, c.oid),
               (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from dds.%I', c.relname), false, true, '')))[1]::text::int
        from pg_inherits i join pg_class c on c.oid = i.inhrelid
        where i.inhparent = 'dds.fact_shot_part'::regclass order by c.relname""")
    return [{"partition": r[0], "bounds": r[1], "rows": r[2]} for r in cur.fetchall()]


def median(values):
    return round(statistics.median(values), 3)


def main():
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()

    out = {"settings": settings(cur), "repeats": REPEATS, "filter_shares": filter_shares(cur),
           "sizes": sizes(cur), "partitions": partition_rows(cur), "runs": {}}
    cur.execute("select correlation, n_distinct from pg_stats where schemaname='dds' and tablename='fact_shot' and attname='match_date'")
    out["match_date_stats"] = dict(zip(("correlation", "n_distinct"), cur.fetchone()))

    plans_file = []
    for qname, filename in QUERIES:
        sqls = {key: read_query(filename, table) for key, table, _ in VARIANTS}
        for _, table, _ in VARIANTS:
            cur.execute(f"analyze {table}")                 # статистика обновлена перед сравнением

        for key in sqls:                                    # прогревочный запуск каждого варианта
            explain(cur, sqls[key])
            cur.execute(sqls[key])
            cur.fetchall()

        server = {key: [] for key in sqls}
        no_timing = {key: [] for key in sqls}
        client = {key: [] for key in sqls}
        last_plan = {}
        rows_of = {}
        # варианты чередуются внутри каждого повтора, чтобы медленный дрейф машины действовал на всех одинаково
        for _ in range(REPEATS):
            for key, sql in sqls.items():
                text = explain(cur, sql)
                server[key].append(parse_plan(text))
                last_plan[key] = text
                no_timing[key].append(execution_without_timing(cur, sql))
                started = time.perf_counter()
                cur.execute(sql)
                rows_of[key] = cur.fetchall()
                client[key].append((time.perf_counter() - started) * 1000)

        for key, table, title in VARIANTS:
            first = server[key][0]
            out["runs"][f"{qname}/{key}"] = {
                "table": table, "title": title, "result_rows": len(rows_of[key]),
                "execution_ms": [s["execution_ms"] for s in server[key]],
                "execution_median_ms": median([s["execution_ms"] for s in server[key]]),
                "execution_timing_off_ms": no_timing[key],
                "execution_timing_off_median_ms": median(no_timing[key]),
                "planning_ms": [s["planning_ms"] for s in server[key]],
                "planning_median_ms": median([s["planning_ms"] for s in server[key]]),
                "client_ms": [round(v, 3) for v in client[key]],
                "client_median_ms": median(client[key]),
                "cost_total": first["cost_total"], "cost_startup": first["cost_startup"],
                "rows_estimated": first["rows_estimated"], "rows_actual": first["rows_actual"],
                "buffers_hit": first["buffers_hit"], "buffers_read": first["buffers_read"],
                "scans": first["scans"], "relations_scanned": len(first["relations"]),
            }
            plans_file.append(f"===== {qname} / {key}: {title} =====\n{sqls[key]};\n\n{last_plan[key]}\n")
            if key == "plain":
                with open(RESULTS_DIR / f"result_{qname}.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, lineterminator="\n")
                    writer.writerow(["source_system", "team_id", "match_date", "shots", "shots_on_target", "goals",
                                     "penalty_goals", "xg", "goals_minus_xg"])
                    writer.writerows(rows_of[key])

    (RESULTS_DIR / "bench_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (RESULTS_DIR / "bench_plans.txt").write_text("\n".join(plans_file), encoding="utf-8")

    lines = [f"PostgreSQL {out['settings']['server_version']}, повторов: {REPEATS} (плюс один прогревочный)"]
    for qname, _ in QUERIES:
        lines.append(f"\n== запрос {qname} ==")
        lines.append(f"{'вариант':9} {'строк':>5} {'exec':>8} {'exec без timing':>16} {'план':>6} {'клиент':>8} "
                     f"{'cost':>9} {'hit/read':>10} {'секций':>6}   (время в мс, медианы)")
        for key, _, _ in VARIANTS:
            r = out["runs"][f"{qname}/{key}"]
            lines.append(f"{key:9} {r['result_rows']:>5} {r['execution_median_ms']:>8} "
                         f"{r['execution_timing_off_median_ms']:>16} {r['planning_median_ms']:>6} {r['client_median_ms']:>8} "
                         f"{r['cost_total']:>9} {str(r['buffers_hit']) + '/' + str(r['buffers_read']):>10} "
                         f"{r['relations_scanned']:>6}")
        for key, _, _ in VARIANTS:
            lines.append(f"  {key:9} exec, мс: {out['runs'][f'{qname}/{key}']['execution_ms']}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
