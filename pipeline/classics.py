"""Classics: score every Grand Prix since 1996 using only what old timing data has.

Inputs per race: lap-by-lap positions and lap times, results (grid, finish, status, time),
championship standings after the race, and pit stops where recorded (2011+).
Safety cars and red flags are inferred from lap times (infer.py); pit laps are inferred
before 2011. Each race is scored against its own era.
"""
import math, statistics as st
from collections import defaultdict
from infer import neutral_laps, pit_laps

ERAS = [  # (first year, last year, label)
    (1996, 2009, "Refuelling era"),
    (2010, 2016, "DRS and Pirelli era"),
    (2017, 2021, "Wide-car era"),
    (2022, 2025, "Ground-effect era"),
    (2026, 2099, "2026 rules"),
]

def era_of(year):
    for a, b, label in ERAS:
        if a <= year <= b:
            return label
    return "Other"

def signals(laptimes, positions, results, pits=None, stakes=0.0, title=0.0):
    """laptimes/positions: {lap: {driver: value}}; results: [{driver, grid, position, finished, millis}];
    pits: {lap: set(driver)} in-laps, or None to infer."""
    total = max(positions) if positions else 0
    if total < 10 or len(results) < 8:
        return None
    neutral, deploy, red = neutral_laps(laptimes, total)
    meds = sorted(st.median([v for v in laptimes[L].values() if v]) for L in laptimes
                  if L > 1 and L not in neutral and len([v for v in laptimes[L].values() if v]) >= 3)
    pace = meds[len(meds) // 4] if meds else None
    if pits is None:
        pits = pit_laps(laptimes, neutral)
    aff = defaultdict(set)
    for L, ds in pits.items():
        aff[L] |= ds; aff[L + 1] |= ds
    cum = defaultdict(dict); run = defaultdict(float)
    for L in sorted(laptimes):
        for d, v in laptimes[L].items():
            if v:
                run[d] += v; cum[L][d] = run[d]

    passes = []
    for L in range(2, total + 1):
        if L not in positions or L - 1 not in positions or L in neutral:
            continue
        prev, cur = positions[L - 1], positions[L]
        a_ = aff[L] | aff[L - 1]
        ds = [d for d in cur if d in prev and d not in a_]
        for a in ds:
            for b in ds:
                if prev[a] > prev[b] and cur[a] < cur[b]:
                    passes.append((L, cur[a]))
    late_cut = int(total * .75)

    lead_changes, leaders = 0, []
    for L in range(1, total + 1):
        if L not in positions or not positions[L]:
            continue
        ld = min(positions[L], key=positions[L].get)
        if leaders and ld != leaders[-1]:
            a_ = aff[L] | aff[L - 1]
            if ld not in a_ and leaders[-1] not in a_ and L not in neutral:
                lead_changes += 1
        leaders.append(ld)

    green = [L for L in range(2, total + 1) if L in cum and L not in neutral and L - 1 not in neutral]
    close = close_front = 0; p12 = {}
    for L in green:
        order = sorted(cum[L], key=lambda d: positions.get(L, {}).get(d, 99))
        a_ = aff[L] | aff[L - 1]
        for i in range(1, min(len(order), 15)):
            a, b = order[i - 1], order[i]
            if a in a_ or b in a_:
                continue
            g = cum[L][b] - cum[L][a]
            if 0 <= g < 1.0:
                close += 1
                if i <= 2: close_front += 1
        if len(order) > 1 and order[0] not in a_ and order[1] not in a_:
            p12[L] = cum[L][order[1]] - cum[L][order[0]]
    ng = max(1, len(green))
    last10 = [p12[L] for L in p12 if L > total - 10]
    min_late = min(last10) if last10 else 10.0

    rs = sorted([r for r in results if r["position"]], key=lambda r: r["position"])
    margin = (rs[1]["millis"] - rs[0]["millis"]) / 1000 if len(rs) > 1 and rs[0]["millis"] and rs[1]["millis"] else 30.0
    if total in neutral:
        margin = min_late
    comeback = max([(r["grid"] or 22) - r["position"] for r in rs[:6]] or [0])
    dnfs = sum(1 for r in results if not r["finished"])

    inten = defaultdict(float)
    for L, p in passes:
        inten[L] += 2.0 if p <= 3 else 1.0
    for L in deploy:
        inten[L] += 3.0
    for L, g in p12.items():
        inten[L] += 1.5 if g < 1 else .5 if g < 2 else 0
    return {
        "laps": total,
        "passes_per_lap": len(passes) / ng,
        "front_passes": sum(1 for L, p in passes if p <= 3),
        "late_passes": sum(1 for L, p in passes if L > late_cut) / max(1, total - late_cut),
        "lead_changes": lead_changes,
        "close_per_lap": close / ng,
        "front_close_share": close_front / ng,
        "margin": margin, "min_late_gap": min_late,
        "comeback": comeback, "dnfs": dnfs,
        "deploys": len(deploy), "red": red,
        "late_sc": sum(1 for L in deploy if L > late_cut),
        "stakes": stakes,
        "title": title,
        "pace": pace,
        "intensity": [round(inten[L], 2) for L in range(1, total + 1)],
    }

W = {"action": .15, "battles": .09, "late_action": .09, "front_fight": .16, "finish": .17,
     "chaos": .12, "comeback": .07, "stakes": .04, "title": .11}

def features(r):
    return {
        "action": r["passes_per_lap"],
        "battles": r["close_per_lap"],
        "late_action": r["late_passes"],
        "front_fight": r["lead_changes"] + .5 * r["front_passes"] + 20 * r["front_close_share"],
        "finish": -math.log(.3 + min(r["margin"], r["min_late_gap"] + 2)),
        "chaos": .9 * r["deploys"] + 2 * r["red"] + .25 * r["dnfs"] + r["late_sc"] + (2.5 if r.get("wet") else 0),
        "comeback": r["comeback"],
        "stakes": r["stakes"],
        "title": r["title"],
    }

def mark_wet(races, ratio=1.07):
    """Wet if a race's green pace is well off that circuit's typical pace in the same era."""
    by = defaultdict(list)
    for r in races:
        if r.get("pace"):
            by[(r["circuit_ref"], era_of(r["year"]), round(r.get("sched_laps", r["laps"]) / 5))].append(r["pace"])
    for r in races:
        p = by.get((r.get("circuit_ref"), era_of(r["year"]), round(r.get("sched_laps", r["laps"]) / 5)), [])
        r["wet"] = bool(r.get("pace") and len(p) >= 3 and r["pace"] > st.median(p) * ratio)
    return races

def score(races, group=lambda r: era_of(r["year"])):
    """Adds score_raw and era percentile (0-100) to each race, z-scored within its group."""
    groups = defaultdict(list)
    for r in races:
        r["_f"] = features(r); groups[group(r)].append(r)
    for g, rs in groups.items():
        cols = {k: [x["_f"][k] for x in rs] for k in W}
        stats = {k: (st.mean(v), st.pstdev(v) or 1) for k, v in cols.items()}
        for r in rs:
            z = {k: max(-2.5, min(2.5, (r["_f"][k] - stats[k][0]) / stats[k][1])) for k in W}
            r["z"] = z
            r["score_raw"] = sum(W[k] * z[k] for k in W)
        vals = sorted(x["score_raw"] for x in rs)
        for r in rs:
            r["era_pct"] = round(100 * sum(1 for v in vals if v <= r["score_raw"]) / len(vals))
    for r in races:
        r.pop("_f", None)
    return races
