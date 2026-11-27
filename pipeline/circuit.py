"""Draw a circuit outline from one clean lap of real car positions in any OpenF1 session.

Used before a race starts: practice and qualifying run on the same circuit, so the race-day
page can show the map at lights out instead of waiting for race data. Same method as tracks.py.
"""
import json, time, urllib.request, urllib.parse
from datetime import datetime, timedelta

API = "https://api.openf1.org/v1"

def _get(path, timeout=60):
    with urllib.request.urlopen(f"{API}/{path}", timeout=timeout) as r:
        return json.load(r)

def draw(sk, min_lap=2):
    """Returns {"d", "w", "h"} or None. Raises urllib.error.HTTPError 401 while a session is live."""
    laps = _get(f"laps?session_key={sk}")
    cand = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap") and l.get("date_start") and l["lap_number"] >= min_lap]
    cand.sort(key=lambda l: l["lap_duration"])
    xy = []
    for lap in cand[: 8] + cand[:: max(1, len(cand) // 20)]:
        t0 = lap["date_start"]
        t1 = (datetime.fromisoformat(t0) + timedelta(seconds=lap["lap_duration"])).isoformat()
        q = f"session_key={sk}&driver_number={lap['driver_number']}&date>={urllib.parse.quote(t0)}&date<={urllib.parse.quote(t1)}"
        try:
            pts = _get(f"location?{q}")
        except Exception:
            time.sleep(1); continue
        xy = [(p["x"], p["y"]) for p in pts if p["x"] or p["y"]]
        xy = [q for i, q in enumerate(xy) if i == 0 or q != xy[i - 1]]
        if len(xy) >= 200: break
        time.sleep(0.4)
    if len(xy) < 150:
        return None
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    s = 100 / max(maxx - minx, maxy - miny)
    step = max(1, len(xy) // 160)
    pts2 = [((x - minx) * s, (maxy - y) * s) for x, y in xy[::step]]
    return {"d": "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z",
            "w": round((maxx - minx) * s, 1), "h": round((maxy - miny) * s, 1)}

def pre_race_track(year, race_date):
    """Outline from the latest finished non-race session of the weekend whose race runs on race_date, or None.
    Matches on the race date, not the country name, because Jolpica and OpenF1 spell countries differently."""
    sessions = _get(f"sessions?year={year}")
    race = next((s for s in sessions if s.get("session_name") == "Race" and s["date_start"][:10] == race_date), None)
    if not race:
        return None
    now = datetime.now().astimezone()
    done = [s for s in sessions if s.get("meeting_key") == race["meeting_key"] and s.get("session_type") != "Race"
            and not s.get("is_cancelled") and datetime.fromisoformat(s["date_end"]) < now]
    for s in sorted(done, key=lambda s: s["date_start"], reverse=True):
        t = draw(s["session_key"])
        if t:
            t["from"] = s["session_name"]
            return t
    return None

if __name__ == "__main__":
    import sys
    print(json.dumps(pre_race_track(int(sys.argv[1]), sys.argv[2]))[:300])
