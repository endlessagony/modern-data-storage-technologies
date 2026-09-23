-- ODS: наблюдения «команда — главный тренер — дата матча» из актуальных записей матчей.
-- managers в источнике — массив; обычно один элемент. Команда без тренера даёт строку с manager_id = null.
with sides as (
    select source_system, match_id, match_date, home_team_id as team_id, home_team_name as team_name, home_managers as managers
    from {{ ref('ods_matches') }}
    union all
    select source_system, match_id, match_date, away_team_id, away_team_name, away_managers
    from {{ ref('ods_matches') }}
)
select s.source_system, s.team_id, s.team_name, s.match_id, s.match_date,
       (mg ->> 'id')::bigint as manager_id,
       mg ->> 'name'         as manager_name
from sides s
left join lateral jsonb_array_elements(coalesce(s.managers, '[]'::jsonb)) mg on true
