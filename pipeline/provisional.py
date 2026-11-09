"""Pre-race expectation for the next race that has no official rating yet -> out/provisional.json.

Uses only pre-race facts: circuit history (out/provisional_model.json), the title fight
going in (Jolpica standings), and the grid once qualifying is posted.
Prints "PROVISIONAL CHANGED" when the output differs from the previous file.
"""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch import get, RAW, YEAR, CACHE

H = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(H, "out", "provisional.json")

def features(circ_pct, gap_before, win_pts, frac, final, leader_grid, rival_grid):
    """All inputs known before lights out. leader_grid/rival_grid None before qualifying."""
    close = max(0.0, 1 - gap_before / (3 * win_pts)) if gap_before is not None else 0.0
    f = [
        circ_pct / 100,
        close * frac,
        1.0 if final and gap_before is not None and gap_before <= win_pts else 0.0,
        min(leader_grid, 12) / 12 if leader_grid else 0.15,
        min(rival_grid, 12) / 12 if rival_grid else 0.2,
    ]
    return f

def word(pct):
    return "usually quiet" if pct < 40 else "usually lively" if pct > 60 else "about average"

def main():
    model = json.load(open(os.path.join(H, "out", "provisional_model.json")))
    known = set(json.load(open(CACHE))) if os.path.exists(CACHE) else set()
    races = json.load(open(os.path.join(RAW, "j_races.json")))["MRData"]["RaceTable"]["Races"]
    nxt = next((r for r in sorted(races, key=lambda r: int(r["round"])) if f"{YEAR}-{r['round']}" not in known), None)
    old = open(OUT).read() if os.path.exists(OUT) else None
    if not nxt:
        if os.path.exists(OUT):
            os.remove(OUT)
        print("PROVISIONAL CHANGED" if old else "PROVISIONAL: none (season complete)")
        return
    rnd = nxt["round"]; total = max(int(r["round"]) for r in races)
    circ = nxt["Circuit"]["circuitId"]
    ch = model["circuits"].get(circ, {"pct": 50.0, "races": 0})
    st = get(f"https://api.jolpi.ca/ergast/f1/{YEAR}/driverstandings.json", os.path.join(RAW, "j_standings_now.json"), True)
    lists = st["MRData"]["StandingsTable"]["StandingsLists"]
    ds = lists[0]["DriverStandings"] if lists else []
    gap = float(ds[0]["points"]) - float(ds[1]["points"]) if len(ds) > 1 else None
    lead_id = ds[0]["Driver"]["driverId"] if ds else None
    rival_id = ds[1]["Driver"]["driverId"] if len(ds) > 1 else None
    q = get(f"https://api.jolpi.ca/ergast/f1/{YEAR}/{rnd}/qualifying.json", os.path.join(RAW, f"j_quali_{rnd}.json"), True)
    qr = q["MRData"]["RaceTable"]["Races"]
    grid = {x["Driver"]["driverId"]: int(x["position"]) for x in (qr[0]["QualifyingResults"] if qr else [])}
    final = int(rnd) == total
    f = features(ch["pct"], gap, 25.0, int(rnd) / total, final, grid.get(lead_id), grid.get(rival_id))
    w = model["weights"]
    pct = max(0.0, min(100.0, w[0] + sum(a * b for a, b in zip(w[1:], f))))
    basis = [f"Track history: {word(ch['pct'])}" + (f" across {ch['races']} races since 1996" if ch["races"] else " (new circuit, no history)")]
    if gap is not None:
        rounds_left = total - int(rnd) + 1
        if final and gap <= 25:
            basis.append("Title fight: still open going into the final race")
        elif gap <= 25 * min(3, rounds_left):
            basis.append("Title fight: close, with points on the line")
        else:
            basis.append("Title fight: not much at stake")
    basis.append("Grid: factored in" if grid else "Grid: not set yet, qualifying still to come")
    start = f"{nxt['date']}T{nxt.get('time', '12:00:00Z')}"
    out = {"key": f"{YEAR}-{rnd}", "round": rnd, "name": nxt["raceName"], "date": nxt["date"], "start": start,
           "locality": nxt["Circuit"]["Location"]["locality"], "country": nxt["Circuit"]["Location"]["country"],
           "expected_tier": "Snoozer" if pct < 40 else "Worth It", "expected_pct": round(pct),
           "basis": basis, "grid_known": bool(grid)}
    new = json.dumps(out, indent=1)
    open(OUT, "w").write(new)
    print("PROVISIONAL CHANGED" if new != old else "PROVISIONAL: unchanged", "-", out["name"], out["expected_tier"], out["expected_pct"])

if __name__ == "__main__":
    main()
