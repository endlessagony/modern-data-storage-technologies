#!/usr/bin/env bash
# Останавливает одиночный сервер. Данные остаются в $HW3_HOME/pgmain.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config/env.sh"
pg_ctl -D "$HW3_HOME/pgmain" -m fast stop || true
