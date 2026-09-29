#!/usr/bin/env bash
# Секции: границы, распределение строк, края интервала и то, какие секции остаются в планах запросов.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"
run() { psql -p "$MAIN_PORT" -d "$MAIN_DB" -X "$@"; }

run -f "$SQL_DIR/partitions_check.sql"

plan_of() { { echo "explain (costs off)"; sed "s/{fact}/$1/" "$SQL_DIR/query_$2.sql"; } | run -f -; }

for table in dds.fact_shot_part dds.fact_shot_part_idx; do
    for name in narrow wide; do
        echo
        echo "== план без стоимости: запрос $name, таблица $table =="
        plan_of "$table" "$name" | grep -E "Scan|Append"
        n=$(plan_of "$table" "$name" | sed -nE 's/.* on (fact_shot_part[a-z_0-9]*) .*/\1/p' | sort -u | wc -l)
        echo "секций в плане: $n из 13"
    done
done
