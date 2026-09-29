#!/usr/bin/env bash
# Останавливает узлы Patroni (вместе с их PostgreSQL) и etcd. Данные сохраняются.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
CL="$HW3_HOME/cluster"

for name in node2 node1 etcd; do
    if [ -f "$CL/$name.pid" ] && kill -0 "$(cat "$CL/$name.pid")" 2>/dev/null; then
        kill -TERM "$(cat "$CL/$name.pid")"
        while kill -0 "$(cat "$CL/$name.pid")" 2>/dev/null; do sleep 1; done
    fi
    rm -f "$CL/$name.pid"
done
echo "кластер остановлен, данные в $CL"
