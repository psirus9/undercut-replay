"""One-off: recount passes and lead changes for every cached race from OpenF1 overtakes.

Usage: python3 rebuild_passes.py <dir with OpenF1 files named {endpoint}_{session_key}.json or o_{endpoint}_{session_key}.json>
Rewrites passes_per_lap, front_passes, late_passes, lead_changes and the per-lap intensity in out/signals.json.
Run once when the method changed (Nov 2026); new races are scored this way by score.py directly.
"""
import json, os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import overtakes

def loader(d, sk):
    def load(name):
        for f in (f"{name}_{sk}.json", f"o_{name}_{sk}.json"):
            p = os.path.join(d, f)
            if os.path.exists(p):
                return json.load(open(p))
        return []
    return load

def neutral_laps(rc, total):
    laps, state, start, sc_dep, vsc_dep = set(), None, None, [], []
    for m in sorted([m for m in rc if m.get("lap_number")], key=lambda m: m["date"]):
        msg = (m.get("message") or "").upper(); L = m["lap_number"]
        if m["category"] == "SafetyCar":
            if "VSC DEPLOYED" in msg or "VIRTUAL SAFETY CAR DEPLOYED" in msg:
                if state is None: vsc_dep.append(L); state, start = "vsc", L
            elif "SAFETY CAR DEPLOYED" in msg:
                if state != "sc": sc_dep.append(L); start = L if state is None else start
                state = "sc"
            elif ("ENDING" in msg or "IN THIS LAP" in msg) and state:
                laps.update(range(start, L + 1)); state = None
    if state: laps.update(range(start, total + 1))
    return laps, sc_dep, vsc_dep

def main(src):
    cache_p = os.path.join(HERE, "out", "signals.json")
    cache = json.load(open(cache_p))
    for key, r in cache.items():
        sk, total = r["session_key"], r["laps"]
        load = loader(src, sk)
        ov = overtakes.passes(load, sk, total)
        if ov is None:
            print("no overtakes data, kept lap-end counts:", key); continue
        neutral, sc_dep, vsc_dep = neutral_laps(load("race_control"), total)
        passes = [(L, p) for L, p in ov if L not in neutral]
        n_green = max(1, len([L for L in range(2, total + 1) if L not in neutral and L - 1 not in neutral]))
        late_cut = int(total * 0.75)
        r["passes_per_lap"] = len(passes) / n_green
        r["front_passes"] = sum(1 for L, p in passes if p <= 3)
        r["late_passes"] = sum(1 for L, p in passes if L > late_cut) / max(1, total - late_cut)
        r["lead_changes"] = sum(1 for L, p in passes if p == 1)
        r["pass_source"] = "openf1-overtakes"
        inten = defaultdict(float)
        for L, p in passes: inten[L] += 2.0 if p <= 3 else 1.0
        for L in sc_dep + vsc_dep: inten[L] += 3.0
        for L, g in overtakes.p12_gaps(load).items():
            if L in neutral: continue
            if g < 1.0: inten[L] += 1.5
            elif g < 2.0: inten[L] += 0.5
        r["intensity"] = [round(inten[L], 2) for L in range(1, total + 1)]
    json.dump(cache, open(cache_p, "w"))
    print("rebuilt", len(cache), "races")

if __name__ == "__main__":
    main(sys.argv[1])
