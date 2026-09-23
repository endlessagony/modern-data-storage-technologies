-- Сверка витрины с фактом: суммы ударов, голов и xG по срезу совпадают (JOIN не размножил и не потерял строки).
with f as (
    select count(*) as shots, count(*) filter (where is_goal) as goals, round(sum(xg), 4) as xg
    from {{ ref('fact_shot') }}
    where not is_shootout
      and match_date >= date '{{ var("slice_start") }}' and match_date < date '{{ var("slice_end") }}'
), m as (
    select coalesce(sum(shots),0) as shots, coalesce(sum(goals),0) as goals, coalesce(round(sum(xg), 4),0) as xg
    from {{ ref('mart_team_day_shots') }}
)
select f.shots as fact_shots, m.shots as mart_shots, f.goals as fact_goals, m.goals as mart_goals,
       f.xg as fact_xg, m.xg as mart_xg
from f cross join m
where f.shots <> m.shots or f.goals <> m.goals or abs(f.xg - m.xg) > 0.001
