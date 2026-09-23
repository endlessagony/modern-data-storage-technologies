"""
Независимая проверка: пересчёт мер прямо по исходным файлам StatsBomb (тот же коммит),
без базы и dbt. Результат сравнивается:
  1) со счётом матча из matches/*.json: голы из ударов (без серии пенальти) + автоголы = счёт;
  2) с опубликованной витриной: удары, удары в створ, голы и xG по каждой команде и дню.
Вывод сохраняется в evidence/independent_check.txt.
"""
import json
import os
import pathlib
import urllib.request
from collections import defaultdict
from decimal import Decimal

import psycopg2

COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
BASE = f"https://raw.githubusercontent.com/statsbomb/open-data/{COMMIT}/data"
ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "statsbomb"
ON_TARGET = {"Goal", "Saved", "Saved to Post"}


def get(path):
    f = CACHE / path
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f"{BASE}/{path}", timeout=120) as r:
            f.write_bytes(r.read())
    return json.loads(f.read_text(encoding="utf-8"))


def main():
    calc = {}
    for comp, season in [(43, 106), (55, 282)]:
        for m in get(f"matches/{comp}/{season}.json"):
            if m["competition_stage"]["name"] == "Group Stage":
                continue
            home, away = m["home_team"]["home_team_id"], m["away_team"]["away_team_id"]
            agg = defaultdict(lambda: {"shots": 0, "on_target": 0, "goals": 0, "xg": Decimal(0), "own_goals_for": 0})
            for e in get(f"events/{m['match_id']}.json"):
                t = e["type"]["name"]
                if t == "Shot" and e["period"] < 5:
                    a = agg[e["team"]["id"]]
                    a["shots"] += 1
                    a["on_target"] += e["shot"]["outcome"]["name"] in ON_TARGET
                    a["goals"] += e["shot"]["outcome"]["name"] == "Goal"
                    a["xg"] += Decimal(str(e["shot"]["statsbomb_xg"]))
                elif t == "Own Goal For" and e["period"] < 5:
                    agg[e["team"]["id"]]["own_goals_for"] += 1
            for team, score in [(home, m["home_score"]), (away, m["away_score"])]:
                a = agg[team]
                a["score"] = score
                calc[(team, m["match_date"])] = a | {"match_id": m["match_id"]}

    conn = psycopg2.connect(host=os.environ.get("DWH_HOST", "localhost"), dbname="dwh", user="dwh", password="dwh")
    with conn, conn.cursor() as cur:
        cur.execute("""select team_id, match_date::text, team_name, shots, shots_on_target, goals, xg
                       from publish.team_day_shots where source_system='statsbomb'""")
        pub = {(r[0], r[1]): r for r in cur.fetchall()}

    lines, bad_score, bad_pub = [], 0, 0
    hdr = f"{'date':10} {'team':22} {'src shots':>9} {'pub':>4} {'src ontg':>8} {'pub':>4} {'src goals':>9} {'pub':>4} {'OG':>3} {'score':>5} {'src xG':>8} {'pub xG':>8}  check"
    lines.append(hdr)
    for (team, d), a in sorted(calc.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        p = pub.get((team, d))
        score_ok = a["goals"] + a["own_goals_for"] == a["score"]
        pub_ok = p is not None and (p[3], p[4], p[5]) == (a["shots"], a["on_target"], a["goals"]) \
            and abs(Decimal(p[6]) - a["xg"]) < Decimal("0.0001")
        bad_score += not score_ok
        bad_pub += not pub_ok
        lines.append(f"{d:10} {(p[2] if p else str(team))[:22]:22} {a['shots']:9} {p[3] if p else '-':>4} {a['on_target']:8} "
                     f"{p[4] if p else '-':>4} {a['goals']:9} {p[5] if p else '-':>4} {a['own_goals_for']:3} {a['score']:5} "
                     f"{a['xg']:8.4f} {p[6] if p else '-':>8}  {'OK' if score_ok and pub_ok else 'MISMATCH'}")
    tot = {k: sum(a[k] for a in calc.values()) for k in ["shots", "on_target", "goals", "own_goals_for", "score"]}
    lines.append("")
    lines.append(f"ИТОГО по источнику: команд-матчей={len(calc)} удары={tot['shots']} в створ={tot['on_target']} "
                 f"голы из ударов={tot['goals']} автоголы в пользу={tot['own_goals_for']} сумма счетов={tot['score']} "
                 f"xG={sum(a['xg'] for a in calc.values()):.4f}")
    lines.append(f"Расхождений со счётом матча: {bad_score}; расхождений с публикацией: {bad_pub}; "
                 f"строк в публикации (statsbomb): {len(pub)}")
    out = "\n".join(lines)
    print(out)
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence" / "independent_check.txt").write_text(out + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
