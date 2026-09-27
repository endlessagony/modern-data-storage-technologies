-- queries.sql — ДЗ 1, студент naermishov, датасет weather.
-- Проверочные, аналитический и федеративный запросы к lakehouse.naermishov.weather.
-- Запуск из infra/: docker compose exec -T trino trino < trino/scripts/hw01_queries.sql
-- либо этот же файл открыть в DataGrip с подключением Trino (localhost:8088, user teacher).
-- Выполнять блоки по порядку, после pipeline.py.

-- 1. Что видно через каталог
SHOW CATALOGS;
SHOW SCHEMAS IN lakehouse;
SHOW TABLES IN lakehouse.naermishov;
DESCRIBE lakehouse.naermishov.weather;

-- 2. Сверка со Spark: тот же вопрос, что в pipeline.py (Москва, январь 2023)
SELECT count(*) AS n_rows,
       avg(CAST(temperature_2m AS decimal(18,6))) AS avg_temp_c
FROM lakehouse.naermishov.weather
WHERE city = 'Москва'
  AND event_date >= DATE '2023-01-01'
  AND event_date < DATE '2023-02-01';

-- 3. Общий объём таблицы (обе порции)
SELECT count(*) AS all_rows FROM lakehouse.naermishov.weather;

-- 4. История snapshots — две новые записи после pipeline.py
SELECT snapshot_id, committed_at, operation,
       CAST(summary['total-records'] AS bigint) AS total_records
FROM lakehouse.naermishov."weather$snapshots"
ORDER BY committed_at DESC;

-- 5. Исследовательский вопрос: какие города похожи по суточному профилю
-- температуры? Средняя температура по городу и часу суток (время в UTC).
SELECT city,
       hour(event_ts) AS hour_of_day,
       round(avg(CAST(temperature_2m AS decimal(18,6))), 2) AS avg_temp_c,
       count(*) AS n
FROM lakehouse.naermishov.weather
GROUP BY city, hour(event_ts)
ORDER BY city, hour_of_day;

-- 6. Федерация: справочник город -> федеральный округ в memory-каталоге
-- Trino. Справочник заведомо неполный (5 из 8 городов), чтобы честно
-- показать группу "Не сопоставлен" для остальных трёх.
DROP TABLE IF EXISTS memory.default.city_regions;
CREATE TABLE memory.default.city_regions AS
SELECT * FROM (VALUES
    ('Москва', 'Центральный'),
    ('Санкт-Петербург', 'Северо-Западный'),
    ('Новосибирск', 'Сибирский'),
    ('Екатеринбург', 'Уральский'),
    ('Краснодар', 'Южный')
) AS t(city, federal_district);
SELECT * FROM memory.default.city_regions ORDER BY city;

-- ключи справочника не дублируются (ожидаем 0 строк)
SELECT city, count(*) AS key_count
FROM memory.default.city_regions
GROUP BY city
HAVING count(*) > 1;

-- 7. Federated JOIN, отвечает на исследовательский вопрос по округам:
-- профиль температуры по часу суток для каждого федерального округа
-- (города без округа не теряются — попадают в "Не сопоставлен")
SELECT coalesce(g.federal_district, 'Не сопоставлен') AS region_group,
       hour(w.event_ts) AS hour_of_day,
       round(avg(CAST(w.temperature_2m AS decimal(18,6))), 2) AS avg_temp_c,
       count(*) AS n
FROM lakehouse.naermishov.weather w
LEFT JOIN memory.default.city_regions g ON w.city = g.city
GROUP BY coalesce(g.federal_district, 'Не сопоставлен'), hour(w.event_ts)
ORDER BY region_group, hour_of_day;

-- 8. Проверка, что JOIN не размножает строки и не теряет их незаметно
WITH base AS (
    SELECT city FROM lakehouse.naermishov.weather
)
SELECT (SELECT count(*) FROM base) AS before_join,
       count(*) AS after_join,
       count_if(g.city IS NULL) AS unmatched
FROM base b
LEFT JOIN memory.default.city_regions g ON b.city = g.city;
