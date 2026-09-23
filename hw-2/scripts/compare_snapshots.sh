#!/usr/bin/env bash
# Сравнение двух снимков по КЛЮЧАМ, СТРОКАМ и МЕРАМ (а не только count(*)).
# Использование: scripts/compare_snapshots.sh <label_a> <label_b>
set -euo pipefail
psql -v ON_ERROR_STOP=1 -v a="$1" -v b="$2" <<'SQL'
\echo '== 1. Количество строк и контрольные суммы мер'
select 'fact_shot' obj, label, count(*) rows, count(distinct shot_key) keys, round(sum(xg),4) sum_xg, count(*) filter (where outcome='Goal') goals,
       md5(string_agg(concat_ws('|', shot_key, team_version_key, outcome, xg), ',' order by shot_key)) checksum
from evidence.snap_fact where label in (:'a', :'b') group by label
union all
select 'publish', label, count(*), count(distinct (source_system, team_id, match_date)), round(sum(xg),4), sum(goals),
       md5(string_agg(concat_ws('|', source_system, team_id, match_date, team_name, manager_name, shots, shots_on_target, goals, xg, goals_minus_xg), ',' order by source_system, team_id, match_date))
from evidence.snap_publish where label in (:'a', :'b') group by label
order by 1, 2;
\echo '== 2. Ключи факта: есть в A, нет в B / есть в B, нет в A'
select 'only_in_A' side, count(*) from (select shot_key from evidence.snap_fact where label=:'a' except select shot_key from evidence.snap_fact where label=:'b') x
union all
select 'only_in_B', count(*) from (select shot_key from evidence.snap_fact where label=:'b' except select shot_key from evidence.snap_fact where label=:'a') x;
\echo '== 3. Строки факта, у которых изменились атрибуты/меры'
select a.event_id, a.source_system, a.outcome a_outcome, b.outcome b_outcome, a.xg a_xg, b.xg b_xg, a.source_version a_version, b.source_version b_version
from evidence.snap_fact a join evidence.snap_fact b on a.shot_key=b.shot_key and a.label=:'a' and b.label=:'b'
where (a.outcome, a.xg, a.team_version_key) is distinct from (b.outcome, b.xg, b.team_version_key);
\echo '== 4. Строки публикации: различия (симметричная разность по всем бизнес-колонкам)'
with pa as (select source_system, team_id, match_date, team_name, manager_name, opponent_name, team_score, shots, shots_on_target, goals, penalty_goals, xg, goals_minus_xg from evidence.snap_publish where label=:'a'),
     pb as (select source_system, team_id, match_date, team_name, manager_name, opponent_name, team_score, shots, shots_on_target, goals, penalty_goals, xg, goals_minus_xg from evidence.snap_publish where label=:'b')
select 'only_in_A' side, * from (select * from pa except select * from pb) x
union all
select 'only_in_B', * from (select * from pb except select * from pa) y
order by match_date, team_id, side;
SQL
