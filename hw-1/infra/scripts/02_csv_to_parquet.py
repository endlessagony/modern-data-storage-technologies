"""Шаг 2. Явная схема, проверки, CSV → Parquet и одинаковый SQL-запрос.

Будущий запуск на подготовленном стенде:
    docker compose exec spark spark-submit /scripts/02_csv_to_parquet.py

Корректные события без цены сохраняются. Набор синтетический; ограничения
и трактовка финансовых полей описаны в ../DATASET.md.
"""

import time

from pyspark.sql import SparkSession, functions as F, types as T

CSV_PATH = "s3a://raw/events/2026/events.csv"
PARQUET_PATH = "s3a://datalake/warehouse/events_parquet"
FINANCIAL_FIELDS = {"price_rub", "quantity", "payment_method"}
EVENT_TYPES = ["page_view", "item_view", "click", "search", "add_to_cart",
               "remove_from_cart", "purchase", "refund"]
PAYMENT_METHODS = ["card", "sbp", "wallet", "cash_on_delivery", "installment"]

# CSV не хранит типы. Даже обязательные поля проверяем по значениям после чтения:
# nullable=False само по себе не является проверкой качества CSV в Spark.
EVENT_SCHEMA = T.StructType([
    T.StructField("event_id", T.StringType()),
    T.StructField("user_id", T.IntegerType()),
    T.StructField("session_id", T.StringType()),
    T.StructField("event_ts", T.TimestampType()),
    T.StructField("event_date", T.DateType()),
    T.StructField("event_type", T.StringType()),
    T.StructField("platform", T.StringType()),
    T.StructField("device_type", T.StringType()),
    T.StructField("os_version", T.StringType()),
    T.StructField("app_version", T.StringType()),
    T.StructField("region", T.StringType()),
    T.StructField("city", T.StringType()),
    T.StructField("referrer", T.StringType()),
    T.StructField("category_id", T.IntegerType()),
    T.StructField("category_name", T.StringType()),
    T.StructField("price_rub", T.DecimalType(12, 2)),
    T.StructField("quantity", T.IntegerType()),
    T.StructField("currency", T.StringType()),
    T.StructField("payment_method", T.StringType()),
    T.StructField("duration_ms", T.IntegerType()),
    T.StructField("ab_group", T.StringType()),
])

QUERY = """
    SELECT count(*) AS purchase_events, avg(price_rub) AS mean_purchase_price
    FROM {view}
    WHERE event_type = 'purchase'
      AND event_date >= DATE '2026-09-01'
      AND event_date < DATE '2026-10-01'
"""


def dir_size_mb(spark, path):
    jvm = spark._jvm
    conf = spark._jsc.hadoopConfiguration()
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(jvm.java.net.URI.create(path), conf)
    summary = fs.getContentSummary(jvm.org.apache.hadoop.fs.Path(path))
    return summary.getLength() / 1024 / 1024


def validate_events(df):
    invalid = F.lit(False)
    for field in EVENT_SCHEMA.fields:
        if field.name not in FINANCIAL_FIELDS:
            invalid = invalid | F.col(field.name).isNull()
            if isinstance(field.dataType, T.StringType):
                invalid = invalid | (F.trim(F.col(field.name)) == "")

    financial = F.col("event_type").isin("purchase", "refund")
    bad_financial = (
        F.col("price_rub").isNull() | (F.col("price_rub") <= 0)
        | F.col("quantity").isNull() | ~F.col("quantity").between(1, 4)
        | F.col("payment_method").isNull()
        | ~F.col("payment_method").isin(PAYMENT_METHODS)
    )
    unexpected_financial = (
        F.col("price_rub").isNotNull() | F.col("quantity").isNotNull()
        | F.col("payment_method").isNotNull()
    )
    invalid = (
        invalid | ~F.col("event_type").isin(EVENT_TYPES)
        | (F.col("event_date") != F.to_date("event_ts"))
        | (F.col("event_date") < F.lit("2026-09-01").cast("date"))
        | (F.col("event_date") >= F.lit("2026-11-30").cast("date"))
        | (F.col("currency") != "RUB")
        | (financial & bad_financial)
        | (~financial & unexpected_financial)
    )
    metrics = df.agg(
        F.count("*").alias("rows"),
        F.countDistinct("event_id").alias("unique_ids"),
        F.sum(F.when(invalid, 1).otherwise(0)).alias("invalid_rows"),
    ).first()
    if metrics.rows == 0:
        raise ValueError("CSV пуст: для демонстрации нужны события")
    if metrics.invalid_rows or metrics.unique_ids != metrics.rows:
        raise ValueError(f"Проверки не пройдены: {metrics.asDict()}")
    print(f"Проверки CSV: {metrics.rows:,} строк; обязательные поля, даты, "
          "финансовые поля и уникальность event_id — OK")
    print("События без цены сохранены: для nonfinancial это допустимый null")
    return metrics.rows


