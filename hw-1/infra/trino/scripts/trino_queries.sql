-- Шаг 4. Федеративные SQL-запросы через Trino поверх Iceberg.
-- Запуск:
-- Файл запускается с хоста из каталога infra/:
--   docker compose exec -T trino trino < trino/scripts/trino_queries.sql
-- Либо построчно в интерактивной консоли:
--   docker compose exec trino trino

-- Какие каталоги видит Trino: наш lakehouse (Iceberg в MinIO) и встроенные
SHOW CATALOGS;

-- Схемы в каталоге lakehouse (неймспейсы Iceberg из JDBC-каталога)
SHOW SCHEMAS IN lakehouse;

-- Таблицы
SHOW TABLES IN lakehouse.dwh;

-- Структура Iceberg-таблицы
DESCRIBE lakehouse.dwh.events;

-- Тот же вопрос и контроль, что в Spark: сверить для одной версии таблицы.
SELECT count(*) AS all_events FROM lakehouse.dwh.events;
SELECT count(*) AS purchase_events, avg(price_rub) AS mean_purchase_price
FROM lakehouse.dwh.events
WHERE event_type = 'purchase'
  AND event_date >= DATE '2026-09-01'
  AND event_date < DATE '2026-10-01';

-- Сумма поля price_rub по событиям purchase; не называем её реальной выручкой.
SELECT region, platform, count(*) AS events,
       round(sum(price_rub) / 1e6, 2) AS price_sum_mln
FROM lakehouse.dwh.events
WHERE event_type = 'purchase'
GROUP BY region, platform
ORDER BY price_sum_mln DESC
LIMIT 10;

-- Отношение числа событий purchase к page_view, не пользовательская конверсия:
-- генератор не моделирует связанную воронку пользователей или сессий.
SELECT category_name,
       count_if(event_type = 'page_view') AS views,
       count_if(event_type = 'purchase')  AS purchases,
       round(
           count_if(event_type = 'purchase') * 100.0 /
           NULLIF(count_if(event_type = 'page_view'), 0),
           2
       ) AS purchase_to_view_pct
FROM lakehouse.dwh.events
GROUP BY category_name
ORDER BY purchases DESC
LIMIT 10;

-- Метаданные Iceberg: снапшоты таблицы видны прямо из SQL
SELECT snapshot_id,
       committed_at,
       operation,
       CAST(summary['total-records'] AS bigint) AS total_records
FROM lakehouse.dwh."events$snapshots";

-- ФЕДЕРАЦИЯ: справочник в другом каталоге (in-memory), JOIN через каталоги.
-- Справочник создаём явно; всю Iceberg-таблицу заранее в memory не копируем.
-- Во время запроса Trino читает и передаёт данные. Справочник покрывает не все регионы.
-- Только учебный справочник: восстановить исходное правило при повторном показе.
DROP TABLE IF EXISTS memory.default.region_groups;
CREATE TABLE memory.default.region_groups AS
SELECT * FROM (
    VALUES
        ('Москва', 'Центр'),
        ('Санкт-Петербург', 'Северо-Запад'),
        ('Новосибирская область', 'Сибирь'),
        ('Свердловская область', 'Урал'),
        ('Татарстан', 'Приволжье')
) AS t(region, federal_district);

SELECT coalesce(g.federal_district, 'Не сопоставлен') AS region_group,
       count(*) AS purchase_events,
       round(avg(e.price_rub), 2) AS mean_purchase_price
FROM lakehouse.dwh.events e
LEFT JOIN memory.default.region_groups g ON e.region = g.region
WHERE e.event_type = 'purchase'
  AND e.event_date >= DATE '2026-09-01'
  AND e.event_date < DATE '2026-10-01'
GROUP BY coalesce(g.federal_district, 'Не сопоставлен')
ORDER BY purchase_events DESC;
