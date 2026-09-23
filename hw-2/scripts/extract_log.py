"""Печать лога задачи Airflow (JSON-строки) в читаемом виде: scripts/extract_log.py <run_id> <task_id>"""
import json, os, pathlib, sys
home = pathlib.Path(os.environ.get("AIRFLOW_HOME", "/opt/airflow"))
run_id, task_id = sys.argv[1], sys.argv[2]
for f in sorted((home / "logs" / "dag_id=football_shots_elt" / f"run_id={run_id}" / f"task_id={task_id}").glob("attempt=*.log")):
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            print(line); continue
        ev = o.get("event", "")
        lg = o.get("logger", "")
        if lg in ("task.stdout", "task.stderr") or "SubprocessHook" in lg or o.get("level") in ("error", "warning", "critical"):
            print(f"{o.get('timestamp','')[:19]} {o.get('level','')[:5]:5} {ev}")
