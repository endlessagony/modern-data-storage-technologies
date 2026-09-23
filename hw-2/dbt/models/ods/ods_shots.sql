-- ODS: актуальное состояние удара. Ключ — (source_system, event_id).
-- Повтор той же версии схлопывается; позднее исправление (больший source_version) замещает старую версию.
with hashed as (
    select *,
           dense_rank() over (partition by source_system, event_id, source_version order by payload_hash) as hash_rank
    from {{ ref('stg_shots') }}
),
ranked as (
    select *,
           row_number() over (partition by source_system, event_id
                              order by source_version desc, batch_seq desc, line_no desc) as rn,
           count(*)     over (partition by source_system, event_id) as raw_copies,
           max(hash_rank) over (partition by source_system, event_id, source_version) as variants_same_version
    from hashed
)
select {{ surrogate_key(['source_system', 'event_id']) }} as shot_key,
       source_system, event_id, match_id, source_version,
       period, minute, second, time_in_period,
       team_id, team_name, player_id, player_name, position_name,
       play_pattern, shot_type, outcome, body_part, technique, xg, is_first_time,
       location_x, location_y, raw_copies, variants_same_version, batch_id, payload_hash
from ranked
where rn = 1
