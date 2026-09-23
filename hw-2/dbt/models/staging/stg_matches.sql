-- STAGING: типизация записей матчей. Одна строка = одна полученная запись матча (повторы ещё не убраны).
select
    m.source_system,
    (m.payload ->> 'match_id')::bigint                              as match_id,
    (m.payload ->> 'match_date')::date                              as match_date,      -- календарная дата матча из источника
    m.payload ->> 'kick_off'                                        as kick_off_raw,    -- TZ не документирована, не используется для датировки
    (m.payload -> 'competition' ->> 'competition_id')::int          as competition_id,
    m.payload -> 'competition' ->> 'competition_name'               as competition_name,
    (m.payload -> 'season' ->> 'season_id')::int                    as season_id,
    m.payload -> 'season' ->> 'season_name'                         as season_name,
    m.payload -> 'competition_stage' ->> 'name'                     as stage_name,
    (m.payload -> 'home_team' ->> 'home_team_id')::bigint           as home_team_id,
    m.payload -> 'home_team' ->> 'home_team_name'                   as home_team_name,
    (m.payload -> 'away_team' ->> 'away_team_id')::bigint           as away_team_id,
    m.payload -> 'away_team' ->> 'away_team_name'                   as away_team_name,
    (m.payload ->> 'home_score')::int                               as home_score,      -- голы с учётом доп. времени, без серии пенальти
    (m.payload ->> 'away_score')::int                               as away_score,
    m.payload -> 'home_team' -> 'managers'                          as home_managers,
    m.payload -> 'away_team' -> 'managers'                          as away_managers,
    m.payload -> 'stadium' ->> 'name'                               as stadium_name,
    m.payload -> 'referee' ->> 'name'                               as referee_name,
    (m.payload ->> 'last_updated')::timestamp                       as source_last_updated,  -- версия записи в источнике
    b.batch_seq,
    m.batch_id,
    m.line_no,
    md5(m.payload::text)                                            as payload_hash
from {{ source('raw', 'matches') }} m
join {{ source('raw', 'batches') }} b using (batch_id)
