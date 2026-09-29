"""
Цена оптимизации на записи: вставка тех же 101 тыс. строк в пустые копии таблицы и построение индекса с нуля.
Каждая вставка повторяется REPEATS раз (между повторами таблица очищается), выводятся все значения и медиана.
Внешних ключей в копиях нет, чтобы измерить именно первичный ключ, индекс и секции.
"""
import os
import statistics
import time

import psycopg2

REPEATS = 5
INDEX = "create index {name}_key on scratch.{name} (source_system, match_date, team_id)"
COLUMNS = """(match_date date not null, source_system text not null, event_id uuid not null,
    match_id bigint not null, team_id bigint not null, player_id bigint not null, period smallint not null,
    minute smallint not null, second smallint not null, shot_type text not null, outcome text not null,
    is_shootout boolean not null, is_penalty boolean not null, is_on_target boolean not null,
    is_goal boolean not null, xg numeric(12, 10) not null"""


def create_partitions(cur, parent):
    cur.execute(f"create table scratch.{parent}_old partition of scratch.{parent} "
                f"for values from ('1900-01-01') to ('2015-01-01')")
    for year in range(2015, 2027):
        cur.execute(f"create table scratch.{parent}_{year} partition of scratch.{parent} "
                    f"for values from ('{year}-01-01') to ('{year + 1}-01-01')")


def main():
    conn = psycopg2.connect(host="127.0.0.1", port=int(os.environ.get("MAIN_PORT", 5440)),
                            dbname=os.environ.get("MAIN_DB", "shots"), user="postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("drop schema if exists scratch cascade")
    cur.execute("create schema scratch")

    cur.execute(f"create table scratch.heap {COLUMNS})")
    cur.execute(f"create table scratch.heap_pk {COLUMNS}, primary key (source_system, event_id))")
    cur.execute(f"create table scratch.heap_pk_idx {COLUMNS}, primary key (source_system, event_id))")
    cur.execute(INDEX.format(name="heap_pk_idx"))
    cur.execute(f"create table scratch.part_pk {COLUMNS}, primary key (source_system, event_id, match_date)) "
                f"partition by range (match_date)")
    create_partitions(cur, "part_pk")
    cur.execute(f"create table scratch.part_pk_idx {COLUMNS}, primary key (source_system, event_id, match_date)) "
                f"partition by range (match_date)")
    create_partitions(cur, "part_pk_idx")
    cur.execute(INDEX.format(name="part_pk_idx"))

    print(f"вставка {REPEATS} раз по 101 227 строк из dds.fact_shot, мс")
    print(f"{'таблица':14} {'значения':60} {'медиана':>9}")
    for name, note in [("heap", "куча без ключей"), ("heap_pk", "куча + PK"),
                       ("heap_pk_idx", "куча + PK + составной индекс"), ("part_pk", "секции + PK"),
                       ("part_pk_idx", "секции + PK + составной индекс")]:
        values = []
        for _ in range(REPEATS):
            cur.execute(f"truncate scratch.{name}")
            started = time.perf_counter()
            cur.execute(f"insert into scratch.{name} select * from dds.fact_shot")
            values.append((time.perf_counter() - started) * 1000)
        print(f"{name:14} {str([round(v) for v in values]):60} {round(statistics.median(values)):>9}   {note}")

    values = []
    for _ in range(REPEATS):
        cur.execute("drop index scratch.heap_pk_idx_key")
        started = time.perf_counter()
        cur.execute(INDEX.format(name="heap_pk_idx"))
        values.append((time.perf_counter() - started) * 1000)
    print(f"\nпостроение индекса (source_system, match_date, team_id) с нуля на 101 227 строках, мс: "
          f"{[round(v) for v in values]}, медиана {round(statistics.median(values))}")

    cur.execute("select pg_relation_size('scratch.heap_pk'), pg_relation_size('scratch.heap_pk_idx_key'), "
                "pg_relation_size('scratch.heap_pk_pkey')")
    heap, idx, pkey = cur.fetchone()
    print(f"размеры: куча {heap / 1e6:.1f} МБ, PK {pkey / 1e6:.1f} МБ, составной индекс {idx / 1e6:.1f} МБ")
    cur.execute("drop schema scratch cascade")


if __name__ == "__main__":
    main()
