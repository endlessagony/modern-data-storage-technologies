# Общие настройки стенда. Подключается командой: source config/env.sh
HW3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HW3_DIR
CONFIG_DIR="$HW3_DIR/config"
SQL_DIR="$HW3_DIR/sql"
DATA_DIR="$HW3_DIR/data"
PY_DIR="$HW3_DIR/python"
SCRIPTS_DIR="$HW3_DIR/scripts"
RESULTS_DIR="$HW3_DIR/results"

# данные кластеров, логи и вспомогательные бинарники лежат вне папки с домашним заданием
export HW3_HOME="${HW3_HOME:-$HOME/hw3-stand}"
export PG_BIN="${PG_BIN:-/usr/lib/postgresql/16/bin}"
export ETCD_VERSION="3.5.17"
export ETCD_BIN="${ETCD_BIN:-$HW3_HOME/etcd-v$ETCD_VERSION-linux-amd64}"
export VENV="${VENV:-$HW3_HOME/venv}"

# одиночный сервер для измерений, копии и опыта с двумя сессиями
export MAIN_PORT="${MAIN_PORT:-5440}"
export MAIN_DB="shots"

# учебный кластер Patroni: два узла и один etcd
export ETCD_CLIENT_PORT=2379
export ETCD_PEER_PORT=2380
export NODE1_PG_PORT=5501
export NODE2_PG_PORT=5502
export NODE1_API_PORT=8008
export NODE2_API_PORT=8009
export CLUSTER_DB="shots"

export PATH="$PG_BIN:$VENV/bin:$PATH"
export PGHOST=127.0.0.1
export PGUSER=postgres
export PGPASSWORD=postgres
