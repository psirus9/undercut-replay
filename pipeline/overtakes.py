"""On-track passes from OpenF1's timestamped overtakes feed.

End-of-lap positions miss passes that happen and get undone within a lap (the 2026 Las Vegas GP showed
8 lead changes that way; race reports give 35). OpenF1 records each overtake with a timestamp, so we
count those instead, with the same exclusions the score has always used: lap 1, safety car / VSC / red
flag periods, pit stops, cars about to retire, and anything after the chequered flag.

passes(load, sk, total_laps) -> list of (lap, position_gained_to), or None if there is no overtakes data.
`load(name)` returns the parsed OpenF1 file for that endpoint (e.g. "overtakes", "pit", "race_control", "laps").
"""
import bisect
from datetime import datetime

def _t(s):
    return datetime.fromisoformat(s).timestamp()

def passes(load, sk, total_laps):
    ov = load("overtakes")
    if not ov:
        return None
    pit, rc, laps = load("pit") or [], load("race_control") or [], load("laps") or []
    starts = {}
    for l in laps:
        if l.get("date_start"):
            starts.setdefault(l["driver_number"], []).append((_t(l["date_start"]), l["lap_number"]))
    for d in starts:
        starts[d].sort()
    lap2 = min((t for v in starts.values() for t, n in v if n == 2), default=0)
    last = {d: v[-1][0] for d, v in starts.items()}
    race_end = max(last.values(), default=1e12)
    durs = sorted(l["lap_duration"] for l in laps if l.get("lap_duration"))
    typ = durs[len(durs) // 2] if durs else 90
    final = [t for v in starts.values() for t, n in v if n == total_laps]
    flag = (min(final) + typ) if final else race_end

    def lap_of(d, t):
        v = starts.get(d)
        if not v:
            return 0
        i = bisect.bisect_right([x[0] for x in v], t) - 1
        return v[i][1] if i >= 0 else 1

    # pit windows: position changes are logged up to ~20 s before the recorded pit time
    pw = {}
    for p in pit:
        if not p.get("date"):
            continue
        t = _t(p["date"]); lane = p.get("lane_duration") or p.get("pit_duration") or 25
        pw.setdefault(p["driver_number"], []).append((t - 30, t + lane + 60))
    # neutral windows: safety car / VSC from deployment until ~a lap after it ends, red flags
    neutral, start = [], None
    for m in sorted(rc, key=lambda m: m["date"]):
        msg = (m.get("message") or "").upper(); t = _t(m["date"])
        if m.get("category") == "SafetyCar" and "DEPLOYED" in msg and start is None:
            start = t
        elif m.get("category") == "SafetyCar" and ("ENDING" in msg or "IN THIS LAP" in msg) and start is not None:
            neutral.append((start, t + 100)); start = None
        if m.get("flag") == "RED" or msg.startswith("RED FLAG"):
            neutral.append((t, t + 600))
    if start is not None:
        neutral.append((start, 1e12))
    inside = lambda ws, t: any(a <= t <= b for a, b in ws)

    out = []
    for o in ov:
        t = _t(o["date"]); a = o["overtaking_driver_number"]; b = o["overtaken_driver_number"]
        if t < lap2 or t > flag - 2 or inside(neutral, t):
            continue
        if inside(pw.get(a, []), t) or inside(pw.get(b, []), t):
            continue
        if b in last and last[b] - t < 150 and last[b] < race_end - 300:
            continue  # the overtaken car stops for good within the next lap or two
        out.append((lap_of(a, t), o["position"]))
    return out

def p12_gaps(load):
    """Gap between the first two cars across the line at the end of each lap, from OpenF1 lap start times."""
    laps = load("laps") or []
    by = {}
    for l in laps:
        if l.get("date_start"):
            by.setdefault(l["lap_number"], []).append(_t(l["date_start"]))
    gaps = {}
    for n, ts in by.items():
        if n < 2 or len(ts) < 2:
            continue
        ts.sort()
        gaps[n - 1] = ts[1] - ts[0]
    return gaps
