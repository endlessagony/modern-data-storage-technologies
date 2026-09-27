"""pipeline.py — ДЗ 1: raw (Open-Meteo) -> проверки -> Parquet -> Iceberg.

Источник: Open-Meteo Historical Weather API, погода по 8 городам России
за 2023-2024 год (см. report.md и schema.md в папке сдачи). Запуск из
infra/ после fetch_weather.py и upload_raw.py:

    docker compose exec spark spark-submit /scripts/hw01/pipeline.py

inferSchema не используется, типы заданы явно. У этого набора нет
финансовых полей из учебного примера, поэтому вместо проверок цены/
количества используются проверки физического диапазона: температура,
влажность, осадки, скорость ветра.
"""

import time

from pyspark.sql import SparkSession, functions as F, types as T

STUDENT = "naermishov"
DATASET = "weather"
INGESTION_DATE = "2026-09-27"

CSV_PATH = f"s3a://raw/{STUDENT}/{DATASET}/ingestion_date={INGESTION_DATE}/weather.csv"
PARQUET_PATH = f"s3a://datalake/{STUDENT}/{DATASET}/parquet/"
REJECT_PATH = f"s3a://datalake/{STUDENT}/{DATASET}/rejected/"
TABLE = f"lakehouse.{STUDENT}.{DATASET}"
BOUNDARY = "2024-01-01"

# CSV не хранит типы, поэтому схема задаётся вручную
WEATHER_SCHEMA = T.StructType([
    T.StructField("city", T.StringType()),
    T.StructField("latitude", T.DoubleType()),
    T.StructField("longitude", T.DoubleType()),
    T.StructField("event_ts", T.TimestampType()),
    T.StructField("event_date", T.DateType()),
    T.StructField("temperature_2m", T.DecimalType(5, 2)),
    T.StructField("relative_humidity_2m", T.DecimalType(5, 2)),
    T.StructField("precipitation_mm", T.DecimalType(6, 2)),
    T.StructField("wind_speed_10m", T.DecimalType(6, 2)),
])

# один и тот же вопрос гоняем на CSV, на Parquet и потом на Iceberg-таблице,
# чтобы сравнивать одинаковые данные и один и тот же SQL (аналог сентября
# в учебном примере, только город и месяц свои)
QUERY = """
    SELECT count(*) AS n_rows,
           avg(CAST(temperature_2m AS DECIMAL(18,6))) AS avg_temp_c
    FROM {view}
    WHERE city = 'Москва'
      AND event_date >= DATE '2023-01-01'
      AND event_date < DATE '2023-02-01'
"""


def dir_size_mb(spark, path):
    jvm = spark._jvm
    conf = spark._jsc.hadoopConfiguration()
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(jvm.java.net.URI.create(path), conf)
    summary = fs.getContentSummary(jvm.org.apache.hadoop.fs.Path(path))
    return summary.getLength() / 1024 / 1024


def split_valid(df):
    """Делит датафрейм на (accepted, rejected). rejected несёт reject_reason."""
    required_null = (
        F.col("city").isNull() | (F.trim(F.col("city")) == "")
        | F.col("event_ts").isNull() | F.col("event_date").isNull()
        | F.col("temperature_2m").isNull()
    )
    bad_date = F.col("event_date") != F.to_date("event_ts")
    bad_temp = ~F.col("temperature_2m").between(-55, 45)
    bad_humidity = F.col("relative_humidity_2m").isNotNull() & (
        ~F.col("relative_humidity_2m").between(0, 100)
    )
    bad_precip = F.col("precipitation_mm").isNotNull() & (F.col("precipitation_mm") < 0)
    bad_wind = F.col("wind_speed_10m").isNotNull() & (F.col("wind_speed_10m") < 0)

    checks = [
        (required_null, "missing_required_field"),
        (bad_date, "event_date_mismatch"),
        (bad_temp, "temperature_out_of_range"),
        (bad_humidity, "humidity_out_of_range"),
        (bad_precip, "negative_precipitation"),
        (bad_wind, "negative_wind_speed"),
    ]

    reason = F.lit(None).cast("string")
    is_bad = F.lit(False)
    for cond, label in checks:
        reason = F.when(cond & reason.isNull(), F.lit(label)).otherwise(reason)
        is_bad = is_bad | cond

    key = F.concat_ws("_", "city", F.col("event_ts").cast("string"))
    tagged = df.withColumn("_key", key).withColumn("_is_bad", is_bad).withColumn("_reason", reason)

    # дубликаты ключа (city, event_ts) — отдельная проверка по всей таблице
    dup_keys = [r["_key"] for r in
                tagged.groupBy("_key").count().filter(F.col("count") > 1).collect()]
    if dup_keys:
        is_dup = F.col("_key").isin(dup_keys)
        tagged = tagged.withColumn(
            "_reason", F.when(is_dup & F.col("_reason").isNull(), F.lit("duplicate_key")).otherwise(F.col("_reason"))
        ).withColumn("_is_bad", F.col("_is_bad") | is_dup)

    accepted = tagged.filter(~F.col("_is_bad")).drop("_key", "_is_bad", "_reason")
    rejected = (tagged.filter(F.col("_is_bad"))
                .withColumnRenamed("_reason", "reject_reason")
                .drop("_key", "_is_bad"))
    return accepted, rejected


