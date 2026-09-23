"""
DAG football_shots_elt: загрузка ударов StatsBomb в PostgreSQL, расчёт в dbt, проверки и публикация.

Порядок задач:
  resolve_slice -> acquire_pipeline_lock -> ingest_raw -> dbt_run_candidate -> dbt_test_candidate
  -> publish -> report_publication; при падении тестов вместо публикации работает diagnose_quality_failure;
  в конце всегда release_pipeline_lock.

Период обработки — это даты матчей [slice_start, slice_end), а не дата запуска.
Если параметры не заданы, берётся data_interval расписания (в ежедневном режиме запуск в 00:00 UTC
19.12.2022 обработает матчи 18.12.2022). Если нет и его, задача падает, а не подставляет «сегодня».

Одновременно выполняется только один запуск: max_active_runs=1 и замок ops.pipeline_lock в базе.
Замок нужен, потому что backfill-запуски max_active_runs не ограничивает (см. REPORT.md, §7).
"""
from __future__ import annotations

import json
import os
import pathlib

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param, get_current_context, setup, task, teardown
from airflow.timetables.trigger import CronTriggerTimetable

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "/opt/project")
DBT_DIR = f"{PROJECT_ROOT}/dbt"
DBT_BIN = os.environ.get("DBT_BIN", "dbt")
PYTHON_BIN = os.environ.get("PYTHON_BIN", "python")
SCENARIOS = sorted(p.stem for p in pathlib.Path(PROJECT_ROOT, "data/input/manifests").glob("*.json")) or ["baseline"]

DBT_VARS = (
    "'{\"slice_start\": \"{{ ti.xcom_pull(task_ids='resolve_slice')['slice_start'] }}\", "
    "\"slice_end\": \"{{ ti.xcom_pull(task_ids='resolve_slice')['slice_end'] }}\", "
    "\"run_id\": \"{{ run_id }}\"}'"
)
DBT_FLAGS = f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR} --target-path target --no-use-colors"


def _pg():
    import psycopg2

    return psycopg2.connect(
        host=os.environ.get("DWH_HOST", "localhost"), port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ.get("DWH_DB", "dwh"), user=os.environ.get("DWH_USER", "dwh"),
        password=os.environ.get("DWH_PASSWORD", "dwh"),
    )


def _print_table(cur, title: str):
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f"--- {title} ({len(rows)} rows)")
    if len(cols) > 10:  # широкие строки печатаем вертикально: «колонка = значение»
        for i, r in enumerate(rows, 1):
            print(f"  [row {i}]")
            for c, v in zip(cols, r):
                print(f"    {c:22s} = {v}")
        return
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))


