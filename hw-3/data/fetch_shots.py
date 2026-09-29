"""
Скачивает удары из StatsBomb Open Data (https://github.com/statsbomb/open-data) по тому же
коммиту, что и в ДЗ-2, и складывает их в плоские CSV.

Результат (рядом со скриптом):
  matches.csv          все матчи открытого набора (одна строка = матч)
  shots.csv.gz         все удары (одна строка = событие Shot)
  control_matches.csv  31 матч плей-офф ЧМ-2022 и Евро-2024 из ДЗ-2
  control_shots.csv    удары этих матчей (866 строк) - маленький контрольный срез
  source_manifest.json коммит, sha256 списков матчей, число файлов событий и итоговая контрольная сумма

Порядок строк фиксирован, поэтому при повторном запуске файлы получаются побайтно теми же
(gzip пишется без времени в заголовке).

Запуск: python fetch_shots.py [--workers 8]
"""
import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import io
import json
import pathlib
import time
import urllib.request

SOURCE_COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
BASE = f"https://raw.githubusercontent.com/statsbomb/open-data/{SOURCE_COMMIT}/data"
HERE = pathlib.Path(__file__).resolve().parent

# матчи плей-офф ЧМ-2022 (43/106) и Евро-2024 (55/282), которые брались в ДЗ-2
CONTROL_MATCH_IDS = {
    3869117, 3869118, 3869151, 3869152, 3869219, 3869220, 3869253, 3869254, 3869321, 3869354,
    3869420, 3869486, 3869519, 3869552, 3869684, 3869685, 3940878, 3940983, 3941017, 3941018,
    3941019, 3941020, 3941021, 3941022, 3942226, 3942227, 3942349, 3942382, 3942752, 3942819,
    3943043,
}

MATCH_COLUMNS = [
    "match_id", "match_date", "competition_id", "competition_name", "season_id", "season_name",
    "stage_name", "home_team_id", "home_team_name", "away_team_id", "away_team_name",
    "home_score", "away_score", "last_updated",
]
SHOT_COLUMNS = [
    "source_system", "event_id", "match_id", "match_date", "team_id", "team_name",
    "player_id", "player_name", "period", "minute", "second", "shot_type", "outcome",
    "body_part", "xg",
]


def download(path, attempts=5):
    url = f"{BASE}/{path}"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                return resp.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def load_matches():
    competitions = json.loads(download("competitions.json"))
    manifest, matches = [], {}
    for comp in sorted(competitions, key=lambda c: (c["competition_id"], c["season_id"])):
        path = f"matches/{comp['competition_id']}/{comp['season_id']}.json"
        body = download(path)
        manifest.append({"file": path, "sha256": hashlib.sha256(body).hexdigest()})
        for m in json.loads(body):
            matches[m["match_id"]] = {
                "match_id": m["match_id"],
                "match_date": m["match_date"],
                "competition_id": m["competition"]["competition_id"],
                "competition_name": m["competition"]["competition_name"],
                "season_id": m["season"]["season_id"],
                "season_name": m["season"]["season_name"],
                "stage_name": m["competition_stage"]["name"],
                "home_team_id": m["home_team"]["home_team_id"],
                "home_team_name": m["home_team"]["home_team_name"],
                "away_team_id": m["away_team"]["away_team_id"],
                "away_team_name": m["away_team"]["away_team_name"],
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "last_updated": m["last_updated"],
            }
    return matches, manifest


def shots_of_match(match):
    body = download(f"events/{match['match_id']}.json")
    rows = []
    for event in json.loads(body):
        if event["type"]["name"] != "Shot":
            continue
        shot = event["shot"]
        rows.append((event["index"], {
            "source_system": "statsbomb",
            "event_id": event["id"],
            "match_id": match["match_id"],
            "match_date": match["match_date"],
            "team_id": event["team"]["id"],
            "team_name": event["team"]["name"],
            "player_id": event["player"]["id"],
            "player_name": event["player"]["name"],
            "period": event["period"],
            "minute": event["minute"],
            "second": event["second"],
            "shot_type": shot["type"]["name"],
            "outcome": shot["outcome"]["name"],
            "body_part": shot["body_part"]["name"],
            "xg": shot.get("statsbomb_xg", ""),
        }))
    rows.sort(key=lambda r: r[0])
    return match["match_id"], hashlib.sha256(body).hexdigest(), [r for _, r in rows]


def write_csv(target, columns, rows, gz=False):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buf.getvalue().encode("utf-8")
    if gz:
        with open(target, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
            f.write(data)
    else:
        target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    matches, manifest = load_matches()
    ordered = sorted(matches.values(), key=lambda m: (m["competition_id"], m["season_id"], m["match_id"]))
    print(f"матчей: {len(ordered)}")

    by_match, event_hashes = {}, {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(shots_of_match, m) for m in ordered]
        for i, fut in enumerate(cf.as_completed(futures), 1):
            match_id, sha, rows = fut.result()
            by_match[match_id] = rows
            event_hashes[match_id] = sha
            if i % 500 == 0:
                print(f"  обработано файлов событий: {i}")

    shots = [row for m in ordered for row in by_match[m["match_id"]]]
    control_matches = [m for m in ordered if m["match_id"] in CONTROL_MATCH_IDS]
    control_shots = [row for row in shots if row["match_id"] in CONTROL_MATCH_IDS]

    write_csv(HERE / "matches.csv", MATCH_COLUMNS, ordered)
    write_csv(HERE / "shots.csv.gz", SHOT_COLUMNS, shots, gz=True)
    write_csv(HERE / "control_matches.csv", MATCH_COLUMNS, control_matches)
    write_csv(HERE / "control_shots.csv", SHOT_COLUMNS, control_shots)

    events_digest = hashlib.sha256(
        "".join(f"{mid}:{event_hashes[mid]}\n" for mid in sorted(event_hashes)).encode()
    ).hexdigest()
    result = {
        "repository": "https://github.com/statsbomb/open-data",
        "commit": SOURCE_COMMIT,
        "matches": len(ordered),
        "shots": len(shots),
        "control_matches": len(control_matches),
        "control_shots": len(control_shots),
        "events_files": len(event_hashes),
        "events_sha256_of_hashes": events_digest,
        "matches_files": manifest,
    }
    (HERE / "source_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ударов: {len(shots)}, контрольный срез: {len(control_shots)}")


if __name__ == "__main__":
    main()
