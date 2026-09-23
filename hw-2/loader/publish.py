"""
Публикация витрины для потребителя. Запускается только после успешных тестов dbt.

Кандидат (mart.mart_team_day_shots) dbt пересобирает при каждом запуске, даже неудачном.
Потребитель же читает publish.team_day_shots (через view publish.v_team_day_shots), и меняется
она только здесь:
- сначала проверяется, что кандидат построен этим же запуском и за тот же период;
- затем строки периода заменяются целиком (delete + insert) в одной транзакции, поэтому повтор
  даёт тот же результат, а частичной публикации не бывает;
- каждая публикация записывается в publish.publication_log с контрольной суммой.
"""
import argparse
import os
import sys

import psycopg2

LOCK_ID = 20260924
COLS = ["match_date", "date_key", "source_system", "team_id", "team_name", "manager_name",
        "competition_name", "stage_name", "match_id", "opponent_name", "team_score", "shots",
        "shots_on_target", "goals", "penalty_goals", "xg", "goals_minus_xg"]

DDL = """
create schema if not exists publish;
create table if not exists publish.team_day_shots (
    match_date date not null, date_key int not null, source_system text not null, team_id bigint not null,
    team_name text, manager_name text, competition_name text, stage_name text, match_id bigint,
    opponent_name text, team_score int, shots int, shots_on_target int, goals int, penalty_goals int,
    xg numeric(12,4), goals_minus_xg numeric(12,4),
    published_run_id text not null, published_at timestamptz not null,
    primary key (source_system, team_id, match_date)
);
create table if not exists publish.publication_log (
    publication_id bigserial primary key,
    run_id text not null, scenario text, slice_start date not null, slice_end date not null,
    rows_published int not null, checksum text not null, published_at timestamptz not null default now()
);
create or replace view publish.v_team_day_shots as
select p.*, (select max(published_at) from publish.publication_log) as last_successful_publication
from publish.team_day_shots p;
"""

CHECKSUM_SQL = """
select count(*), coalesce(md5(string_agg(concat_ws('|', {cols}), E'\\n' order by source_system, team_id, match_date)), 'empty')
from publish.team_day_shots where match_date >= %s and match_date < %s
""".format(cols=", ".join(COLS))


def dsn():
    return dict(host=os.environ.get("DWH_HOST", "localhost"), port=int(os.environ.get("DWH_PORT", "5432")),
                dbname=os.environ.get("DWH_DB", "dwh"), user=os.environ.get("DWH_USER", "dwh"),
                password=os.environ.get("DWH_PASSWORD", "dwh"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice-start", required=True)
    ap.add_argument("--slice-end", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--scenario", default="")
    a = ap.parse_args()

    conn = psycopg2.connect(**dsn())
    with conn, conn.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(%s)", (LOCK_ID,))
        cur.execute(DDL)
        cur.execute("select distinct slice_start::text, slice_end::text, run_id from mart.mart_team_day_shots")
        cands = cur.fetchall()
        if cands and cands != [(a.slice_start, a.slice_end, a.run_id)]:
            sys.exit(f"Кандидат построен для {cands}, а публикуется {(a.slice_start, a.slice_end, a.run_id)} — отказ")
        cur.execute("delete from publish.team_day_shots where match_date >= %s and match_date < %s",
                    (a.slice_start, a.slice_end))
        deleted = cur.rowcount
        cur.execute(f"""insert into publish.team_day_shots ({", ".join(COLS)}, published_run_id, published_at)
                        select {", ".join(COLS)}, %s, now() from mart.mart_team_day_shots""", (a.run_id,))
        inserted = cur.rowcount
        cur.execute(CHECKSUM_SQL, (a.slice_start, a.slice_end))
        n, checksum = cur.fetchone()
        cur.execute("""insert into publish.publication_log(run_id, scenario, slice_start, slice_end, rows_published, checksum)
                       values (%s,%s,%s,%s,%s,%s)""", (a.run_id, a.scenario, a.slice_start, a.slice_end, n, checksum))
        print(f"published slice [{a.slice_start}, {a.slice_end}) run_id={a.run_id}: "
              f"replaced {deleted} -> {inserted} rows, checksum={checksum}")
    conn.close()


if __name__ == "__main__":
    main()
