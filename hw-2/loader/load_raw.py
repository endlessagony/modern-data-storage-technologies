"""
Загрузка входных файлов в слой raw без каких-либо преобразований.

Какие файлы загружать, задаёт манифест сценария (data/input/manifests/<scenario>.json).
- Каждый файл — отдельная загрузка (партия) в raw.batches, с sha256 содержимого.
- Файл, который уже загружен с тем же содержимым, повторно не загружается, поэтому повтор ничего не меняет.
- Загрузки, которых нет в манифесте, удаляются: так перед каждым опытом легко вернуться к исходному состоянию.
- Порядок файлов в манифесте сохраняется (batch_seq); dbt использует его, когда версии записей совпадают.

Всё выполняется в одной транзакции под advisory-lock, поэтому два запуска не мешают друг другу.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys

import psycopg2
from psycopg2.extras import Json, execute_values

ROOT = pathlib.Path(os.environ.get("PROJECT_ROOT", pathlib.Path(__file__).resolve().parents[1]))
INPUT_DIR = ROOT / "data" / "input"
LOCK_ID = 20260924  # общий ключ advisory-lock для загрузки и публикации

DDL = """
create schema if not exists raw;
create table if not exists raw.batches (
    batch_id      bigserial primary key,
    batch_seq     int         not null,
    scenario      text        not null,
    source_system text        not null,
    entity        text        not null check (entity in ('matches','shots')),
    file_path     text        not null,
    file_sha256   text        not null,
    row_count     int         not null,
    run_id        text,
    loaded_at     timestamptz not null default now(),
    unique (source_system, entity, file_path, file_sha256)
);
create table if not exists raw.matches (
    batch_id      bigint not null references raw.batches(batch_id) on delete cascade,
    line_no       int    not null,
    source_system text   not null,
    envelope      jsonb  not null,
    payload       jsonb  not null,
    loaded_at     timestamptz not null default now(),
    primary key (batch_id, line_no)
);
create table if not exists raw.shots (
    batch_id      bigint not null references raw.batches(batch_id) on delete cascade,
    line_no       int    not null,
    source_system text   not null,
    envelope      jsonb  not null,
    payload       jsonb  not null,
    loaded_at     timestamptz not null default now(),
    primary key (batch_id, line_no)
);
"""


def dsn():
    return dict(host=os.environ.get("DWH_HOST", "localhost"),
                port=int(os.environ.get("DWH_PORT", "5432")),
                dbname=os.environ.get("DWH_DB", "dwh"),
                user=os.environ.get("DWH_USER", "dwh"),
                password=os.environ.get("DWH_PASSWORD", "dwh"))


def read_manifest(scenario: str) -> dict:
    path = INPUT_DIR / "manifests" / f"{scenario}.json"
    if not path.exists():
        sys.exit(f"Нет манифеста сценария {scenario}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="baseline")
    ap.add_argument("--run-id", default="manual")
    args = ap.parse_args()
    manifest = read_manifest(args.scenario)

    conn = psycopg2.connect(**dsn())
    conn.autocommit = False
    with conn, conn.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(%s)", (LOCK_ID,))
        cur.execute(DDL)
        keep_ids = []
        for seq, f in enumerate(manifest["files"], start=1):
            fpath = INPUT_DIR / f["path"]
            body = fpath.read_bytes()
            sha = hashlib.sha256(body).hexdigest()
            cur.execute("""select batch_id from raw.batches
                           where source_system=%s and entity=%s and file_path=%s and file_sha256=%s""",
                        (f["source_system"], f["entity"], f["path"], sha))
            row = cur.fetchone()
            if row:
                batch_id = row[0]
                cur.execute("update raw.batches set batch_seq=%s, scenario=%s where batch_id=%s",
                            (seq, args.scenario, batch_id))
                print(f"[skip]  {f['path']} sha256={sha[:12]} уже в raw (batch_id={batch_id})")
            else:
                lines = [l for l in body.decode("utf-8").splitlines() if l.strip()]
                cur.execute("""insert into raw.batches(batch_seq, scenario, source_system, entity, file_path,
                                                       file_sha256, row_count, run_id)
                               values (%s,%s,%s,%s,%s,%s,%s,%s) returning batch_id""",
                            (seq, args.scenario, f["source_system"], f["entity"], f["path"], sha,
                             len(lines), args.run_id))
                batch_id = cur.fetchone()[0]
                rows = []
                for i, line in enumerate(lines, start=1):
                    obj = json.loads(line)
                    rows.append((batch_id, i, f["source_system"], Json(obj.get("_source", {})),
                                 Json(obj["record"])))
                execute_values(cur, f"insert into raw.{f['entity']}(batch_id,line_no,source_system,envelope,payload) values %s",
                               rows, page_size=500)
                print(f"[load]  {f['path']} sha256={sha[:12]} rows={len(rows)} batch_id={batch_id}")
            keep_ids.append(batch_id)
        cur.execute("delete from raw.batches where not (batch_id = any(%s)) returning file_path", (keep_ids,))
        for (p,) in cur.fetchall():
            print(f"[drop]  {p}: нет в манифесте сценария {args.scenario}")
        cur.execute("""select entity, source_system, count(*) from (
                          select 'matches' entity, source_system from raw.matches
                          union all select 'shots', source_system from raw.shots) t
                       group by 1,2 order by 1,2""")
        for e, s, n in cur.fetchall():
            print(f"[raw]   {e:8s} {s:14s} rows={n}")
    conn.close()


if __name__ == "__main__":
    main()
