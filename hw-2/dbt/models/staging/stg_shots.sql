-- STAGING: типизация ударов. Одна строка = одна полученная запись удара (повторы ещё не убраны).
select
    s.source_system,
    (s.payload ->> 'id')::uuid                                      as event_id,
    (s.envelope ->> 'match_id')::bigint                             as match_id,        -- из имени файла events/<match_id>.json
    (s.envelope ->> 'version')::timestamp                           as source_version,  -- last_updated матча на момент выгрузки
    (s.payload ->> 'period')::int                                   as period,          -- 1,2 — основное время; 3,4 — дополнительное; 5 — серия пенальти
    (s.payload ->> 'minute')::int                                   as minute,
    (s.payload ->> 'second')::int                                   as second,
    (s.payload ->> 'timestamp')::interval                           as time_in_period,
    (s.payload -> 'team' ->> 'id')::bigint                          as team_id,
    s.payload -> 'team' ->> 'name'                                  as team_name,
    (s.payload -> 'player' ->> 'id')::bigint                        as player_id,
    s.payload -> 'player' ->> 'name'                                as player_name,
    s.payload -> 'position' ->> 'name'                              as position_name,
    s.payload -> 'play_pattern' ->> 'name'                          as play_pattern,
    s.payload -> 'shot' -> 'type' ->> 'name'                        as shot_type,
    s.payload -> 'shot' -> 'outcome' ->> 'name'                     as outcome,
    s.payload -> 'shot' -> 'body_part' ->> 'name'                   as body_part,
    s.payload -> 'shot' -> 'technique' ->> 'name'                   as technique,
    (s.payload -> 'shot' ->> 'statsbomb_xg')::numeric(12,8)         as xg,              -- вероятность гола, безразмерная [0;1]
    coalesce((s.payload -> 'shot' ->> 'first_time')::boolean, false) as is_first_time,
    (s.payload -> 'location' ->> 0)::numeric(6,2)                   as location_x,      -- координаты поля StatsBomb 120x80
    (s.payload -> 'location' ->> 1)::numeric(6,2)                   as location_y,
    b.batch_seq,
    s.batch_id,
    s.line_no,
    md5(s.payload::text)                                            as payload_hash
from {{ source('raw', 'shots') }} s
join {{ source('raw', 'batches') }} b using (batch_id)
