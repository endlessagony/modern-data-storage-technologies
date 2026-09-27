"""Шаг 1 (ДЗ). Загрузка исходных данных Open-Meteo в S3-хранилище (MinIO).

Запуск (внутри контейнера spark, из infra/):
    docker compose exec spark spark-submit /scripts/hw01/upload_raw.py

Перед запуском на хосте должен быть выполнен fetch_weather.py: скрипт
загружает то, что он положил в data/hw01/. Загружаются исходные JSON по
каждому городу без изменений и собранный табличный CSV. Ничего не
редактируется вручную.
"""

import os

import boto3

ENDPOINT = "http://minio:9000"
ACCESS_KEY = "admin"
SECRET_KEY = "hse2026minio"
BUCKET = "raw"

STUDENT = "naermishov"
DATASET = "weather"
INGESTION_DATE = "2026-09-27"
PREFIX = f"{STUDENT}/{DATASET}/ingestion_date={INGESTION_DATE}"

LOCAL_JSON_DIR = "/data/hw01/raw_json"
LOCAL_CSV = "/data/hw01/weather.csv"


def upload_file(s3, local_path, key):
    size_mb = os.path.getsize(local_path) / 1024 / 1024
    print(f"{local_path} ({size_mb:.2f} МиБ) -> s3://{BUCKET}/{key}")
    s3.upload_file(local_path, BUCKET, key)


def main():
    if not os.path.isdir(LOCAL_JSON_DIR) or not os.path.exists(LOCAL_CSV):
        raise SystemExit(
            "Нет данных в /data/hw01. Сначала на хосте (не в контейнере) "
            "выполните: python3 scripts/hw01/fetch_weather.py"
        )

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if BUCKET not in buckets:
        s3.create_bucket(Bucket=BUCKET)
        print(f"Создан бакет: {BUCKET}")

    for name in sorted(os.listdir(LOCAL_JSON_DIR)):
        local = os.path.join(LOCAL_JSON_DIR, name)
        upload_file(s3, local, f"{PREFIX}/raw_json/{name}")

    upload_file(s3, LOCAL_CSV, f"{PREFIX}/weather.csv")

    print("\nОбъекты по префиксу:")
    for obj in s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX).get("Contents", []):
        print(f"  s3://{BUCKET}/{obj['Key']}  {obj['Size'] / 1024 / 1024:.3f} МиБ")


if __name__ == "__main__":
    main()
