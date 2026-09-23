-- БИЗНЕС-ПРАВИЛО: голы команды из ударов в игровое время (без серии пенальти) не могут превышать
-- её счёт в матче по данным источника (счёт может быть больше за счёт автоголов соперника).
-- Возвращает нарушившие пары «матч × команда».
with goals as (
    select f.source_system, f.match_key, f.team_id, count(*) filter (where f.is_goal) as goals_from_shots
    from {{ ref('fact_shot') }} f
    where not f.is_shootout
    group by 1,2,3
)
select g.source_system, m.match_id, m.match_date, g.team_id,
       case when g.team_id = m.home_team_id then m.home_team_name else m.away_team_name end as team_name,
       g.goals_from_shots,
       case when g.team_id = m.home_team_id then m.home_score else m.away_score end as team_score
from goals g
join {{ ref('dim_match') }} m on m.match_key = g.match_key
where g.goals_from_shots > case when g.team_id = m.home_team_id then m.home_score else m.away_score end
