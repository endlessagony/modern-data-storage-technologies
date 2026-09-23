-- Бизнес-правило витрины: голы ≤ удары в створ ≤ все удары.
select * from {{ ref('mart_team_day_shots') }}
where not (goals <= shots_on_target and shots_on_target <= shots)
