#!/usr/bin/env bash
# Создаёт варианты таблицы фактов (индекс, секции) и печатает время загрузки и построения индексов.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"
psql -p "$MAIN_PORT" -d "$MAIN_DB" -v ON_ERROR_STOP=1 -f "$SQL_DIR/build_variants.sql"
