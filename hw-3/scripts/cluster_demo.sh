#!/usr/bin/env bash
# Сценарий для кластера Patroni: роли, маркер, switchover, отказ записи в реплику, отставание.
# Кластер должен быть запущен (cluster_up.sh). Вывод сохраняется в results/cluster_demo_output.txt.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
cd "$HW3_DIR"

CL="$HW3_HOME/cluster"
CFG="$CL/node1.yml"
DB="$CLUSTER_DB"
node_port() { [ "$1" = node1 ] && echo "$NODE1_PG_PORT" || echo "$NODE2_PG_PORT"; }
node_api()  { [ "$1" = node1 ] && echo "$NODE1_API_PORT" || echo "$NODE2_API_PORT"; }
other()     { [ "$1" = node1 ] && echo node2 || echo node1; }
sql()       { local port=$1; shift; psql -p "$port" -d "$DB" -X "$@"; }
# клиент, который сам находит узел, доступный для записи
client()    { psql "host=127.0.0.1,127.0.0.1 port=$NODE1_PG_PORT,$NODE2_PG_PORT dbname=$DB user=postgres target_session_attrs=read-write" -X "$@"; }
title()     { printf '\n### %s\n' "$*"; }

current_leader() {
    for n in node1 node2; do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$(node_api "$n")/primary")" = 200 ]; then
            echo "$n"; return
        fi
    done
}

show_roles() {
    echo "-- Patroni (patronictl list):"
    patronictl -c "$CFG" list
    echo "-- REST API: /primary отвечает 200 только на лидере, /replica только на реплике:"
    for n in node1 node2; do
        printf '   %s: /primary=%s /replica=%s\n' "$n" \
            "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$(node_api "$n")/primary")" \
            "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$(node_api "$n")/replica")"
    done
    echo "-- SQL: pg_is_in_recovery() на каждом узле (false = принимает запись, true = реплика):"
    for n in node1 node2; do
        printf '   %s (порт %s): ' "$n" "$(node_port "$n")"
        psql -p "$(node_port "$n")" -d postgres -X -Atc "select 'pg_is_in_recovery=' || pg_is_in_recovery() || ', transaction_read_only=' || current_setting('transaction_read_only')"
    done
}

wait_marker() {   # порт, маркер: ждём появления строки на узле
    for _ in $(seq 60); do
        [ "$(sql "$1" -Atc "select count(*) from ops.marker where marker = '$2'")" = 1 ] && return 0
        sleep 0.5
    done
    return 1
}

