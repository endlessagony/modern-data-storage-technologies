-- Аналитические запросы к ОПУБЛИКОВАННОЙ витрине (то, что видит потребитель).
-- Запуск: psql -h localhost -U dwh -d dwh -f sql/queries.sql

\echo '=== Q1. Финал ЧМ-2022 (18.12.2022): удары, в створ, голы и xG каждой команды (без серии пенальти)'
\echo '    Ожидание: счёт 3:3 и автоголов нет => голы из ударов 3 и 3; пенальти в игре: ARG 1, FRA 2.'
select match_date, team_name, manager_name, opponent_name, team_score, shots, shots_on_target,
       goals, penalty_goals, xg, goals_minus_xg
from publish.v_team_day_shots
where match_date = date '2022-12-18'
order by team_name;

\echo '=== Q2. Реализация моментов по дням: сколько голов и xG приходится на каждый игровой день плей-офф'
\echo '    Ожидание: сумма голов из ударов по дням = 84; сумма счетов = 88 (4 автогола не являются ударами).'
select match_date, min(competition_name) as competition, min(stage_name) as stage,
       count(*) as team_matches, sum(shots) as shots, sum(goals) as goals_from_shots,
       sum(team_score) as goals_in_score, round(sum(xg), 2) as xg,
       round(sum(goals) - sum(xg), 2) as goals_minus_xg
from publish.v_team_day_shots
group by match_date
order by match_date;

\echo '=== Q3. История атрибута (SCD2): одна команда при разных тренерах — xG и голы на матч'
\echo '    Ожидание: Испания — Луис Энрике (ЧМ-2022, 1 матч, 0 голов из ударов, xG 0.50);'
\echo '              де ла Фуэнте (Евро-2024, 4 матча, 10 голов, xG 6.51). При SCD1 все 5 матчей ушли бы к последнему тренеру.'
select team_name, manager_name, count(*) as matches, sum(shots) as shots, sum(goals) as goals,
       round(sum(xg), 2) as xg, round(sum(xg) / count(*), 2) as xg_per_match,
       round(sum(goals)::numeric / count(*), 2) as goals_per_match
from publish.v_team_day_shots
where team_name in ('Spain', 'Portugal', 'Netherlands')
group by team_name, manager_name
order by team_name, min(match_date);

\echo '=== Q4. Кто реализует моменты лучше ожидаемого: топ-5 команд по (голы − xG) за весь срез'
select team_name, count(*) as matches, sum(goals) as goals, round(sum(xg), 2) as xg,
       round(sum(goals) - sum(xg), 2) as goals_minus_xg
from publish.v_team_day_shots
group by team_name
order by goals_minus_xg desc
limit 5;

\echo '=== Дата последней успешной публикации'
select publication_id, run_id, scenario, slice_start, slice_end, rows_published, checksum, published_at
from publish.publication_log order by publication_id desc limit 1;
