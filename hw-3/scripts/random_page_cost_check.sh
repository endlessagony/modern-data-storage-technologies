#!/usr/bin/env bash
# Широкий запрос на таблице с индексом при двух значениях random_page_cost: показывает, что выбор между
# Seq Scan и Index Scan определяется стоимостью случайного чтения, а индекс не заставляют работать принудительно.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"

for cost in 4 1.1; do
    echo "== random_page_cost = $cost (стенд использует 1.1; 4 это значение PostgreSQL по умолчанию) =="
    { echo "set random_page_cost = $cost;"
      echo "explain (analyze, buffers, timing off)"
      sed "s/{fact}/dds.fact_shot_idx/" "$SQL_DIR/query_wide.sql"; } \
        | psql -p "$MAIN_PORT" -d "$MAIN_DB" -X -f - | grep -E "Scan|Aggregate|Sort Key"
    echo
done
