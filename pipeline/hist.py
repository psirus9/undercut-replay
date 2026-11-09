"""Build classic-mode signals for every Grand Prix with lap data (1996 on) from the Jolpica CSV dump.

Usage: python3 hist.py <csv_dir>   -> out/classics_signals.json
"""
import csv, json, os, sys
from collections import defaultdict
import classics

H = os.path.dirname(os.path.abspath(__file__))

def secs(t):
    if not t:
        return None
    s = 0.0
    for p in t.split(":"):
        s = s * 60 + float(p)
    return s

def rows(d, name):
    return csv.DictReader(open(os.path.join(d, f"formula_one_{name}.csv"), newline=""))

def main(d):
    season = {r["id"]: int(r["year"]) for r in rows(d, "season")}
    circuit = {r["id"]: r for r in rows(d, "circuit")}
    rounds = {r["id"]: r for r in rows(d, "round")}
    races = {r["id"]: r for r in rows(d, "session") if r["type"] == "R" and r["is_cancelled"] != "t"}
    entries = defaultdict(list)          # race session -> entries
    entry_sess = {}
    for r in rows(d, "sessionentry"):
        if r["session_id"] in races:
            entries[r["session_id"]].append(r); entry_sess[r["id"]] = r["session_id"]
    laps = defaultdict(lambda: (defaultdict(dict), defaultdict(dict)))   # session -> (times, positions)
    lap_no = {}
    for r in rows(d, "lap"):
        sid = entry_sess.get(r["session_entry_id"])
        if not sid or not r["number"] or r["is_deleted"] == "t":
            continue
        n = int(r["number"])
        lap_no[r["id"]] = (sid, n, r["session_entry_id"])
        t, p = laps[sid]
        t[n][r["session_entry_id"]] = secs(r["time"])
        if r["position"]:
            p[n][r["session_entry_id"]] = int(r["position"])
    pits = defaultdict(lambda: defaultdict(set))
    for r in rows(d, "pitstop"):
        x = lap_no.get(r["lap_id"])
        if x:
            pits[x[0]][x[1]].add(x[2])
    champ = defaultdict(dict)   # session -> driver -> points after the race
    for r in rows(d, "driverchampionship"):
        if r["session_id"] in races and r["points"]:
            champ[r["session_id"]][r["driver_id"]] = float(r["points"])
    # previous race and final round per season, for title swings
    by_season = defaultdict(list)
    for sid, s in races.items():
        rd = rounds[s["round_id"]]
        by_season[rd["season_id"]].append((int(rd["number"]), sid))
    prev_of, is_final = {}, {}
    all_rounds = defaultdict(int)
    for r in rounds.values():
        if r["is_cancelled"] != "t":
            all_rounds[r["season_id"]] = max(all_rounds[r["season_id"]], int(r["number"]))
    for se, lst in by_season.items():
        lst.sort()
        for i, (n, sid) in enumerate(lst):
            prev_of[sid] = lst[i - 1][1] if i else None
            is_final[sid] = (n == all_rounds[se], n / max(1, all_rounds[se]))

    out = []
    for sid, s in races.items():
        if sid not in laps:
            continue
        rd = rounds[s["round_id"]]; year = season[rd["season_id"]]
        if year < 1996:
            continue
        res = []
        for e in entries[sid]:
            det = e["detail"] or ""
            res.append({"driver": e["id"], "grid": int(e["grid"] or 0),
                        "position": int(e["position"]) if e["position"] else None,
                        "finished": det in ("Finished", "Lapped", "Did not start", "") and e["is_classified"] == "t" or det.startswith("+"),
                        "millis": None, "points": float(e["points"] or 0)})
        # race time: winner's time is absolute; others are absolute in this dump too (h:mm:ss)
        for e, r in zip(entries[sid], res):
            t = secs(e["time"]) if e["time"] and e["time"].count(":") == 2 else None
            r["millis"] = int(t * 1000) if t else None
        win_pts = max([r["points"] for r in res if r["position"] == 1] or [10]) or 10
        pts = sorted(champ.get(sid, {}).values(), reverse=True)
        stakes = max(0.0, 1 - (pts[0] - pts[1]) / (3 * win_pts)) if len(pts) > 1 else 0.0
        title = 0.0
        before = champ.get(prev_of.get(sid), {})
        after = champ.get(sid, {})
        final, frac = is_final.get(sid, (False, 0))
        if before and after:
            lb = max(before, key=before.get); la = max(after, key=after.get)
            if lb != la:
                title += 1.5 * frac ** 2          # lead changed hands; counts more late in the year
            bp = sorted(before.values(), reverse=True)
            if final and len(bp) > 1 and bp[0] - bp[1] <= win_pts:
                title += 3.0                        # title still live going into the final race
        t, p = laps[sid]
        sig = classics.signals(t, p, res, pits=pits[sid] if pits.get(sid) else None, stakes=stakes, title=title)
        if not sig:
            continue
        c = circuit[rd["circuit_id"]]
        out.append({"year": year, "round": int(rd["number"]), "name": rd["name"], "date": rd["date"],
                    "locality": c["locality"], "country": c["country"], "circuit_ref": c["reference"],
                    "pits_recorded": bool(pits.get(sid)), **sig,
                    "sched_laps": int(s["scheduled_laps"]) if s["scheduled_laps"] else sig["laps"]})
    out.sort(key=lambda r: (r["year"], r["round"]))
    os.makedirs(os.path.join(H, "out"), exist_ok=True)
    json.dump(out, open(os.path.join(H, "out", "classics_signals.json"), "w"))
    print(len(out), "races", out[0]["year"], "to", out[-1]["year"])

if __name__ == "__main__":
    main(sys.argv[1])
