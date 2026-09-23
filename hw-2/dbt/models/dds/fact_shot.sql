-- DDS: факт. Одна строка = один удар (событие Shot) в актуальной версии,
-- ключ (source_system, event_id). Включены удары серии пенальти (period = 5) с флагом is_shootout.
-- Версия команды выбирается на ДАТУ МАТЧА (дату события), а не на дату запуска.
select s.shot_key,
       s.source_system,
       s.event_id,
       m.match_key,
       to_char(m.match_date, 'YYYYMMDD')::int                     as date_key,
       m.match_date,
       t.team_version_key,
       {{ surrogate_key(['s.source_system', 's.team_id']) }}      as team_nk,
       s.team_id,
       case when s.team_id = m.home_team_id then m.away_team_id else m.home_team_id end as opponent_team_id,
       p.player_key,
       s.period,
       s.minute,
       s.second,
       s.period = 5                                               as is_shootout,
       s.shot_type,
       s.shot_type = 'Penalty'                                    as is_penalty,
       s.play_pattern,
       s.body_part,
       s.outcome,
       s.outcome in ('Goal', 'Saved', 'Saved to Post')            as is_on_target,
       s.outcome = 'Goal'                                         as is_goal,
       s.xg,
       s.location_x,
       s.location_y,
       s.source_version
from {{ ref('ods_shots') }} s
left join {{ ref('ods_matches') }} m
       on m.source_system = s.source_system and m.match_id = s.match_id
left join {{ ref('dim_team') }} t
       on t.source_system = s.source_system
      and t.team_id = s.team_id
      and m.match_date >= t.valid_from and m.match_date < t.valid_to
left join {{ ref('dim_player') }} p
       on p.source_system = s.source_system and p.player_id = s.player_id
