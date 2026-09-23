-- DDS: календарь. Одна строка = один календарный день диапазона дат матчей.
select to_char(d, 'YYYYMMDD')::int as date_key,
       d::date                     as calendar_date,
       extract(year from d)::int   as year,
       extract(month from d)::int  as month,
       extract(isodow from d)::int as iso_day_of_week,
       to_char(d, 'Dy')            as day_name
from generate_series((select min(match_date) from {{ ref('ods_matches') }}),
                     (select max(match_date) from {{ ref('ods_matches') }}),
                     interval '1 day') as d
