-- ВИТРИНА-КАНДИДАТ. Одна строка = команда × день матча (в срезе [slice_start, slice_end)).
-- Команда играет не более одного матча в день, поэтому строка = выступление команды в матче.
-- Удары серии пенальти (period = 5) исключены: они не влияют на счёт матча и xG игры.
-- Публикация для потребителя — отдельный шаг (publish.team_day_shots) после успешных тестов.
select f.match_date,
       f.date_key,
       f.source_system,
       f.team_id,
       t.team_name,
       t.manager_name,
       m.competition_name,
       m.stage_name,
       m.match_id,
       case when f.team_id = m.home_team_id then m.away_team_name else m.home_team_name end as opponent_name,
       case when f.team_id = m.home_team_id then m.home_score else m.away_score end         as team_score,
       count(*)                                                    as shots,
       count(*) filter (where f.is_on_target)                      as shots_on_target,
       count(*) filter (where f.is_goal)                           as goals,
       count(*) filter (where f.is_goal and f.is_penalty)          as penalty_goals,
       round(sum(f.xg), 4)                                         as xg,
       round(count(*) filter (where f.is_goal) - sum(f.xg), 4)     as goals_minus_xg,
       date '{{ var("slice_start") }}'                             as slice_start,
       date '{{ var("slice_end") }}'                               as slice_end,
       '{{ var("run_id") }}'::text                                 as run_id
from {{ ref('fact_shot') }} f
join {{ ref('dim_team') }}  t on t.team_version_key = f.team_version_key
join {{ ref('dim_match') }} m on m.match_key = f.match_key
where not f.is_shootout
  and f.match_date >= date '{{ var("slice_start") }}'
  and f.match_date <  date '{{ var("slice_end") }}'
group by 1,2,3,4,5,6,7,8,9,10,11
