# Переменные окружения для запуска БЕЗ Docker (Linux / WSL2). Использование: source scripts/local_env.sh
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow_hw2}"
export AIRFLOW__CORE__DAGS_FOLDER="$PROJECT_ROOT/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@127.0.0.1:5432/airflow
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
export AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True
export AIRFLOW__CORE__DEFAULT_TIMEZONE=utc
export AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL=15
export DBT_BIN="$PROJECT_ROOT/.venv-dbt/bin/dbt"
export PYTHON_BIN="$PROJECT_ROOT/.venv-airflow/bin/python"
export DWH_HOST=127.0.0.1 DWH_PORT=5432 DWH_DB=dwh DWH_USER=dwh DWH_PASSWORD=dwh
export PGHOST=127.0.0.1 PGUSER=dwh PGDATABASE=dwh PGPASSWORD=dwh
export PATH="$PROJECT_ROOT/.venv-airflow/bin:$PATH"
