-- История (SCD2): у одной команды периоды версий не должны пересекаться.
-- Возвращает пары пересекающихся версий.
select a.source_system, a.team_id, a.team_name,
       a.manager_name as manager_a, a.valid_from as from_a, a.valid_to as to_a,
       b.manager_name as manager_b, b.valid_from as from_b, b.valid_to as to_b
from {{ ref('dim_team') }} a
join {{ ref('dim_team') }} b
  on a.source_system = b.source_system
 and a.team_id = b.team_id
 and a.team_version_key < b.team_version_key
 and a.valid_from < b.valid_to
 and b.valid_from < a.valid_to
