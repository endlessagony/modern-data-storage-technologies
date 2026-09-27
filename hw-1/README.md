# ДЗ 1 — naermishov — weather

Как повторить работу с чистого стенда. Все команды `docker compose` и
python-скрипты запускаются из `infra/` распакованного `lecture_01_student/`
(на Windows — в Ubuntu/WSL, не в PowerShell). Docker Desktop должен быть
запущен.

**Известная проблема окружения.** В сентябре 2026 MinIO закрыли
бесплатную раздачу: образы `minio/minio` и `minio/mc` пропали и с Docker
Hub, и с Quay.io (401/`repository does not exist`), а прямые бинарники на
`dl.min.io` отдают `410 Gone`. Из-за этого `docker compose up -d` из
исходного `infra/docker-compose.yml` не поднимается вообще. В
`infra/docker-compose.yml` этой сдачи сервис `minio` переключён на
`bitnamilegacy/minio:latest` — независимо поддерживаемую заморозку того же
MinIO, которая пока анонимно скачивается (её же используют другие
проекты, столкнувшиеся с этим отключением). Отдельный контейнер с `mc`
убран целиком: бакеты `raw` и `datalake` создаёт сам образ через
`MINIO_DEFAULT_BUCKETS`, а сервис `minio-init` дополнительно подстраховывает
это скриптом `scripts/init_buckets.py` на `boto3` в уже собранном образе
`spark` — без обращения к внешним реестрам. Если у преподавателя тот же
стенд не поднимается с ошибкой pull для `minio/minio` или `minio/mc` —
дело не в сборке, а в этом внешнем отключении, и это уже исправлено в
данном docker-compose.yml.

## 0. Стенд и учебный пример

Сначала пройти инструкцию `setup_windows.md` (или `setup_macos.md`) из
комплекта и повторить учебный пример семинара один раз — это разобрано в
`homework_01.md`, этап 0. Короткая версия:

```bash
cd infra
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps --all
python3 generate_dataset.py --rows 200000 --out data/events_demo.csv
docker compose exec spark spark-submit /scripts/01_upload_csv.py /data/events_demo.csv
docker compose exec spark spark-submit /scripts/02_csv_to_parquet.py
docker compose exec spark spark-submit /scripts/03_iceberg.py
docker compose exec -T trino trino < trino/scripts/seminar_demo.sql
```

Сохранить `docker compose ps --all` в `evidence/compose-ps.txt`.

## 1. Свой источник — Open-Meteo

Все команды ниже тоже из `infra/`.

```bash
python3 scripts/hw01/fetch_weather.py
```

Скрипт делает 8 запросов к `archive-api.open-meteo.com` (по одному на
город), кладёт исходные JSON-ответы в `data/hw01/raw_json/` и собирает
табличный `data/hw01/weather.csv`. Ожидается порядка 140 000 строк без
заголовка (8 городов × 17544 часа за 2023-2024). Интернет нужен только
на этом шаге.

## 2. Raw в MinIO

```bash
docker compose exec spark spark-submit /scripts/hw01/upload_raw.py
```

Загружает 8 JSON-файлов и `weather.csv` без изменений в бакет `raw`, ключ
`raw/naermishov/weather/ingestion_date=2026-09-27/...`. Вывод скрипта —
список объектов с размерами — сохранить в `evidence/object-listing.txt`.

## 3. Проверки, Parquet, Iceberg

```bash
docker compose exec spark spark-submit /scripts/hw01/pipeline.py
```

Один скрипт: явная схема → проверки качества (accepted/rejected) →
запись в Parquet (`s3://datalake/naermishov/weather/parquet/`, партиции
по `city`) → сравнение CSV/Parquet на одном запросе, 3 замера → создание
`lakehouse.naermishov.weather` двумя порциями (2023 год, потом 2024) →
история snapshots. Весь вывод сохранить в `evidence/spark-result.txt`.
