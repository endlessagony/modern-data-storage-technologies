"""Шаг 3. Две записи в учебную Iceberg-таблицу из одного Parquet-набора.

Будущий запуск:
    docker compose exec spark spark-submit /scripts/03_iceberg.py

Первая порция — сентябрь, вторая — оставшийся диапазон. CTAS пишет новые
файлы, а не регистрирует готовые Parquet без копирования. Повторный запуск
заменяет содержимое только учебной lakehouse.dwh.events и добавляет порцию
заново: строки не должны накопиться. История может содержать старые snapshots.
"""

from pyspark.sql import SparkSession, functions as F

TABLE = "lakehouse.dwh.events"
PARQUET_PATH = "s3a://datalake/warehouse/events_parquet"
BOUNDARY = "2026-10-01"


def snapshot_ids(spark):
    return {row.snapshot_id for row in
            spark.sql(f"SELECT snapshot_id FROM {TABLE}.snapshots").collect()}


def main():
    spark = (SparkSession.builder.appName("iceberg-table")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        print("== Проверяем две непересекающиеся порции до записи ==")
        source = spark.read.parquet(PARQUET_PATH)
        before_boundary = F.col("event_date") < F.lit(BOUNDARY).cast("date")
        metrics = source.agg(
            F.count("*").alias("rows"),
            F.countDistinct("event_id").alias("unique_ids"),
            F.sum(F.when(before_boundary, 1).otherwise(0)).alias("first_batch"),
            F.sum(F.when(~before_boundary, 1).otherwise(0)).alias("second_batch"),
            F.sum(F.when(F.col("event_date").isNull()
                         | F.col("event_ts").isNull()
                         | (F.col("event_date") != F.to_date("event_ts")),
                         1).otherwise(0)).alias("bad_dates"),
        ).first()
        if (metrics.rows == 0 or metrics.unique_ids != metrics.rows
                or metrics.bad_dates or not metrics.first_batch
                or not metrics.second_batch
                or metrics.first_batch + metrics.second_batch != metrics.rows):
            raise ValueError(f"Нужны уникальные event_id, согласованные даты "
                             f"и две непустые порции: {metrics.asDict()}")
        print(f"Проверки до записи: {metrics.asDict()}")
        spark.sql("CREATE DATABASE IF NOT EXISTS lakehouse.dwh")
        previous_ids = snapshot_ids(spark) if spark.catalog.tableExists(TABLE) else set()

        print("\n== Запись 1: CTAS первой порции, даты до 2026-10-01 ==")
        spark.sql(f"""
            CREATE OR REPLACE TABLE {TABLE}
            USING iceberg
            PARTITIONED BY (days(event_ts))
            AS SELECT * FROM parquet.`{PARQUET_PATH}`
            WHERE event_date < DATE '{BOUNDARY}'
        """)
        first_count = spark.table(TABLE).count()
        if first_count != metrics.first_batch:
            raise ValueError("Число строк после CTAS не совпало с первой порцией")
        after_first_ids = snapshot_ids(spark)
        print(f"После записи 1: {first_count:,} строк; "
              f"новые snapshots: {sorted(after_first_ids - previous_ids)}")

        print("\n== Запись 2: INSERT второй порции, даты от 2026-10-01 ==")
        spark.sql(f"""
            INSERT INTO {TABLE}
            SELECT * FROM parquet.`{PARQUET_PATH}`
            WHERE event_date >= DATE '{BOUNDARY}'
        """)
        final = spark.table(TABLE).agg(
            F.count("*").alias("rows"),
            F.countDistinct("event_id").alias("unique_ids"),
        ).first()
        if final.rows != metrics.rows or final.unique_ids != metrics.rows:
            raise ValueError(f"Финальные строки/идентификаторы не совпали: {final}")
        after_second_ids = snapshot_ids(spark)
        print(f"После записи 2: {final.rows:,} строк; "
              f"новые snapshots: {sorted(after_second_ids - after_first_ids)}")
        print("Проверка: все строки Parquet сохранены в Iceberg без дублей event_id.")

        print("\n== История: две новые записи; старые snapshots могут сохраниться ==")
        spark.sql(f"""
            SELECT snapshot_id, committed_at, operation, summary['total-records'] AS total_records
            FROM {TABLE}.snapshots ORDER BY committed_at
        """).show(100, truncate=False)
        print("\n== Тот же аналитический вопрос: покупки сентября ==")
        spark.sql(f"""
            SELECT count(*) AS purchase_events, avg(price_rub) AS mean_purchase_price
            FROM {TABLE}
            WHERE event_type = 'purchase'
              AND event_date >= DATE '2026-09-01'
              AND event_date < DATE '2026-10-01'
        """).show(truncate=False)
        print("Вторая порция не меняет сентябрьский результат, "
              "но увеличивает общее число строк.")
        print("\n== Схема из метаданных Iceberg ==")
        spark.sql(f"DESCRIBE TABLE {TABLE}").show(30, truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
