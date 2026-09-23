-- DDS: игрок, SCD1 (последнее написание имени). Одна строка = (source_system, player_id).
select distinct on (source_system, player_id)
       {{ surrogate_key(['source_system', 'player_id']) }} as player_key,
       source_system, player_id, player_name
from {{ ref('ods_shots') }}
order by source_system, player_id, source_version desc, event_id
