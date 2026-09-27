"""Шаг 1. Загрузка CSV-файла в объектное хранилище S3 (MinIO).

Запуск (внутри контейнера spark):
    docker compose exec spark spark-submit /scripts/01_upload_csv.py /data/events_demo.csv

Скрипт загружает локальный CSV в бакет raw по ключу events/2026/events.csv
и выводит список объектов с размерами.
"""

import os
import sys

import boto3

ENDPOINT = "http://minio:9000"
ACCESS_KEY = "admin"
SECRET_KEY = "hse2026minio"
BUCKET = "raw"
S3_KEY = "events/2026/events.csv"


def main():
    local_path = sys.argv[1] if len(sys.argv) > 1 else "/data/events_demo.csv"
    if not os.path.exists(local_path):
        sys.exit(f"Файл не найден: {local_path}. Сначала запустите generate_dataset.py")

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

    size_mb = os.path.getsize(local_path) / 1024 / 1024
    print(f"Загружаем {local_path} ({size_mb:.1f} МиБ) -> s3://{BUCKET}/{S3_KEY} ...")
    s3.upload_file(local_path, BUCKET, S3_KEY)

    print("\nОбъекты в бакете raw:")
    for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []):
        print(f"  s3://{BUCKET}/{obj['Key']}  {obj['Size'] / 1024 / 1024:.1f} МиБ")


if __name__ == "__main__":
    main()
