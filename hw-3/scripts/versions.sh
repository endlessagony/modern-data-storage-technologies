#!/usr/bin/env bash
# Печатает версии программ, ресурсы машины и настройки сервера, на которых сняты измерения.
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"

echo "ОС:          $(. /etc/os-release && echo "$PRETTY_NAME"), ядро $(uname -r)"
echo "Процессор:   $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs), логических ядер: $(nproc)"
echo "Память:      $(free -m | awk '/Mem:/ {print $2 " МБ всего"}')"
echo "Диск:        $(df -h "$HW3_HOME" | awk 'NR==2 {print $2 " всего, файловая система " $1}')"
echo "PostgreSQL:  $(postgres --version)"
echo "Клиент:      $(psql --version)"
echo "Patroni:     $(patroni --version)"
echo "etcd:        $("$ETCD_BIN/etcd" --version | head -1)"
echo "Python:      $(python --version), psycopg2 $(python -c 'import psycopg2; print(psycopg2.__version__)')"
echo "Источник:    StatsBomb Open Data, коммит $(python -c "import json; print(json.load(open('$DATA_DIR/source_manifest.json'))['commit'])")"
echo
echo "Настройки одиночного сервера (порт $MAIN_PORT):"
psql -p "$MAIN_PORT" -d "$MAIN_DB" -Atc "
    select '  ' || name || ' = ' || setting || coalesce(unit, '')
    from pg_settings
    where name in ('shared_buffers', 'work_mem', 'effective_cache_size', 'maintenance_work_mem',
                   'random_page_cost', 'seq_page_cost', 'max_parallel_workers_per_gather', 'jit',
                   'default_statistics_target', 'enable_seqscan', 'enable_partition_pruning', 'fsync',
                   'TimeZone')
    order by name"
