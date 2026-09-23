#!/usr/bin/env bash
# Установка БЕЗ Docker (Ubuntu 24.04 / WSL2, Python 3.11, PostgreSQL 16 уже установлен и запущен на :5432).
# Именно этим способом выполнялись запуски, приведённые в evidence/.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3.11}
# 1. Базы и роли (под суперпользователем postgres)
sudo -u postgres psql -v ON_ERROR_STOP=1 -f docker/init-db.sql || echo "роли/базы уже существуют"
# 2. Airflow 3.1.8 с официальными constraints
$PY -m venv .venv-airflow
.venv-airflow/bin/pip install -q "apache-airflow[postgres]==3.1.8" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.1.8/constraints-3.11.txt"
# 3. dbt в отдельном окружении
$PY -m venv .venv-dbt
.venv-dbt/bin/pip install -q -r requirements/dbt.txt
# 4. Метаданные Airflow
source scripts/local_env.sh
airflow db migrate
echo "Готово. Старт: source scripts/local_env.sh && airflow standalone   (UI: http://localhost:8080)"
