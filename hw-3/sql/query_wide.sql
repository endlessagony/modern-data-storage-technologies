-- Запрос 2 (широкий): та же витрина «команда x день» за девять лет, [2016-01-01; 2025-01-01).
select f.source_system,
       f.team_id,
       f.match_date,
       count(*)                                          as shots,
       count(*) filter (where f.is_on_target)            as shots_on_target,
       count(*) filter (where f.is_goal)                 as goals,
       count(*) filter (where f.is_goal and f.is_penalty) as penalty_goals,
       sum(f.xg)                                         as xg,
       count(*) filter (where f.is_goal) - sum(f.xg)     as goals_minus_xg
from {fact} f
where f.source_system = 'statsbomb'
  and not f.is_shootout
  and f.match_date >= date '2016-01-01'
  and f.match_date <  date '2025-01-01'
group by f.source_system, f.team_id, f.match_date
order by f.match_date, f.team_id
