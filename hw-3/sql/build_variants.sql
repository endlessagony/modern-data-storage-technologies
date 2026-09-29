-- Четыре физических варианта одной и той же таблицы фактов (данные идентичны, различается только устройство):
--   dds.fact_shot          исходная таблица: куча + первичный ключ + внешний ключ (создана в ddl_core.sql)
--   dds.fact_shot_idx      то же + составной B-tree индекс под запросы витрины
--   dds.fact_shot_part     секционирование по match_date (RANGE, по годам), без дополнительных индексов
--   dds.fact_shot_part_idx секционирование + тот же составной индекс
-- Побочный вариант dds.fact_shot_idx_rev нужен только для проверки порядка полей в индексе.
\timing on

-- 1. Таблица с индексом. Порядок полей: source_system (равенство), match_date (диапазон), team_id (группировка).
create table dds.fact_shot_idx (like dds.fact_shot including defaults including constraints);
alter table dds.fact_shot_idx add primary key (source_system, event_id);
alter table dds.fact_shot_idx add foreign key (source_system, match_id) references dds.match (source_system, match_id);
create index fact_shot_idx_src_date_team on dds.fact_shot_idx (source_system, match_date, team_id);

\echo '-- вставка 101 тыс. строк в таблицу, где индекс уже есть (поддержка индекса при записи)'
insert into dds.fact_shot_idx select * from dds.fact_shot;

\echo '-- построение того же индекса с нуля на заполненной таблице'
drop index dds.fact_shot_idx_src_date_team;
create index fact_shot_idx_src_date_team on dds.fact_shot_idx (source_system, match_date, team_id);

-- 2. Секционированные таблицы. Границы секций: начало включается, конец исключается.
create table dds.fact_shot_part (like dds.fact_shot including defaults including constraints)
    partition by range (match_date);
create table dds.fact_shot_part_idx (like dds.fact_shot including defaults including constraints)
    partition by range (match_date);

do $$
declare
    parent text;
    year int;
begin
    foreach parent in array array['fact_shot_part', 'fact_shot_part_idx'] loop
        execute format('create table dds.%I partition of dds.%I for values from (%L) to (%L)',
                       parent || '_before_2015', parent, date '1900-01-01', date '2015-01-01');
        for year in 2015..2026 loop
            execute format('create table dds.%I partition of dds.%I for values from (%L) to (%L)',
                           parent || '_' || year, parent, make_date(year, 1, 1), make_date(year + 1, 1, 1));
        end loop;
    end loop;
end $$;

-- в ключ секционированной таблицы обязан входить ключ секционирования
alter table dds.fact_shot_part add primary key (source_system, event_id, match_date);
alter table dds.fact_shot_part add foreign key (source_system, match_id) references dds.match (source_system, match_id);
alter table dds.fact_shot_part_idx add primary key (source_system, event_id, match_date);
alter table dds.fact_shot_part_idx add foreign key (source_system, match_id) references dds.match (source_system, match_id);

insert into dds.fact_shot_part select * from dds.fact_shot;
insert into dds.fact_shot_part_idx select * from dds.fact_shot;

\echo '-- индекс на секционированной таблице (строится по каждой секции)'
create index fact_shot_part_idx_src_date_team on dds.fact_shot_part_idx (source_system, match_date, team_id);

-- 3. Проверка порядка полей: тот же набор колонок, но team_id стоит первым
create table dds.fact_shot_idx_rev (like dds.fact_shot including defaults including constraints);
insert into dds.fact_shot_idx_rev select * from dds.fact_shot;
create index fact_shot_idx_rev_team_date_src on dds.fact_shot_idx_rev (team_id, match_date, source_system);

vacuum (analyze) dds.fact_shot_idx;
vacuum (analyze) dds.fact_shot_part;
vacuum (analyze) dds.fact_shot_part_idx;
vacuum (analyze) dds.fact_shot_idx_rev;
