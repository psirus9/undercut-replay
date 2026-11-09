"""Write Jolpica-format files (laps, pit stops, results, standings) from OpenF1 data,
so a race can be scored as soon as OpenF1 unlocks after the flag, without waiting for Jolpica.

synthesize(rawdir, round, session_key) reads o_*.json files and writes j_*_<round>_0.json.
"""
import json, os
from collections import defaultdict
from datetime import datetime

def ts(s):
    return datetime.fromisoformat(s).timestamp() if s else None

def fmt(sec):
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:06.3f}"

def synthesize(rawdir, rnd, sk, champ=None, season=None):
    L = lambda n: json.load(open(os.path.join(rawdir, f"o_{n}_{sk}.json")))
    laps = L("laps"); res = L("session_result"); pits = L("pit"); posn = L("position")
    by = defaultdict(dict)
    for l in laps:
        by[l["driver_number"]][l["lap_number"]] = l
    # lap end time per driver/lap
    end = defaultdict(dict)
    for d, ls in by.items():
        for n, l in ls.items():
            # the line crossing that ends lap n is the start of lap n+1; fall back to duration on the last lap
            st = ts(l.get("date_start"))
            if n + 1 in ls and ls[n + 1].get("date_start"):
                end[d][n] = ts(ls[n + 1]["date_start"])
            elif l.get("lap_duration") and st:
                end[d][n] = st + l["lap_duration"]
    # fill missing lap end times by interpolating between known laps, so a gap in the feed
    # doesn't drop a driver out of the running order for a lap
    for d, e in end.items():
        known = sorted(e)
        for a, b in zip(known, known[1:]):
            for n in range(a + 1, b):
                e[n] = e[a] + (e[b] - e[a]) * (n - a) / (b - a)
    # smooth timing glitches: a lap recorded several seconds slow followed by one equally fast is a
    # mis-stamped line crossing, not real pace (a pit stop or incident makes both laps slow)
    for d, e in end.items():
        lt = {n: e[n] - e[n - 1] for n in e if n - 1 in e}
        for n in sorted(lt):
            if n + 1 not in lt:
                continue
            around = [lt[k] for k in range(n - 4, n + 6) if k in lt and k not in (n, n + 1)]
            if len(around) < 4:
                continue
            typ = sorted(around)[len(around) // 2]
            a, b = lt[n], lt[n + 1]
            if abs(a - typ) > 2.0 and abs(b - typ) > 1.5 and (a - typ) * (b - typ) < 0 and abs(a + b - 2 * typ) < 0.8:
                e[n] = e[n - 1] + (a + b) / 2
                lt[n] = lt[n + 1] = (a + b) / 2
    starts = [ts(l["date_start"]) for l in laps if l["lap_number"] == 1 and l.get("date_start")]
    t0 = min(starts) if starts else min(min(v.values()) for v in end.values() if v) - 90
    total = max((n for v in end.values() for n in v), default=0)
    out_laps = []
    for n in range(1, total + 1):
        done = sorted((end[d][n], d) for d in end if n in end[d])
        timings = []
        for i, (t, d) in enumerate(done, 1):
            prev = end[d].get(n - 1, t0) if n > 1 else t0
            timings.append({"driverId": str(d), "position": str(i), "time": fmt(t - prev)})
        out_laps.append({"number": str(n), "Timings": timings})
    race_start = t0
    stops = [{"driverId": str(p["driver_number"]), "lap": str(p["lap_number"])}
             for p in pits if p.get("lap_number") and (ts(p["date"]) or 0) > race_start + 30]
    grid = {}
    for p in sorted(posn, key=lambda p: p["date"]):
        if ts(p["date"]) <= race_start + 5:
            grid[p["driver_number"]] = p["position"]
    win = next((r for r in res if r.get("position") == 1), None)
    win_laps = win["number_of_laps"] if win else total
    results = []
    order = sorted(res, key=lambda r: (r.get("position") is None, r.get("position") or 99))
    for i, r in enumerate(order, 1):
        d = r["driver_number"]
        if r.get("dns"): status = "Did not start"
        elif r.get("dnf") or r.get("dsq"): status = "Retired"
        elif r.get("number_of_laps", 0) < win_laps: status = f"+{win_laps - r['number_of_laps']} Laps"
        else: status = "Finished"
        item = {"position": str(r.get("position") or i), "grid": str(grid.get(d, 0)), "laps": str(r.get("number_of_laps") or 0),
                "status": status, "Driver": {"driverId": str(d)}}
        g = r.get("gap_to_leader")
        if win and status == "Finished":
            millis = win["duration"] * 1000 + (g * 1000 if isinstance(g, (int, float)) else 0)
            item["Time"] = {"millis": str(int(millis))}
        results.append(item)
    W = lambda name, mr: json.dump({"MRData": {"total": "1", **mr}}, open(os.path.join(rawdir, f"j_{name}_{rnd}_0.json"), "w"))
    W("laps", {"RaceTable": {"Races": [{"Laps": out_laps}]}})
    W("pits", {"RaceTable": {"Races": [{"PitStops": stops}]}})
    W("results", {"RaceTable": {"Races": [{"Results": results}]}})
    if champ:
        st = sorted(champ, key=lambda c: -(c.get("points_current") or 0))
        W("stand", {"StandingsTable": {"StandingsLists": [{"DriverStandings": [
            {"position": str(i), "points": str(c.get("points_current") or 0)} for i, c in enumerate(st, 1)]}]}})
    return total
