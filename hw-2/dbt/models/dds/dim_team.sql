-- DDS: команда, SCD2 по атрибуту «главный тренер».
-- Одна строка = одна версия команды: (source_system, team_id, manager_id) в периоде [valid_from, valid_to).
-- valid_from — первая дата матча, где тренер указан в источнике (дата назначения в источнике отсутствует);
-- valid_to   — первая дата появления ДРУГОГО тренера после последнего наблюдения этого тренера,
--              иначе 9999-12-31. Если источник указывает двух тренеров на одну дату, периоды пересекаются —
--              это неоднозначность, её ловят тесты и публикация блокируется (молча не выбираем).
-- team_name — SCD1: последнее наблюдавшееся написание.
with obs as (
    select * from {{ ref('ods_team_manager_obs') }}
),
versions as (
    select source_system, team_id, manager_id,
           max(manager_name) as manager_name,
           min(match_date)   as first_seen,
           max(match_date)   as last_seen
    from obs
    group by source_system, team_id, manager_id
),
names as (
    select distinct on (source_system, team_id) source_system, team_id, team_name
    from obs
    order by source_system, team_id, match_date desc, match_id desc
)
select {{ surrogate_key(['v.source_system', 'v.team_id', 'v.manager_id', 'v.first_seen']) }} as team_version_key,
       {{ surrogate_key(['v.source_system', 'v.team_id']) }}                                as team_nk,
       v.source_system,
       v.team_id,
       n.team_name,
       v.manager_id,
       v.manager_name,
       v.first_seen as valid_from,
       coalesce((select min(o.first_seen)
                 from versions o
                 where o.source_system = v.source_system
                   and o.team_id = v.team_id
                   and o.manager_id is distinct from v.manager_id
                   and o.first_seen > v.last_seen), date '9999-12-31') as valid_to,
       v.last_seen  as last_observed_on
from versions v
join names n using (source_system, team_id)
