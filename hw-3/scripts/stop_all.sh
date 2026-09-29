#!/usr/bin/env bash
# Останавливает одиночный сервер и кластер Patroni. Данные сохраняются, повторный запуск: start_pg.sh и cluster_up.sh.
cd "$(dirname "${BASH_SOURCE[0]}")"
./cluster_down.sh
./stop_pg.sh
