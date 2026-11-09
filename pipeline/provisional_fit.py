"""Fit the provisional (pre-race) model on 1996-2025 and save it as out/provisional_model.json.

Pre-race features only: circuit history, the title fight going in, and the grid.
Target: the race's within-era excitement percentile from classics.py.
Usage: python3 provisional_fit.py <jolpica_csv_dir>
"""
import csv, json, os, sys
from collections import defaultdict
import numpy as np
import classics
from provisional import features

H = os.path.dirname(os.path.abspath(__file__))
K = 3  # shrink circuit history toward 50 as if it had K average races

def rows(d, n):
    return csv.DictReader(open(os.path.join(d, f"formula_one_{n}.csv"), newline=""))

def main(d):
    sig = {(r["year"], r["round"]): r for r in json.load(open(os.path.join(H, "out", "classics_signals.json")))}
    R = list(sig.values()); classics.mark_wet(R); classics.score(R)
    season = {r["id"]: int(r["year"]) for r in rows(d, "season")}
    rounds = {r["id"]: r for r in rows(d, "round")}
    circuit = {r["id"]: r["reference"] for r in rows(d, "circuit")}
    races = {r["id"]: r for r in rows(d, "session") if r["type"] == "R" and r["is_cancelled"] != "t"}
    td = {r["id"]: r["driver_id"] for r in rows(d, "teamdriver")}
    rentry = {r["id"]: td.get(r["team_driver_id"]) for r in rows(d, "roundentry")}
    grid = defaultdict(dict); win_pts = {}
    for e in rows(d, "sessionentry"):
        if e["session_id"] in races:
            drv = rentry.get(e["round_entry_id"])
            if drv and e["grid"]:
                grid[e["session_id"]][drv] = int(e["grid"]) or 22
            if e["position"] == "1":
                win_pts[e["session_id"]] = float(e["points"] or 10) or 10
    champ = defaultdict(dict)
    for r in rows(d, "driverchampionship"):
        if r["session_id"] in races and r["points"]:
            champ[r["session_id"]][r["driver_id"]] = float(r["points"])
    by_season = defaultdict(list); last_round = defaultdict(int)
    for sid, s in races.items():
        rd = rounds[s["round_id"]]; by_season[rd["season_id"]].append((int(rd["number"]), sid))
    for r in rounds.values():
        if r["is_cancelled"] != "t":
            last_round[r["season_id"]] = max(last_round[r["season_id"]], int(r["number"]))

    data = []
    for se, lst in by_season.items():
        lst.sort()
        for i, (n, sid) in enumerate(lst):
            rd = rounds[races[sid]["round_id"]]; year = season[se]
            r = sig.get((year, n))
            if not r or year > 2025:
                continue
            before = champ.get(lst[i - 1][1], {}) if i else {}
            if len(before) >= 2:
                order = sorted(before, key=before.get, reverse=True)
                gap = before[order[0]] - before[order[1]]
                lg, rg = grid[sid].get(order[0]), grid[sid].get(order[1])
            else:
                gap, lg, rg = None, None, None
            data.append({"year": year, "circuit": circuit[rd["circuit_id"]], "y": r["era_pct"],
                         "gap": gap, "win": win_pts.get(sid, 25), "frac": n / max(1, last_round[se]),
                         "final": n == last_round[se], "lg": lg, "rg": rg})

    # circuit history, leave-one-out so a race never predicts itself
    tot = defaultdict(lambda: [0.0, 0])
    for x in data:
        tot[x["circuit"]][0] += x["y"]; tot[x["circuit"]][1] += 1
    def circ(x, loo=True):
        s, c = tot[x["circuit"]]
        if loo: s, c = s - x["y"], c - 1
        return (s + 50 * K) / (c + K)
    X = np.array([features(circ(x), x["gap"], x["win"], x["frac"], x["final"], x["lg"], x["rg"]) for x in data])
    y = np.array([x["y"] for x in data], dtype=float)
    A = np.c_[np.ones(len(X)), X]

    # leave-one-season-out check
    years = np.array([x["year"] for x in data]); pred = np.zeros(len(y))
    for yr in sorted(set(years)):
        m = years != yr
        w, *_ = np.linalg.lstsq(A[m], y[m], rcond=None)
        pred[~m] = A[~m] @ w
    r = np.corrcoef(pred, y)[0, 1]
    tier = lambda p: 0 if p <= 30 else 1 if p <= 80 else 2
    hit = np.mean([tier(a) == tier(b) for a, b in zip(pred, y)])
    base = np.mean([tier(50) == tier(b) for b in y])
    must_hits = np.mean([tier(b) == 2 for a, b in zip(pred, y) if a > 62]) if any(pred > 62) else 0
    snooze_hits = np.mean([tier(b) == 0 for a, b in zip(pred, y) if a < 40]) if any(pred < 40) else 0
    print(f"races {len(y)}  corr {r:.2f}  same tier {hit:.0%} (always-'Worth It' baseline {base:.0%})")
    print(f"when it predicts high (>62): really Must Watch {must_hits:.0%}; when low (<40): really Snoozer {snooze_hits:.0%}")
    w, *_ = np.linalg.lstsq(A, y, rcond=None)
    print("weights", np.round(w, 1))
    hist = {c: {"pct": round((s + 50 * K) / (n + K), 1), "races": n} for c, (s, n) in tot.items()}
    json.dump({"weights": list(map(float, w)), "circuits": hist, "cv_corr": round(float(r), 2),
               "cv_same_tier": round(float(hit), 2), "pred_sd": round(float(np.std(pred)), 1)},
              open(os.path.join(H, "out", "provisional_model.json"), "w"), indent=1)

if __name__ == "__main__":
    main(sys.argv[1])
