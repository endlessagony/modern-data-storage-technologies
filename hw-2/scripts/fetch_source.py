"""
Скачивание контрольного среза из StatsBomb Open Data (https://github.com/statsbomb/open-data).

Файлы берутся по конкретному коммиту репозитория (SOURCE_COMMIT), поэтому при повторном запуске
получаются те же данные, даже если в репозитории что-то обновится.

Срез: матчи плей-офф ЧМ-2022 (43/106) и Евро-2024 (55/282); из событий берутся только удары (Shot).
Записи источника не меняются, к каждой добавляется только служебный блок _source: откуда запись,
коммит, match_id (в самом файле событий его нет) и версия матча last_updated.

Результат: data/input/baseline/matches.jsonl, shots.jsonl и SOURCE_MANIFEST.json (sha256 исходных файлов).
"""
import hashlib
import json
import pathlib
import sys
import urllib.request

SOURCE_COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"   # git ls-remote, 2026-09-23
BASE = f"https://raw.githubusercontent.com/statsbomb/open-data/{SOURCE_COMMIT}/data"
COMPETITIONS = [(43, 106), (55, 282)]
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "input" / "baseline"


def get_json(path: str):
    url = f"{BASE}/{path}"
    with urllib.request.urlopen(url, timeout=120) as r:
        body = r.read()
    return json.loads(body), hashlib.sha256(body).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    matches_out, shots_out, manifest = [], [], []
    for comp_id, season_id in COMPETITIONS:
        path = f"matches/{comp_id}/{season_id}.json"
        matches, sha = get_json(path)
        manifest.append({"file": path, "sha256": sha})
        ko = sorted((m for m in matches if m["competition_stage"]["name"] != "Group Stage"),
                    key=lambda m: (m["match_date"], m["match_id"]))
        for m in ko:
            matches_out.append({"_source": {"file": path, "commit": SOURCE_COMMIT}, "record": m})
            epath = f"events/{m['match_id']}.json"
            events, esha = get_json(epath)
            manifest.append({"file": epath, "sha256": esha, "events_total": len(events)})
            for e in events:
                if e["type"]["name"] == "Shot":
                    shots_out.append({"_source": {"file": epath, "commit": SOURCE_COMMIT,
                                                  "match_id": m["match_id"],
                                                  "version": m["last_updated"]},
                                      "record": e})
            print(f"{m['match_id']} {m['match_date']} events={len(events)}", file=sys.stderr)
    with open(OUT / "matches.jsonl", "w", encoding="utf-8") as f:
        for r in matches_out:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT / "shots.jsonl", "w", encoding="utf-8") as f:
        for r in shots_out:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT / "SOURCE_MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump({"repository": "https://github.com/statsbomb/open-data", "commit": SOURCE_COMMIT,
                   "files": manifest}, f, ensure_ascii=False, indent=1)
    print(f"matches={len(matches_out)} shots={len(shots_out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
