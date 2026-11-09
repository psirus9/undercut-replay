"""Fetch raw data for held Grands Prix that are not yet in out/signals.json. Safe to rerun."""
import json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime as _dt
HERE = os.path.dirname(os.path.abspath(__file__))
YEAR = int(next((a for a in sys.argv[1:] if a.isdigit()), _dt.date.today().year))
RAW = os.path.join(HERE, f"raw{YEAR}")
CACHE = os.path.join(HERE, "out", "signals.json")
os.makedirs(RAW, exist_ok=True)

def get(url, path, force=False, tries=5):
    if os.path.exists(path) and not force:
        with open(path) as f:
            return json.load(f)
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.load(r)
            with open(path, "w") as f:
                json.dump(data, f)
            time.sleep(0.4)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (i + 1)); continue
            if e.code == 404:
                return []
            if e.code == 401:
                print("LOCKED: OpenF1 restricts access while a session is live. Try again after it ends.", file=sys.stderr)
                sys.exit(3)
            raise
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed {url}")

def jolpica(path, name, force=False):
    out, offset = [], 0
    while True:
        d = get(f"https://api.jolpi.ca/ergast/f1/{path}.json?limit=100&offset={offset}",
                os.path.join(RAW, f"{name}_{offset}.json"), force)
        mr = d["MRData"]
        out.append(mr)
        total = int(mr["total"])
        offset += 100
        if offset >= total:
            return out

def main():
    races = get(f"https://api.jolpi.ca/ergast/f1/{YEAR}/races.json?limit=100",
                os.path.join(RAW, "j_races.json"), force=True)["MRData"]["RaceTable"]["Races"]
    sessions = get(f"https://api.openf1.org/v1/sessions?year={YEAR}&session_name=Race",
                   os.path.join(RAW, "sessions.json"), force=True)
    by_date = {s["date_start"][:10]: s for s in sessions}
    known = set(json.load(open(CACHE))) if os.path.exists(CACHE) else set()
    today = _dt.date.today().isoformat()
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    held = []
    for r in races:
        rnd = r["round"]
        if f"{YEAR}-{rnd}" in known or r["date"] > today:
            continue  # already scored, or not run yet
        s = by_date.get(r["date"])
        if not s or (s.get("date_end") or "9999") > now:
            continue  # no timing session yet, or still running
        res = get(f"https://api.openf1.org/v1/session_result?session_key={s['session_key']}",
                  os.path.join(RAW, f"o_session_result_{s['session_key']}.json"), True)
        if not res:
            continue  # OpenF1 hasn't posted the result yet
        held.append((r, s))
    for r, s in held:
        rnd, sk = r["round"], s["session_key"]
        print("round", rnd, r["raceName"], sk, file=sys.stderr)
        for ep in ["laps", "race_control", "stints", "weather", "pit", "position"]:
            get(f"https://api.openf1.org/v1/{ep}?session_key={sk}", os.path.join(RAW, f"o_{ep}_{sk}.json"))
        # Jolpica if it has posted; otherwise build the same files from OpenF1 so we don't wait
        # (lap data is what Jolpica posts last, so check for it specifically)
        jl = jolpica(f"{YEAR}/{rnd}/laps", f"j_laps_{rnd}", True)
        if int(jl[0]["total"]) > 0:
            jolpica(f"{YEAR}/{rnd}/results", f"j_results_{rnd}", True)
            jolpica(f"{YEAR}/{rnd}/pitstops", f"j_pits_{rnd}", True)
            jolpica(f"{YEAR}/{rnd}/driverstandings", f"j_stand_{rnd}", True)
            r["_source"] = "jolpica"
        else:
            for f in os.listdir(RAW):
                if f.startswith(("j_laps_", "j_results_", "j_pits_", "j_stand_")) and f"_{rnd}_" in f:
                    os.remove(os.path.join(RAW, f))
            import openf1_adapter
            champ = get(f"https://api.openf1.org/v1/championship_drivers?session_key={sk}",
                        os.path.join(RAW, f"o_championship_drivers_{sk}.json"), True)
            openf1_adapter.synthesize(RAW, rnd, sk, champ or None)
            r["_source"] = "openf1"
    with open(os.path.join(RAW, "held.json"), "w") as f:
        json.dump([{"round": r["round"], "name": r["raceName"], "date": r["date"],
                    "circuit": r["Circuit"]["circuitName"], "locality": r["Circuit"]["Location"]["locality"],
                    "country": r["Circuit"]["Location"]["country"], "session_key": s["session_key"],
                    "source": r.get("_source")} for r, s in held], f, indent=1)
    print("held races:", len(held), file=sys.stderr)

if __name__ == "__main__":
    main()
