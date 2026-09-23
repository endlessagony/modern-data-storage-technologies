#!/usr/bin/env bash
# Полный воспроизводимый прогон всех опытов через Airflow (DAG football_shots_elt должен быть активен).
# Результаты: evidence/logs/*.log, evidence/cases/*.txt, evidence/*.txt
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence/logs evidence/cases
run_case() {  # run_id scenario [start end]
  scripts/trigger_and_wait.sh "$@"
  for t in resolve_slice acquire_pipeline_lock ingest_raw dbt_run_candidate dbt_test_candidate publish report_publication diagnose_quality_failure release_pipeline_lock; do
    echo "===== $t"; python scripts/extract_log.py "$1" "$t"; done > "evidence/logs/$1.log" 2>&1
  scripts/snapshot.sh "$1" >/dev/null
}
FULL="2022-12-03 2024-07-15"

# 0. Успешный запуск с нуля и повтор на том же входе
run_case 01_baseline_first baseline $FULL
psql -f sql/queries.sql > evidence/sql_queries_output.txt 2>&1
python scripts/independent_check.py > /dev/null
run_case 02_baseline_repeat baseline $FULL
scripts/compare_snapshots.sh 01_baseline_first 02_baseline_repeat > evidence/repeat_comparison.txt 2>&1

# 1. Дубликат
run_case 10_case1_duplicate case1_duplicate $FULL
{ echo "### Случай 1. Дубликат: 10_case1_duplicate vs 02_baseline_repeat"
  psql -c "select batch_seq, source_system, file_path, row_count from raw.batches order by batch_seq"
  psql -c "select (select count(*) from raw.shots) raw_shots, (select count(*) from stg.stg_shots) stg_shots, (select count(*) from ods.ods_shots) ods_shots, (select count(*) from dds.fact_shot) fact_shots"
  psql -c "select source_system, event_id, raw_copies, variants_same_version, xg, outcome from ods.ods_shots where raw_copies > 1"
  scripts/compare_snapshots.sh 02_baseline_repeat 10_case1_duplicate; } > evidence/cases/case1_duplicate.txt 2>&1
run_case 11_restore_baseline baseline $FULL

# 2. Пересечение истории
run_case 20_case2_history_overlap case2_history_overlap $FULL
{ echo "### Случай 2. Пересечение истории: 20_case2_history_overlap vs 11_restore_baseline"
  psql -c "select team_name, manager_id, manager_name, valid_from, valid_to, last_observed_on from dds.dim_team where team_id=779 and source_system='statsbomb' order by valid_from, manager_id"
  psql -c "select * from audit.assert_team_versions_no_overlap"
  psql -c "select count(*) as shots_with_ambiguous_version, min(match_date), max(match_date), min(team_name), min(managers) from audit.assert_one_team_version_per_shot"
  psql -c "select * from audit.assert_goals_not_exceed_match_score"
  psql -c "select count(*) duplicated_shot_keys from audit.unique_fact_shot_shot_key"
  echo '-- кандидат витрины (dbt не откатил таблицы):'
  psql -c "select match_date, team_name, manager_name, shots, goals, xg, run_id from mart.mart_team_day_shots where match_date='2022-12-18' order by team_name, manager_name"
  echo '-- опубликованная витрина (потребитель видит прежнюю корректную версию):'
  psql -c "select match_date, team_name, manager_name, shots, goals, xg, published_run_id from publish.team_day_shots where match_date='2022-12-18' order by team_name"
  psql -c "select publication_id, run_id, scenario, rows_published, checksum, published_at from publish.publication_log order by 1 desc limit 1"
  scripts/compare_snapshots.sh 11_restore_baseline 20_case2_history_overlap; } > evidence/cases/case2_history_overlap.txt 2>&1
run_case 21_restore_baseline baseline $FULL

# 3. Позднее исправление: ежедневный срез дня события 2022-12-18 и повтор
run_case 30_case3_late_correction case3_late_correction 2022-12-18 2022-12-19
run_case 31_case3_late_correction_repeat case3_late_correction 2022-12-18 2022-12-19
{ echo "### Случай 3. Позднее исправление: 30_case3_late_correction (срез [2022-12-18, 2022-12-19)) vs 21_restore_baseline"
  psql -c "select batch_seq, source_system, file_path, row_count from raw.batches order by batch_seq"
  psql -c "select event_id, source_version, xg, batch_seq, line_no from stg.stg_shots where event_id='ef86f4d9-7acd-4ed0-a5ec-9129079e8fbe' order by source_version"
  psql -c "select event_id, source_version, xg, raw_copies from ods.ods_shots where event_id='ef86f4d9-7acd-4ed0-a5ec-9129079e8fbe'"
  scripts/compare_snapshots.sh 21_restore_baseline 30_case3_late_correction
  echo; echo "### Повтор на том же входе: 31 vs 30 (исправление не удваивается)"
  scripts/compare_snapshots.sh 30_case3_late_correction 31_case3_late_correction_repeat
  psql -c "select publication_id, run_id, scenario, slice_start, slice_end, rows_published, checksum from publish.publication_log order by 1 desc limit 3"
} > evidence/cases/case3_late_correction.txt 2>&1
run_case 32_restore_baseline baseline $FULL