def main():
    spark = (SparkSession.builder.appName("csv-to-parquet")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        print("== CSV: явная схема 21 поля, Decimal(12,2), время UTC ==")
        df = (spark.read.schema(EVENT_SCHEMA)
              .option("header", True).option("enforceSchema", False)
              .option("mode", "FAILFAST").option("nullValue", "")
              .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
              .option("dateFormat", "yyyy-MM-dd").csv(CSV_PATH))
        df.printSchema()
        count = validate_events(df)

        print("\n== Parquet: все события, snappy, партиции event_date ==")
        (df.write.mode("overwrite").option("compression", "snappy")
         .partitionBy("event_date").parquet(PARQUET_PATH))
        parquet_df = spark.read.parquet(PARQUET_PATH)
        csv_types = {field.name: field.dataType for field in df.schema.fields}
        parquet_types = {field.name: field.dataType for field in parquet_df.schema.fields}
        if csv_types != parquet_types:
            raise ValueError("Имена или типы полей изменились после записи Parquet")
        print("Имена и типы всех 21 поля CSV = Parquet (порядок колонок не сравниваем)")
        parquet_count = parquet_df.count()
        if parquet_count != count:
            raise ValueError(f"Количество строк изменилось: CSV={count}, "
                             f"Parquet={parquet_count}")
        print(f"Строки CSV = Parquet: {count:,}")
        csv_mb = dir_size_mb(spark, CSV_PATH)
        pq_mb = dir_size_mb(spark, PARQUET_PATH)
        print(f"Размер CSV: {csv_mb:.2f} МиБ; Parquet: {pq_mb:.2f} МиБ")
        if pq_mb > 0:
            print(f"Отношение размеров CSV/Parquet: {csv_mb / pq_mb:.2f}")

        df.createOrReplaceTempView("events_csv")
        parquet_df.createOrReplaceTempView("events_parquet")
        print("\n== Один запрос: COUNT(*) и AVG(price_rub), покупки сентября ==")
        print(QUERY.format(view="events_csv"))
        print("По 3 измерения каждого формата; первый замер отдельно. "
              "Это не холодный старт: проверки и запись уже читали данные.")
        results = {}
        for trial in range(1, 4):
            # Чередование порядка уменьшает, но не устраняет влияние прогрева.
            formats = ("csv", "parquet") if trial % 2 else ("parquet", "csv")
            for fmt in formats:
                started = time.perf_counter()
                result = spark.sql(QUERY.format(view=f"events_{fmt}")).first()
                elapsed = time.perf_counter() - started
                if results and result != next(iter(results.values())):
                    raise ValueError(f"Результат запроса изменился: {fmt}: {result}")
                results[fmt] = result
                label = "первый замер" if trial == 1 else f"повтор {trial}"
                print(f"{fmt.upper()}, {label}: {elapsed:.3f} с; {result.asDict()}")
        print("Результаты CSV = Parquet во всех замерах.")
        print("Время зависит от кэшей, прогрева, файлов и среды; "
              "преимущество формата по скорости не гарантируется.")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
