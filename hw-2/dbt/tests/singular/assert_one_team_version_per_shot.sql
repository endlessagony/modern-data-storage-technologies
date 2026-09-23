-- История: для каждого удара (события) на дату матча действует РОВНО одна версия команды.
-- Считается независимо от fact_shot — по ODS и dim_team. Возвращает удары с 0 или >1 версий.
select s.source_system, s.event_id, s.match_id, m.match_date, s.team_id, s.team_name,
       count(t.team_version_key) as versions_on_event_date,
       string_agg(t.manager_name, ' | ' order by t.valid_from) as managers
from {{ ref('ods_shots') }} s
join {{ ref('ods_matches') }} m on m.source_system = s.source_system and m.match_id = s.match_id
left join {{ ref('dim_team') }} t
       on t.source_system = s.source_system and t.team_id = s.team_id
      and m.match_date >= t.valid_from and m.match_date < t.valid_to
group by 1,2,3,4,5,6
having count(t.team_version_key) <> 1
