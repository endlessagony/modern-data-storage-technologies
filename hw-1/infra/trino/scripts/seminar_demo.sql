-- Семинар 1: выполнять выделенные блоки в DataGrip по порядку.
-- Подключение: jdbc:trino://localhost:8088/lakehouse/dwh, user teacher.
-- Начать после успешного выполнения Spark-скрипта 03_iceberg.py.
-- Изменяется только учебный справочник memory.default.region_groups (блок 5).

-- 1. 53–57 мин. Что доступно через подключение?
SHOW CATALOGS;
SHOW TABLES IN lakehouse.dwh;

-- 2. Читаем подготовленные данные. LIMIT ограничивает вывод, не задаёт порядок.
SELECT count(*) AS all_events FROM lakehouse.dwh.events;
SELECT event_id, event_date, event_type, price_rub
FROM lakehouse.dwh.events
LIMIT 10;

-- 3. 57–60 мин. Тот же вопрос, что в Spark; scale 6 для точного сравнения AVG.
-- Подготовленный набор: 4000 событий, 150808.033185.
SELECT count(*) AS purchase_events,
       avg(CAST(price_rub AS decimal(18,6))) AS mean_purchase_price
FROM lakehouse.dwh.events
WHERE event_type = 'purchase'
  AND event_date >= DATE '2026-09-01'
  AND event_date < DATE '2026-10-01';

-- 4. История таблицы. После повторного показа могут сохраняться старые снимки.
SELECT snapshot_id, committed_at, operation,
       CAST(summary['total-records'] AS bigint) AS total_records
FROM lakehouse.dwh."events$snapshots"
ORDER BY committed_at DESC;

-- 5. 60–65 мин. Восстанавливаем учебный справочник после перезапуска Trino.
DROP TABLE IF EXISTS memory.default.region_groups;
CREATE TABLE memory.default.region_groups AS
SELECT * FROM (VALUES
    ('Москва', 'Центр'),
    ('Санкт-Петербург', 'Северо-Запад'),
    ('Новосибирская область', 'Сибирь'),
    ('Свердловская область', 'Урал'),
    ('Татарстан', 'Приволжье')
) AS t(region, federal_district);
SELECT * FROM memory.default.region_groups ORDER BY region;

-- 6. Обогащаем результат; события без соответствия сохраняются.
SELECT coalesce(g.federal_district, 'Не сопоставлен') AS region_group,
       count(*) AS purchase_events,
       round(avg(CAST(e.price_rub AS decimal(18,6))), 2) AS mean_purchase_price
FROM lakehouse.dwh.events e
LEFT JOIN memory.default.region_groups g ON e.region = g.region
WHERE e.event_type = 'purchase'
  AND e.event_date >= DATE '2026-09-01'
  AND e.event_date < DATE '2026-10-01'
GROUP BY coalesce(g.federal_district, 'Не сопоставлен')
ORDER BY purchase_events DESC;

-- 7. Проверяем отсутствие размножения и незаметных потерь.
-- Первый запрос должен вернуть 0 строк: ключи справочника уникальны.
SELECT region, count(*) AS key_count
FROM memory.default.region_groups
GROUP BY region
HAVING count(*) > 1;

-- Для подготовленного набора: 4000 до JOIN; 4000 после; 1825 без соответствия.
WITH purchases AS (
    SELECT event_id, region
    FROM lakehouse.dwh.events
    WHERE event_type = 'purchase'
      AND event_date >= DATE '2026-09-01'
      AND event_date < DATE '2026-10-01'
)
SELECT (SELECT count(*) FROM purchases) AS before_join,
       count(*) AS after_join,
       count_if(g.region IS NULL) AS unmatched
FROM purchases e
LEFT JOIN memory.default.region_groups g ON e.region = g.region;