# 4. Второй источник
run_case 40_case4_second_source case4_second_source $FULL
{ echo "### Случай 4. Второй источник: 40_case4_second_source vs 32_restore_baseline"
  psql -c "select batch_seq, source_system, file_path, row_count from raw.batches order by batch_seq"
  psql -c "select source_system, match_id, match_key, match_date, competition_name, home_team_name, away_team_name, home_score, away_score from dds.dim_match where match_id=3869685 order by source_system"
  psql -c "select source_system, team_id, team_name, manager_name, team_version_key, valid_from, valid_to from dds.dim_team where team_id in (779,771) order by team_id, source_system"
  psql -c "select source_system, player_id, player_name, player_key from dds.dim_player where player_id=5503 order by source_system"
  psql -c "select f.source_system, f.event_id, f.shot_key, t.team_name, f.outcome, f.xg from dds.fact_shot f join dds.dim_team t using(team_version_key) where f.event_id='6d527ebc-a948-4cd8-ac82-daced35bb715' order by 1"
  psql -c "select source_system, match_date, team_id, team_name, shots, goals, xg from publish.team_day_shots where match_date='2022-12-18' order by source_system, team_id"
  echo '-- Контрпример: ключ только по локальному ID слил бы сущности разных источников:'
  psql -c "select event_id, count(*) rows_with_same_local_id, string_agg(source_system, ', ' order by source_system) sources from ods.ods_shots group by event_id having count(*) > 1"
  psql -c "select match_id, count(*) rows_with_same_local_id, string_agg(source_system||': '||home_team_name||' - '||away_team_name, ' | ') from ods.ods_matches group by match_id having count(*) > 1"
  scripts/compare_snapshots.sh 32_restore_baseline 40_case4_second_source; } > evidence/cases/case4_second_source.txt 2>&1
run_case 41_restore_baseline baseline $FULL

# 5. Испорченный вход -> блокировка -> восстановление
run_case 50_corrupted_input corrupted $FULL
{ echo "### Испорченный вход: 50_corrupted_input vs 41_restore_baseline"
  grep -E "FAILED TEST|нарушители|ПОСЛЕДНЯЯ" -A3 evidence/logs/50_corrupted_input.log
  echo "-- трассировка ошибочной строки: ODS -> staging -> raw-партия"
  psql -c "select event_id, match_id, team_name, player_name, minute, shot_type, outcome, xg, source_version, batch_id from ods.ods_shots where xg > 1"
  psql -c "select s.event_id, s.xg, s.source_version, b.file_path, left(b.file_sha256,12) sha, s.line_no, r.envelope ->> 'test_case' as test_case from stg.stg_shots s join raw.batches b using(batch_id) join raw.shots r on r.batch_id=s.batch_id and r.line_no=s.line_no where s.event_id='6cc0d5e2-6999-4006-8a7a-34de4cbe3ffd' order by s.source_version"
  echo "-- кандидат витрины (испорчен, т.к. dbt не откатывает таблицы):"
  psql -c "select match_date, team_name, shots, goals, xg, goals_minus_xg, run_id from mart.mart_team_day_shots where match_date='2022-12-18' order by team_name"
  echo "-- публикация (без изменений):"
  psql -c "select match_date, team_name, shots, goals, xg, goals_minus_xg, published_run_id, last_successful_publication from publish.v_team_day_shots where match_date='2022-12-18' order by team_name"
  scripts/compare_snapshots.sh 41_restore_baseline 50_corrupted_input; } > evidence/cases/corrupted_input.txt 2>&1
run_case 51_recovered_baseline baseline $FULL
{ echo "### Восстановление: 51_recovered_baseline vs 41_restore_baseline"
  grep -E "\[drop\]|\[skip\]|\[raw\]" evidence/logs/51_recovered_baseline.log
  scripts/compare_snapshots.sh 41_restore_baseline 51_recovered_baseline
  psql -c "select publication_id, run_id, scenario, rows_published, checksum, published_at from publish.publication_log order by 1 desc limit 3"
} > evidence/cases/corrupted_recovery.txt 2>&1

# 6. Два ручных запуска подряд: второй ждёт (max_active_runs=1 + ops.pipeline_lock)
airflow dags trigger football_shots_elt --run-id 60_parallel_A --conf '{"scenario":"baseline","slice_start":"2022-12-03","slice_end":"2024-07-15"}' >/dev/null 2>&1
airflow dags trigger football_shots_elt --run-id 60_parallel_B --conf '{"scenario":"baseline","slice_start":"2022-12-03","slice_end":"2024-07-15"}' >/dev/null 2>&1
for i in $(seq 1 8); do sleep 6; airflow dags list-runs football_shots_elt -o json 2>/dev/null | python3 -c "import json,sys; print('t+$((i*6))s:', [(r['run_id'], r['state'], (r.get('start_date') or '')[11:19]) for r in json.load(sys.stdin) if r['run_id'].startswith('60_')])"; done > evidence/parallel_runs.txt
echo done
