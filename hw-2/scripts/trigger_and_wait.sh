#!/usr/bin/env bash
# Запуск DAG с явным сценарием и срезом и ожидание завершения.
# Использование: scripts/trigger_and_wait.sh <run_id> <scenario> [slice_start] [slice_end]
set -euo pipefail
RUN_ID="$1"; SCENARIO="$2"; START="${3:-2022-12-03}"; END="${4:-2024-07-15}"
airflow dags trigger football_shots_elt --run-id "$RUN_ID" \
  --conf "{\"scenario\": \"$SCENARIO\", \"slice_start\": \"$START\", \"slice_end\": \"$END\"}" >/dev/null 2>&1
echo "triggered run_id=$RUN_ID scenario=$SCENARIO slice=[$START, $END)"
for i in $(seq 1 120); do
  STATE=$(airflow dags list-runs football_shots_elt -o json 2>/dev/null | python3 -c "import json,sys; print(next((r['state'] for r in json.load(sys.stdin) if r['run_id']=='$RUN_ID'),'none'))")
  [[ "$STATE" == "success" || "$STATE" == "failed" ]] && break
  sleep 5
done
echo "DAG RUN $RUN_ID: $STATE"
airflow tasks states-for-dag-run football_shots_elt "$RUN_ID" -o json 2>/dev/null \
  | python3 -c "import json,sys; [print(f\"  {t['task_id']:28s} {t['state']}\") for t in json.load(sys.stdin)]"
