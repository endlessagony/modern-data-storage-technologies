#!/usr/bin/env bash
# Поднимает учебный кластер: один etcd и два узла Patroni (node1, node2).
# Данные остаются в $HW3_HOME/cluster; повторный запуск продолжает с тем же состоянием.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"

CL="$HW3_HOME/cluster"
mkdir -p "$CL"

render_config() {   # имя узла, порт PostgreSQL, порт REST API
    sed -e "s#@NAME@#$1#" -e "s#@PG_PORT@#$2#" -e "s#@API_PORT@#$3#" \
        -e "s#@ETCD_PORT@#$ETCD_CLIENT_PORT#" -e "s#@DATA_DIR@#$CL/$1-data#" \
        -e "s#@PG_BIN@#$PG_BIN#" -e "s#@SOCKET_DIR@#$CL#" -e "s#@PGPASS@#$CL/$1.pgpass#" \
        "$CONFIG_DIR/patroni_template.yml" > "$CL/$1.yml"
}

start_etcd() {
    if [ -f "$CL/etcd.pid" ] && kill -0 "$(cat "$CL/etcd.pid")" 2>/dev/null; then return; fi
    nohup "$ETCD_BIN/etcd" --name hw3 --data-dir "$CL/etcd-data" \
        --listen-client-urls "http://127.0.0.1:$ETCD_CLIENT_PORT" \
        --advertise-client-urls "http://127.0.0.1:$ETCD_CLIENT_PORT" \
        --listen-peer-urls "http://127.0.0.1:$ETCD_PEER_PORT" \
        --initial-advertise-peer-urls "http://127.0.0.1:$ETCD_PEER_PORT" \
        --initial-cluster "hw3=http://127.0.0.1:$ETCD_PEER_PORT" \
        > "$CL/etcd.log" 2>&1 &
    echo $! > "$CL/etcd.pid"
    for _ in $(seq 30); do
        "$ETCD_BIN/etcdctl" --endpoints "127.0.0.1:$ETCD_CLIENT_PORT" endpoint health >/dev/null 2>&1 && return
        sleep 1
    done
    echo "etcd не поднялся, см. $CL/etcd.log" >&2; exit 1
}

start_node() {
    local name=$1
    if [ -f "$CL/$name.pid" ] && kill -0 "$(cat "$CL/$name.pid")" 2>/dev/null; then return; fi
    nohup patroni "$CL/$name.yml" > "$CL/$name.log" 2>&1 &
    echo $! > "$CL/$name.pid"
}

wait_api() {   # порт REST API, ожидаемое состояние роли (primary|replica)
    for _ in $(seq 90); do
        if curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/$2" | grep -q 200; then return 0; fi
        sleep 1
    done
    echo "узел на порту $1 не стал $2" >&2; return 1
}

render_config node1 "$NODE1_PG_PORT" "$NODE1_API_PORT"
render_config node2 "$NODE2_PG_PORT" "$NODE2_API_PORT"

start_etcd
# первым стартует node1: при первом запуске он инициализирует кластер, node2 клонирует его
if [ ! -d "$CL/node1-data" ] && [ ! -d "$CL/node2-data" ]; then
    start_node node1
    wait_api "$NODE1_API_PORT" primary
    start_node node2
else
    start_node node1
    start_node node2
fi
for _ in $(seq 90); do
    n=$(curl -s "http://127.0.0.1:$NODE1_API_PORT/cluster" | python3 -c \
        'import sys,json; print(len(json.load(sys.stdin)["members"]))' 2>/dev/null || echo 0)
    [ "$n" = "2" ] && break
    sleep 1
done
sleep 5
patronictl -c "$CL/node1.yml" list
