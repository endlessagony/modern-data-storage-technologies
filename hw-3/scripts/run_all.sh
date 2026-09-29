#!/usr/bin/env bash
# Полный прогон с нуля: окружение, загрузка, варианты таблицы, измерения, проверки, копия и восстановление,
# опыт двух сессий и кластер Patroni. Вывод каждого шага сохраняется в results/*_output.txt.
# Если стенд уже существует, сначала выполните scripts/clean_stand.sh.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"
mkdir -p "$RESULTS_DIR"

out() { tee "$RESULTS_DIR/$1_output.txt"; }

"$SCRIPTS_DIR/setup_env.sh" 2>&1 | out setup
"$SCRIPTS_DIR/start_pg.sh"
"$SCRIPTS_DIR/load_data.sh" 2>&1 | out load
"$SCRIPTS_DIR/build_variants.sh" 2>&1 | out build
"$SCRIPTS_DIR/versions.sh" 2>&1 | out versions
"$SCRIPTS_DIR/partitions_check.sh" 2>&1 | out partitions
python "$PY_DIR/check_equal.py" 2>&1 | out equality
python "$PY_DIR/independent_check.py" 2>&1 | out independent
python "$PY_DIR/bench.py" 2>&1 | out bench
python "$PY_DIR/write_cost.py" 2>&1 | out write_cost
"$SCRIPTS_DIR/random_page_cost_check.sh" 2>&1 | out random_page_cost
"$SCRIPTS_DIR/backup_restore.sh" 2>&1 | out backup
python "$PY_DIR/mvcc_two_sessions.py" 2>&1 | out mvcc

"$SCRIPTS_DIR/cluster_up.sh" 2>&1 | out cluster_up
"$SCRIPTS_DIR/cluster_demo.sh" 2>&1 | out cluster_demo
echo "готово; остановить стенд с сохранением данных: scripts/stop_all.sh"
