-- Заполняет dds из staging. Выполняется после того, как в stage.matches и stage.shots загружены CSV.
\timing on

insert into dds.match
select 'statsbomb', match_id, match_date, competition_id, competition_name, season_id, season_name,
       stage_name, home_team_id, home_team_name, away_team_id, away_team_name, home_score, away_score
from stage.matches
order by match_id;

insert into dds.fact_shot
select s.match_date, s.source_system, s.event_id, s.match_id, s.team_id, s.player_id,
       s.period, s.minute, s.second, s.shot_type, s.outcome,
       s.period = 5,
       s.shot_type = 'Penalty',
       s.outcome in ('Goal', 'Saved', 'Saved to Post'),
       s.outcome = 'Goal',
       s.xg
from stage.shots s
order by s.row_no;

vacuum (analyze) dds.match;
vacuum (analyze) dds.fact_shot;