wait_switchover() {   # ждём, пока новый лидер станет лидером, а бывший - здоровой репликой
    for _ in $(seq 90); do
        if [ "$(current_leader)" = "$1" ] &&
           [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$(node_api "$2")/replica")" = 200 ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# patronictl list показывает данные из DCS, которые узлы обновляют раз в loop_wait (10 с): ждём, пока они устоятся
wait_streaming() {
    for _ in $(seq 60); do
        if curl -s "http://127.0.0.1:$NODE1_API_PORT/cluster" | python3 -c '
import json, sys
members = json.load(sys.stdin)["members"]
replicas = [m for m in members if m["role"] != "leader"]
sys.exit(0 if replicas and all(m.get("state") == "streaming" and m.get("lag") == 0 for m in replicas) else 1)'; then
            return 0
        fi
        sleep 1
    done
    return 1
}

title "0. Версии и настройки кластера"
echo "$(postgres --version) | $(patroni --version) | $("$ETCD_BIN/etcd" --version | head -1)"
patronictl -c "$CFG" show-config | grep -E "ttl|loop_wait|retry_timeout|maximum_lag_on_failover|use_pg_rewind|use_slots|synchronous_mode" || true
wait_streaming || echo "предупреждение: реплика не перешла в streaming"

LEADER=$(current_leader); REPLICA=$(other "$LEADER")
title "1. Роли до всяких действий (лидер определён по Patroni и SQL, а не по имени узла)"
show_roles

title "2. Контрольный срез на лидере $LEADER (порт $(node_port "$LEADER"))"
"$SCRIPTS_DIR/load_data.sh" control "$(node_port "$LEADER")" "$DB" 2>&1 | grep -E "dds\.|stage\."
sql "$(node_port "$LEADER")" -q <<'SQL'
create schema if not exists ops;
create table if not exists ops.marker (
    id         bigserial primary key,
    marker     text not null,
    written_on text not null,
    written_at timestamptz not null default now()
);
SQL

title "3. Маркер: запись на лидере $LEADER, чтение на реплике $REPLICA"
M1="marker-1-$(date +%s)-$RANDOM"
echo "маркер: $M1"
sql "$(node_port "$LEADER")" -Atc "insert into ops.marker (marker, written_on) values ('$M1', '$LEADER') returning id, marker, written_on"
if wait_marker "$(node_port "$REPLICA")" "$M1"; then echo "маркер появился на реплике"; else echo "ОШИБКА: маркер не доехал"; fi
echo "-- чтение на реплике $REPLICA (порт $(node_port "$REPLICA")):"
sql "$(node_port "$REPLICA")" -c "select id, marker, written_on, pg_is_in_recovery() as read_on_replica from ops.marker where marker = '$M1'"
echo "-- контрольный срез на реплике: независимая проверка по CSV"
python "$PY_DIR/independent_check.py" --port "$(node_port "$REPLICA")" --db "$DB" --tables dds.fact_shot | tail -4

title "4. Отставание реплики"
echo "-- на лидере, pg_stat_replication:"
sql "$(node_port "$LEADER")" -c "select application_name, state, sent_lsn, replay_lsn, pg_wal_lsn_diff(sent_lsn, replay_lsn) as replay_lag_bytes, replay_lag from pg_stat_replication"
echo "-- на реплике:"
sql "$(node_port "$REPLICA")" -c "select pg_last_wal_receive_lsn() as receive_lsn, pg_last_wal_replay_lsn() as replay_lsn, pg_last_xact_replay_timestamp() as last_replayed_commit"

title "5. Плановая смена лидера: switchover $LEADER -> $REPLICA"
wait_streaming || echo "предупреждение: реплика не перешла в streaming"
OLD_LEADER=$LEADER; NEW_LEADER=$REPLICA
patronictl -c "$CFG" switchover hw3 --leader "$OLD_LEADER" --candidate "$NEW_LEADER" --force
if wait_switchover "$NEW_LEADER" "$OLD_LEADER"; then echo "switchover завершён"; else echo "ОШИБКА: switchover не завершился"; fi
sleep 3

title "6. Роли после switchover"
show_roles
LEADER=$(current_leader); REPLICA=$(other "$LEADER")

title "7. Старый маркер виден на новом лидере $LEADER"
sql "$(node_port "$LEADER")" -c "select id, marker, written_on, pg_is_in_recovery() as in_recovery from ops.marker where marker = '$M1'"
echo "-- контрольный срез на новом лидере: независимая проверка по CSV"
python "$PY_DIR/independent_check.py" --port "$(node_port "$LEADER")" --db "$DB" --tables dds.fact_shot | tail -3

title "8. Клиент сам выбирает узел, доступный для записи (target_session_attrs=read-write)"
M2="marker-2-$(date +%s)-$RANDOM"
echo "маркер: $M2"
client -c "select inet_server_port() as connected_port, pg_is_in_recovery() as in_recovery, current_setting('transaction_read_only') as read_only"
client -Atc "insert into ops.marker (marker, written_on) values ('$M2', 'client via read-write') returning id, marker"
echo "ожидаемый лидер: $LEADER (порт $(node_port "$LEADER"))"
if wait_marker "$(node_port "$REPLICA")" "$M2"; then echo "новый маркер доехал до реплики $REPLICA"; else echo "ОШИБКА: маркер не доехал"; fi
sql "$(node_port "$REPLICA")" -c "select id, marker, written_on, pg_is_in_recovery() as read_on_replica from ops.marker where marker in ('$M1', '$M2') order by id"

title "9. Обычная запись в реплику $REPLICA отклоняется"
sql "$(node_port "$REPLICA")" -c "insert into ops.marker (marker, written_on) values ('rejected-write', '$REPLICA')" 2>&1 | sed 's/^psql:<stdin>:[0-9]*: //'
echo "-- изменения нет ни на реплике, ни на лидере:"
for n in "$REPLICA" "$LEADER"; do
    printf '   %s: ' "$n"
    sql "$(node_port "$n")" -Atc "select 'строк с маркером rejected-write = ' || count(*) from ops.marker where marker = 'rejected-write'"
done
echo "-- число маркеров на обоих узлах одинаково:"
sql "$(node_port "$LEADER")" -Atc "select 'лидер $LEADER: маркеров ' || count(*) from ops.marker"
sql "$(node_port "$REPLICA")" -Atc "select 'реплика $REPLICA: маркеров ' || count(*) from ops.marker"

title "10. Итоговое состояние"
patronictl -c "$CFG" list
patronictl -c "$CFG" history
