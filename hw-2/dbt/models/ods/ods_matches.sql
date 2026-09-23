-- ODS: актуальное состояние матча. Ключ — (source_system, match_id).
-- Повторы и версии: берём запись с максимальным source_last_updated,
-- при равенстве — из более поздней партии манифеста, затем последнюю строку файла.
with ranked as (
    select *,
           row_number() over (partition by source_system, match_id
                              order by source_last_updated desc, batch_seq desc, line_no desc) as rn,
           count(*)     over (partition by source_system, match_id) as raw_copies
    from {{ ref('stg_matches') }}
)
select {{ surrogate_key(['source_system', 'match_id']) }} as match_key,
       source_system, match_id, match_date, kick_off_raw,
       competition_id, competition_name, season_id, season_name, stage_name,
       home_team_id, home_team_name, away_team_id, away_team_name,
       home_score, away_score, home_managers, away_managers,
       stadium_name, referee_name, source_last_updated, raw_copies, batch_id, payload_hash
from ranked
where rn = 1