with DAG(
    dag_id="football_shots_elt",
    description="StatsBomb shots -> PostgreSQL raw -> dbt (stg/ods/dds/mart) -> tests -> publish",
    # По умолчанию — ручной запуск. FOOTBALL_DAG_SCHEDULE=daily включает ежедневный режим:
    # запуск в 00:00 UTC дня D+1 получает data_interval [D, D+1) — обрабатываются матчи дня D.
    # В Airflow 3 просто "@daily" даёт НУЛЕВОЙ интервал (start == end == момент запуска),
    # поэтому интервал задаётся явно через interval=timedelta(days=1).
    schedule=(CronTriggerTimetable("0 0 * * *", timezone="UTC", interval=timedelta(days=1))
              if os.environ.get("FOOTBALL_DAG_SCHEDULE") == "daily" else None),
    start_date=pendulum.datetime(2022, 12, 3, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # конфликтующие запуски сериализуются
    tags=["hw2", "dwh", "dbt"],
    params={
        "scenario": Param("baseline", type="string", enum=SCENARIOS,
                          description="Входной набор (манифест data/input/manifests/<scenario>.json)"),
        "slice_start": Param(None, type=["null", "string"], format="date",
                             description="Начало среза дат матчей (включительно), напр. 2022-12-03. Пусто = data_interval расписания"),
        "slice_end": Param(None, type=["null", "string"], format="date",
                           description="Конец среза (исключительно), напр. 2024-07-15"),
    },
    render_template_as_native_obj=False,
) as dag:

    @task
    def resolve_slice() -> dict:
        ctx = get_current_context()
        p = ctx["params"]
        dis, die = ctx.get("data_interval_start"), ctx.get("data_interval_end")
        if p.get("slice_start") and p.get("slice_end"):
            start, end, how = p["slice_start"], p["slice_end"], "params"
        elif dis is not None and die is not None and dis < die:
            start, end, how = dis.date().isoformat(), die.date().isoformat(), "data_interval"
        else:
            raise ValueError("Срез не задан: укажите slice_start/slice_end или запускайте по расписанию "
                             "(data_interval). Дата запуска вместо даты события не подставляется.")
        if start >= end:
            raise ValueError(f"Пустой срез [{start}, {end})")
        print(f"run_id={ctx['run_id']} logical_date={ctx.get('logical_date')} "
              f"data_interval=[{dis}, {die}) run_type={ctx['dag_run'].run_type}")
        print(f"СРЕЗ ДАТ МАТЧЕЙ (дата события) = [{start}, {end}) источник={how}; сценарий={p['scenario']}")
        return {"slice_start": start, "slice_end": end, "scenario": p["scenario"]}

    @setup
    @task(retries=60, retry_delay=timedelta(seconds=10))
    def acquire_pipeline_lock():
        run_id = get_current_context()["run_id"]
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("""create schema if not exists ops;
                           create table if not exists ops.pipeline_lock (
                               lock_name text primary key, run_id text not null,
                               acquired_at timestamptz not null default now())""")
            cur.execute("""insert into ops.pipeline_lock(lock_name, run_id) values ('football_shots_elt', %s)
                           on conflict (lock_name) do nothing""", (run_id,))
            cur.execute("select run_id, acquired_at from ops.pipeline_lock where lock_name = 'football_shots_elt'")
            holder, since = cur.fetchone()
        if holder != run_id:
            raise RuntimeError(f"DWH занят запуском {holder} (с {since}); повтор через 10 с")
        print(f"lock ops.pipeline_lock захвачен запуском {run_id}")

    @teardown
    @task
    def release_pipeline_lock():
        run_id = get_current_context()["run_id"]
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("delete from ops.pipeline_lock where lock_name = 'football_shots_elt' and run_id = %s", (run_id,))
            print(f"lock освобождён: {cur.rowcount} (run_id={run_id})")

    ingest_raw = BashOperator(
        task_id="ingest_raw",
        bash_command=f"{PYTHON_BIN} {PROJECT_ROOT}/loader/load_raw.py "
                     "--scenario {{ params.scenario }} --run-id '{{ run_id }}'",
    )

    dbt_run_candidate = BashOperator(
        task_id="dbt_run_candidate",
        bash_command=f"{DBT_BIN} run {DBT_FLAGS} --vars {DBT_VARS}",
    )

    dbt_test_candidate = BashOperator(
        task_id="dbt_test_candidate",
        bash_command=f"{DBT_BIN} test {DBT_FLAGS} --store-failures --vars {DBT_VARS}",
    )

    publish = BashOperator(
        task_id="publish",
        bash_command=(
            f"{PYTHON_BIN} {PROJECT_ROOT}/loader/publish.py "
            "--slice-start {{ ti.xcom_pull(task_ids='resolve_slice')['slice_start'] }} "
            "--slice-end {{ ti.xcom_pull(task_ids='resolve_slice')['slice_end'] }} "
            "--run-id '{{ run_id }}' --scenario {{ params.scenario }}"
        ),
    )

    @task
    def report_publication(slice_: dict):
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("""select publication_id, run_id, scenario, slice_start, slice_end, rows_published, checksum, published_at
                           from publish.publication_log order by publication_id desc limit 3""")
            _print_table(cur, "publish.publication_log (последние)")
            cur.execute("""select match_date, team_name, manager_name, stage_name, opponent_name, team_score,
                                  shots, shots_on_target, goals, xg, goals_minus_xg
                           from publish.team_day_shots
                           where match_date >= %s and match_date < %s
                           order by match_date desc, team_name limit 12""",
                        (slice_["slice_start"], slice_["slice_end"]))
            _print_table(cur, "publish.team_day_shots (последние дни среза)")

    @task(trigger_rule="one_failed")
    def diagnose_quality_failure():
        """Выполняется только если упали проверки: печатает упавшие тесты и строки-нарушители,
        затем показывает, что опубликованная витрина осталась прежней."""
        rr = pathlib.Path(DBT_DIR, "target", "run_results.json")
        failed = []
        if rr.exists():
            for r in json.loads(rr.read_text())["results"]:
                if r["status"] in ("fail", "error"):
                    failed.append(r)
        with _pg() as conn, conn.cursor() as cur:
            for r in failed:
                name = r["unique_id"].split(".")[2]
                print(f"FAILED TEST: {name}  status={r['status']}  failures={r.get('failures')}")
                rel = r.get("relation_name")
                if rel:
                    cur.execute(f"select * from {rel} limit 10")
                    _print_table(cur, f"строки-нарушители из {rel}")
            cur.execute("""select publication_id, run_id, scenario, rows_published, checksum, published_at
                           from publish.publication_log order by publication_id desc limit 1""")
            _print_table(cur, "ПОСЛЕДНЯЯ УСПЕШНАЯ ПУБЛИКАЦИЯ (не изменилась)")
        if not failed:
            print("run_results.json не содержит упавших тестов — ошибка на другом шаге, см. его лог")

    s = resolve_slice()
    lock = acquire_pipeline_lock()
    unlock = release_pipeline_lock()
    report = report_publication(s)
    diag = diagnose_quality_failure()
    s >> lock >> ingest_raw >> dbt_run_candidate >> dbt_test_candidate >> publish >> report
    dbt_test_candidate >> diag
    [report, diag] >> unlock
    lock >> unlock  # teardown привязан к setup: выполняется всегда и не влияет на итоговый статус запуска
