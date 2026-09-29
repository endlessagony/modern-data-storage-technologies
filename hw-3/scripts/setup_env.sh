#!/usr/bin/env bash
# Готовит окружение: PostgreSQL 16 (пакеты Ubuntu 24.04 / WSL2), etcd и виртуальное окружение Python.
# Запускать под обычным пользователем; для apt нужен sudo.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"

mkdir -p "$HW3_HOME"

if [ ! -x "$PG_BIN/postgres" ]; then
    sudo apt-get update
    sudo apt-get install -y postgresql-16 postgresql-client-16 python3-venv curl
fi
# служебный кластер из пакета не нужен: порты 5432 стенд не использует
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet postgresql 2>/dev/null; then
    sudo systemctl disable --now postgresql || true
fi

if [ ! -x "$ETCD_BIN/etcd" ]; then
    curl -fsSL -o "$HW3_HOME/etcd.tar.gz" \
        "https://github.com/etcd-io/etcd/releases/download/v$ETCD_VERSION/etcd-v$ETCD_VERSION-linux-amd64.tar.gz"
    tar -xzf "$HW3_HOME/etcd.tar.gz" -C "$HW3_HOME"
    rm "$HW3_HOME/etcd.tar.gz"
fi

if [ ! -x "$VENV/bin/pip" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r "$CONFIG_DIR/requirements.txt"

echo "PostgreSQL: $("$PG_BIN/postgres" --version)"
echo "etcd:       $("$ETCD_BIN/etcd" --version | head -1)"
echo "Patroni:    $("$VENV/bin/patroni" --version)"
echo "Python:     $("$VENV/bin/python" --version)"