def main():
    spark = (SparkSession.builder.appName("hw01-weather")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        print("== 1. Чтение CSV по явной схеме ==")
        df = (spark.read.schema(WEATHER_SCHEMA)
              .option("header", True).option("enforceSchema", False)
              .option("mode", "FAILFAST").option("nullValue", "")
              .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
              .option("dateFormat", "yyyy-MM-dd").csv(CSV_PATH))
        df.printSchema()
        raw_count = df.count()
        if raw_count == 0:
            raise ValueError("CSV пуст")
        print(f"Строк в CSV: {raw_count:,}")

        nulls = df.agg(F.sum(F.when(F.col("temperature_2m").isNull(), 1).otherwise(0))
                        .alias("n")).first()["n"]
        print(f"Доля NULL в temperature_2m: {nulls / raw_count:.4%}")

        print("\n== 2. Проверки качества, accepted/rejected ==")
        accepted, rejected = split_valid(df)
        accepted.persist()
        accepted_count = accepted.count()
        rejected_count = rejected.count()
        print(f"accepted: {accepted_count:,}; rejected: {rejected_count:,}")
        if accepted_count + rejected_count != raw_count:
            raise ValueError("raw != accepted + rejected")
        if rejected_count == 0:
            print("Отклонённых строк нет: проверка воспроизводима, файл rejected не пишем")
        else:
            (rejected.write.mode("overwrite").option("compression", "snappy")
             .parquet(REJECT_PATH))
            print(f"rejected сохранены: {REJECT_PATH}")
            rejected.groupBy("reject_reason").count().show(truncate=False)

        uniq = accepted.select(F.countDistinct("city", "event_ts").alias("keys"),
                                F.count("*").alias("rows")).first()
        if uniq.keys != uniq.rows:
            raise ValueError("В accepted остались дубли (city, event_ts)")
        print("Уникальность (city, event_ts) в accepted подтверждена")

        print("\n== 3. Parquet: партиции по city ==")
        # партиционируем по городу, а не по дате: на 2 годах за 8 городов
        # партиции по дню дали бы больше 700 мелких директорий на этот же
        # объём, а запросы ДЗ и так почти всегда фильтруют по конкретному
        # городу (это не уникальный идентификатор — городов всего 8)
        (accepted.write.mode("overwrite").option("compression", "snappy")
         .partitionBy("city").parquet(PARQUET_PATH))
        parquet_df = spark.read.parquet(PARQUET_PATH)
        parquet_count = parquet_df.count()
        if parquet_count != accepted_count:
            raise ValueError(f"Число строк изменилось: accepted={accepted_count}, parquet={parquet_count}")
        print(f"Строки accepted = Parquet: {accepted_count:,}")

        csv_mb = dir_size_mb(spark, CSV_PATH)
        pq_mb = dir_size_mb(spark, PARQUET_PATH)
        print(f"Размер CSV: {csv_mb:.2f} МиБ; Parquet: {pq_mb:.2f} МиБ")
        if pq_mb > 0:
            print(f"Отношение CSV/Parquet: {csv_mb / pq_mb:.2f}")

        accepted.createOrReplaceTempView("weather_csv")
        parquet_df.createOrReplaceTempView("weather_parquet")
        print("\n== 4. Один запрос на CSV и на Parquet, 3 замера ==")
        print(QUERY.format(view="weather_csv"))
        results = {}
        for trial in range(1, 4):
            formats = ("csv", "parquet") if trial % 2 else ("parquet", "csv")
            for fmt in formats:
                started = time.perf_counter()
                result = spark.sql(QUERY.format(view=f"weather_{fmt}")).first()
                elapsed = time.perf_counter() - started
                if results and result != next(iter(results.values())):
                    raise ValueError(f"Результат запроса разошёлся: {fmt}: {result}")
                results[fmt] = result
                label = "первый замер" if trial == 1 else f"повтор {trial}"
                print(f"{fmt.upper()}, {label}: {elapsed:.3f} с; {result.asDict()}")
        print("Результаты запроса совпали на CSV и Parquet.")
        print("Время зависит от кэшей и среды ноутбука, ускорение не обещается.")

        print("\n== 5. Iceberg: две непересекающиеся порции (2023 и 2024) ==")
        spark.sql(f"CREATE DATABASE IF NOT EXISTS lakehouse.{STUDENT}")
        first_batch = accepted.filter(F.col("event_date") < F.lit(BOUNDARY).cast("date")).count()
        second_batch = accepted.filter(F.col("event_date") >= F.lit(BOUNDARY).cast("date")).count()
        print(f"Первая порция (< {BOUNDARY}, 2023 год): {first_batch:,} строк")
        print(f"Вторая порция (>= {BOUNDARY}, 2024 год): {second_batch:,} строк")
        print(f"Сумма порций: {first_batch + second_batch:,}, accepted: {accepted_count:,}")
        if first_batch == 0 or second_batch == 0 or first_batch + second_batch != accepted_count:
            raise ValueError("Порции для Iceberg не сошлись с accepted")

        def snapshot_ids():
            return {row.snapshot_id for row in
                    spark.sql(f"SELECT snapshot_id FROM {TABLE}.snapshots").collect()}

        previous_ids = snapshot_ids() if spark.catalog.tableExists(TABLE) else set()

        print("\n-- запись 1: CTAS, 2023 год --")
        spark.sql(f"""
            CREATE OR REPLACE TABLE {TABLE}
            USING iceberg
            PARTITIONED BY (months(event_ts))
            AS SELECT * FROM parquet.`{PARQUET_PATH}`
            WHERE event_date < DATE '{BOUNDARY}'
        """)
        after_first = spark.table(TABLE).count()
        if after_first != first_batch:
            raise ValueError("Число строк после CTAS не совпало с первой порцией")
        ids_after_first = snapshot_ids()
        print(f"После записи 1: {after_first:,} строк; новые snapshots: {sorted(ids_after_first - previous_ids)}")

        print("\n-- запись 2: INSERT, 2024 год --")
        spark.sql(f"""
            INSERT INTO {TABLE}
            SELECT * FROM parquet.`{PARQUET_PATH}`
            WHERE event_date >= DATE '{BOUNDARY}'
        """)
        final = spark.table(TABLE).agg(
            F.count("*").alias("rows"),
            F.countDistinct("city", "event_ts").alias("keys"),
        ).first()
        if final.rows != accepted_count or final.keys != accepted_count:
            raise ValueError(f"Финальные строки/ключи не совпали: {final}")
        ids_after_second = snapshot_ids()
        print(f"После записи 2: {final.rows:,} строк; новые snapshots: {sorted(ids_after_second - ids_after_first)}")
        print("Все строки Parquet сохранены в Iceberg без дублей ключа (city, event_ts).")

        print("\n== История snapshots ==")
        spark.sql(f"""
            SELECT snapshot_id, committed_at, operation, summary['total-records'] AS total_records
            FROM {TABLE}.snapshots ORDER BY committed_at
        """).show(50, truncate=False)

        print("\n== Тот же запрос уже на Iceberg-таблице ==")
        spark.sql(QUERY.format(view=TABLE)).show(truncate=False)

        print("\n== Схема Iceberg-таблицы ==")
        spark.sql(f"DESCRIBE TABLE {TABLE}").show(30, truncate=False)

        accepted.unpersist()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
