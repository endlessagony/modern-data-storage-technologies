#!/usr/bin/env bash
# Создаёт (при первом запуске) и запускает одиночный сервер PostgreSQL на $MAIN_PORT.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"

PGDATA_MAIN="$HW3_HOME/pgmain"

if [ ! -f "$PGDATA_MAIN/PG_VERSION" ]; then
    initdb -D "$PGDATA_MAIN" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8 >/dev/null
    echo "include = 'hw3.conf'" >> "$PGDATA_MAIN/postgresql.conf"
    echo "port = $MAIN_PORT" >> "$PGDATA_MAIN/postgresql.conf"
fi

cp "$CONFIG_DIR/pg_main.conf" "$PGDATA_MAIN/hw3.conf"

if ! pg_ctl -D "$PGDATA_MAIN" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA_MAIN" -l "$HW3_HOME/pgmain.log" -w start
fi
psql -p "$MAIN_PORT" -d postgres -Atc "select 'сервер готов: ' || version()"
