"""Создание бакетов raw и datalake в MinIO.

Замена шага minio-init: официальный образ minio/mc пропал из публичных
реестров (см. README сдачи), поэтому бакеты создаются через boto3 в уже
собранном образе spark вместо отдельного mc-контейнера.
"""

import boto3
from botocore.exceptions import ClientError

ENDPOINT = "http://minio:9000"
ACCESS_KEY = "admin"
SECRET_KEY = "hse2026minio"
BUCKETS = ["raw", "datalake"]


def main():
    s3 = boto3.client(
        "s3", endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
    )
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    for bucket in BUCKETS:
        if bucket in existing:
            print(f"Бакет уже есть: {bucket}")
            continue
        try:
            s3.create_bucket(Bucket=bucket)
            print(f"Создан бакет: {bucket}")
        except ClientError as e:
            raise SystemExit(f"Не удалось создать бакет {bucket}: {e}")
    print("Бакеты raw и datalake готовы")


if __name__ == "__main__":
    main()
