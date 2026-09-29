-- Границы секций, распределение строк и проверка краёв интервалов для dds.fact_shot_part.
-- Граница FROM входит в секцию, граница TO не входит.
\pset pager off

\echo '== секции и границы =='
select c.relname as partition, pg_get_expr(c.relpartbound, c.oid) as bounds
from pg_inherits i
join pg_class c on c.oid = i.inhrelid
where i.inhparent = 'dds.fact_shot_part'::regclass
order by c.relname;

\echo
\echo '== сколько строк в каждой секции (пустые тоже есть: 2026 создана заранее) =='
select p.relname as partition, coalesce(t.rows, 0) as rows, t.first_day, t.last_day
from pg_inherits i
join pg_class p on p.oid = i.inhrelid
left join (select tableoid, count(*) as rows, min(match_date) as first_day, max(match_date) as last_day
           from dds.fact_shot_part group by tableoid) t on t.tableoid = p.oid
where i.inhparent = 'dds.fact_shot_part'::regclass
order by p.relname;

\echo
\echo '== края интервала: 2023-12-31 уходит в секцию 2023, 2024-01-01 - в секцию 2024 (вставки откатываются) =='
begin;
insert into dds.fact_shot_part
select d, source_system, gen_random_uuid(), match_id, team_id, player_id, period, minute, second,
       'boundary-test', outcome, is_shootout, is_penalty, is_on_target, is_goal, xg
from (select * from dds.fact_shot limit 1) s, (values (date '2023-12-31'), (date '2024-01-01')) v(d);
select tableoid::regclass as partition, match_date from dds.fact_shot_part
where shot_type = 'boundary-test' order by match_date;
rollback;

\echo
\echo '== дата за пределами всех секций отклоняется =='
\set ON_ERROR_STOP off
insert into dds.fact_shot_part
select date '2027-01-01', source_system, gen_random_uuid(), match_id, team_id, player_id, period, minute, second,
       'boundary-test', outcome, is_shootout, is_penalty, is_on_target, is_goal, xg
from dds.fact_shot limit 1;
\set ON_ERROR_STOP on
select count(*) as rows_left_from_tests from dds.fact_shot_part where shot_type = 'boundary-test';

\echo
\echo '== индексы в страницах по 8 КБ и страницы кучи, где лежат строки узкого интервала =='
select relname, pg_relation_size(oid) / 8192 as pages
from pg_class
where relname in ('fact_shot_pkey', 'fact_shot_idx_src_date_team', 'fact_shot_part_2024', 'fact_shot_part_2024_pkey',
                  'fact_shot_part_idx_2024_source_system_match_date_team_id_idx', 'fact_shot_idx', 'fact_shot')
order by relname;
select 'dds.fact_shot_idx' as tbl, count(distinct (ctid::text::point)[0]) as heap_pages_with_narrow_rows
from dds.fact_shot_idx where match_date >= date '2024-06-14' and match_date < date '2024-06-24'
union all
select 'dds.fact_shot_part', count(distinct (ctid::text::point)[0])
from dds.fact_shot_part where match_date >= date '2024-06-14' and match_date < date '2024-06-24';
