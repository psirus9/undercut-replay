"""Draw each circuit from one clean lap of real car positions (OpenF1 location data)."""
import json, os, urllib.request, urllib.parse, time
H = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(H, "out", "tracks.json")
tracks = json.load(open(OUT)) if os.path.exists(OUT) else {}
import glob
RAWD = (sorted(d for d in glob.glob(os.path.join(H, "raw2*")) if os.path.isdir(d)) or [H])[-1]
held = json.load(open(os.path.join(RAWD, "held.json"))) if os.path.exists(os.path.join(RAWD, "held.json")) else []
for m in held:
    sk = m["session_key"]
    if str(sk) in tracks: continue
    laps = json.load(open(os.path.join(RAWD, f"o_laps_{sk}.json")))
    # a clean green lap near the middle of the race from any car
    cand = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap") and l.get("date_start") and l["lap_number"] > 5]
    cand.sort(key=lambda l: l["lap_duration"])
    from datetime import datetime, timedelta
    xy = []
    full = {}
    for lap in (cand[len(cand) // 4: len(cand) // 4 + 6] + cand[::max(1, len(cand) // 25)]):
        t0 = lap["date_start"]
        t1 = (datetime.fromisoformat(t0) + timedelta(seconds=lap["lap_duration"])).isoformat()
        q = f"session_key={sk}&driver_number={lap['driver_number']}&date>={urllib.parse.quote(t0)}&date<={urllib.parse.quote(t1)}"
        try:
            pts = json.load(urllib.request.urlopen(f"https://api.openf1.org/v1/location?{q}", timeout=60))
        except Exception:
            # OpenF1 sometimes refuses a time-window query (Monaco 2026 did). Fetch that car's whole
            # trace once and cut the lap out locally instead.
            try:
                dn = lap["driver_number"]
                if dn not in full:
                    full[dn] = json.load(urllib.request.urlopen(f"https://api.openf1.org/v1/location?session_key={sk}&driver_number={dn}", timeout=180))
                a, b = datetime.fromisoformat(t0), datetime.fromisoformat(t1)
                pts = [p for p in full[dn] if a <= datetime.fromisoformat(p["date"]) <= b]
            except Exception:
                time.sleep(1); continue
        xy = [(p["x"], p["y"]) for p in pts if p["x"] or p["y"]]
        xy = [q for i, q in enumerate(xy) if i == 0 or q != xy[i - 1]]  # drop frozen samples
        if len(xy) >= 200: break
    if len(xy) < 150:
        print("thin", m["name"], len(xy)); continue
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    s = 100 / max(maxx - minx, maxy - miny)
    w, h = (maxx - minx) * s, (maxy - miny) * s
    step = max(1, len(xy) // 160)
    pts2 = [((x - minx) * s, (maxy - y) * s) for x, y in xy[::step]]
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z"
    tracks[str(sk)] = {"d": d, "w": round(w, 1), "h": round(h, 1)}
    print(m["name"], len(xy), "pts")
    json.dump(tracks, open(OUT, "w"))
    time.sleep(0.5)
print(len(tracks), "tracks")
