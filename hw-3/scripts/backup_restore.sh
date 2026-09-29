#!/usr/bin/env bash
# Логическая копия базы с витриной (pg_dump, формат custom) и восстановление в другую базу.
# Исходная база остаётся нетронутой. Файл копии лежит в $HW3_HOME/backup и в отчёт не попадает.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"

export PGOPTIONS="-c client_min_messages=warning"
BACKUP_DIR="$HW3_HOME/backup"
DUMP="$BACKUP_DIR/shots.dump"
RESTORED_DB="shots_restored"
mkdir -p "$BACKUP_DIR"

echo "### Версии утилит"
pg_dump --version
pg_restore --version

echo
echo "### 1. Копия: формат custom (-Fc), сжатие 6, вывод в файл средствами утилиты (-f)"
echo "команда: pg_dump -p $MAIN_PORT -d $MAIN_DB -Fc -Z 6 -f $DUMP"
pg_dump -p "$MAIN_PORT" -d "$MAIN_DB" -Fc -Z 6 -f "$DUMP"
echo "код возврата pg_dump: $?"
ls -l "$DUMP" | awk '{print "размер файла копии, байт: " $5}'
echo "pg_restore --list читает оглавление файла без записи в базу:"
pg_restore --list "$DUMP" | grep -c -E "TABLE |INDEX |CONSTRAINT |FK CONSTRAINT " | sed 's/^/  объектов таблиц, индексов и ограничений в оглавлении: /'

echo
echo "### 2. Восстановление в новую базу $RESTORED_DB"
psql -p "$MAIN_PORT" -d postgres -q -c "drop database if exists $RESTORED_DB" -c "create database $RESTORED_DB"
echo "команда: pg_restore -p $MAIN_PORT -d $RESTORED_DB --exit-on-error --no-owner $DUMP"
pg_restore -p "$MAIN_PORT" -d "$RESTORED_DB" --exit-on-error --no-owner "$DUMP"
echo "код возврата pg_restore: $?  (0 = все команды выполнены без ошибок)"
psql -p "$MAIN_PORT" -d "$RESTORED_DB" -q -c "analyze"

echo
echo "### 3. Проверки восстановленной базы"
python "$PY_DIR/verify_restore.py" --source "$MAIN_DB" --restored "$RESTORED_DB" --port "$MAIN_PORT"
echo
echo "### 4. Независимый расчёт контрольного среза по CSV на восстановленной базе"
python "$PY_DIR/independent_check.py" --port "$MAIN_PORT" --db "$RESTORED_DB"
