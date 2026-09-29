#!/usr/bin/env bash
# Полностью удаляет данные стенда (одиночный сервер, кластер, копию) для прогона с нуля.
# Файлы домашнего задания не затрагиваются.
cd "$(dirname "${BASH_SOURCE[0]}")"
source ../config/env.sh
./stop_all.sh || true
rm -rf "$HW3_HOME/pgmain" "$HW3_HOME/cluster" "$HW3_HOME/backup" "$HW3_HOME/pgmain.log"
echo "данные стенда удалены: $HW3_HOME"
