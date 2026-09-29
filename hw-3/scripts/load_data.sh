#!/usr/bin/env bash
# Загрузка данных в базу: staging из CSV, затем dds.match и dds.fact_shot.
#   ./load_data.sh                     все удары на одиночный сервер ($MAIN_PORT, база $MAIN_DB)
#   ./load_data.sh control PORT DB     контрольный срез (866 ударов) на указанный узел
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"

mode=${1:-full}
if [ "$mode" = "control" ]; then
    port=$2; db=$3
    shots_cmd="cat "$DATA_DIR/control_shots.csv""; matches_file="$DATA_DIR/control_matches.csv"
else
    port=$MAIN_PORT; db=$MAIN_DB
    shots_cmd="gzip -dc "$DATA_DIR/shots.csv.gz""; matches_file="$DATA_DIR/matches.csv"
fi
psql -p "$port" -d postgres -Atc "select 1 from pg_database where datname = '$db'" | grep -q 1 \
    || createdb -p "$port" "$db"
run() { psql -p "$port" -d "$db" -v ON_ERROR_STOP=1 "$@"; }

run -q -f "$SQL_DIR/ddl_core.sql"
run -c '\timing on' \
    -c "\copy stage.matches from stdin with (format csv, header true)" < "$matches_file"
$shots_cmd | run -c '\timing on' \
    -c "\copy stage.shots (source_system, event_id, match_id, match_date, team_id, team_name, player_id, player_name, period, minute, second, shot_type, outcome, body_part, xg) from stdin with (format csv, header true)"
run -f "$SQL_DIR/load_core.sql"
run -Atc "select 'stage.shots: ' || count(*) from stage.shots union all
          select 'dds.match: ' || count(*) from dds.match union all
          select 'dds.fact_shot: ' || count(*) from dds.fact_shot"
