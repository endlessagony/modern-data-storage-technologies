#!/usr/bin/env bash
# Снимок факта, кандидата витрины и публикации под меткой — для сравнения запусков.
# Использование: scripts/snapshot.sh <label>
set -euo pipefail
LABEL="$1"
psql -v ON_ERROR_STOP=1 -q -v label="$LABEL" <<'SQL'
set client_min_messages = warning;
create schema if not exists evidence;
create table if not exists evidence.snap_fact as select ''::text label, now() captured_at, f.shot_key, f.source_system, f.event_id, f.team_version_key, f.match_date, f.outcome, f.xg, f.source_version from dds.fact_shot f where false;
create table if not exists evidence.snap_mart as select ''::text label, now() captured_at, m.* from mart.mart_team_day_shots m where false;
create table if not exists evidence.snap_publish as select ''::text label, now() captured_at, p.* from publish.team_day_shots p where false;
delete from evidence.snap_fact where label = :'label';
delete from evidence.snap_mart where label = :'label';
delete from evidence.snap_publish where label = :'label';
insert into evidence.snap_fact select :'label', now(), f.shot_key, f.source_system, f.event_id, f.team_version_key, f.match_date, f.outcome, f.xg, f.source_version from dds.fact_shot f;
insert into evidence.snap_mart select :'label', now(), m.* from mart.mart_team_day_shots m;
insert into evidence.snap_publish select :'label', now(), p.* from publish.team_day_shots p;
select :'label' as label,
       (select count(*) from evidence.snap_fact where label = :'label') as fact_rows,
       (select count(*) from evidence.snap_mart where label = :'label') as mart_rows,
       (select count(*) from evidence.snap_publish where label = :'label') as publish_rows;
SQL
