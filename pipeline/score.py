"""Compute spoiler-free excitement signals and scores for every held race.

Usage: python3 score.py            -> writes out/races.json (current season scored against every cached season)
"""
import json, glob, os, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

def tsec(t):
    if not t:
        return None
    parts = t.split(":")
    s = 0.0
    for p in parts:
        s = s * 60 + float(p)
    return s

def jol(rawdir, prefix):
    out = []
    for f in sorted(glob.glob(os.path.join(rawdir, prefix + "_*.json")), key=lambda p: int(p.rsplit("_", 1)[1][:-5])):
        out.append(json.load(open(f))["MRData"])
    return out

def load(rawdir, path, default=None):
    p = os.path.join(rawdir, path)
    if not os.path.exists(p):
        return default if default is not None else []
    return json.load(open(p))

def race_signals(rawdir, meta):
    rnd, sk = meta["round"], meta["session_key"]
    results = jol(rawdir, f"j_results_{rnd}")[0]["RaceTable"]["Races"][0]["Results"]
    total_laps = max(int(r["laps"]) for r in results)

    # per-lap positions and cumulative times from Jolpica laps
    pos = defaultdict(dict)   # lap -> driver -> position
    cum = defaultdict(dict)   # lap -> driver -> cumulative seconds
    running = defaultdict(float)
    laptimes = defaultdict(dict)
    for mr in jol(rawdir, f"j_laps_{rnd}"):
        for race in mr["RaceTable"]["Races"]:
            for lap in race["Laps"]:
                n = int(lap["number"])
                for t in lap["Timings"]:
                    pos[n][t["driverId"]] = int(t["position"])
                    laptimes[n][t["driverId"]] = tsec(t["time"])
    for n in sorted(laptimes):
        for d, lt in laptimes[n].items():
            if lt is None:
                continue
            running[d] += lt
            cum[n][d] = running[d]

    # pit laps (in-lap) per driver; in-lap and out-lap are "pit affected"
    pitaff = defaultdict(set)
    for mr in jol(rawdir, f"j_pits_{rnd}"):
        for race in mr["RaceTable"]["Races"]:
            for p in race["PitStops"]:
                L = int(p["lap"])
                pitaff[L].add(p["driverId"]); pitaff[L + 1].add(p["driverId"])

    # race control: SC / VSC / red flag, by lap
    rc = load(rawdir, f"o_race_control_{sk}.json")
    sc_laps, vsc_laps, red_laps = set(), set(), set()
    sc_deploy, vsc_deploy = [], []
    state = None; start = None
    rc_sorted = sorted([m for m in rc if m.get("lap_number")], key=lambda m: m["date"])
    for m in rc_sorted:
        msg = (m.get("message") or "").upper(); L = m["lap_number"]
        # a suspension: the RED flag itself, or a message that starts "RED FLAG" (never a plain
        # substring match: "CHEQUERED FLAG" contains "RED FLAG", and steward notes mention it too)
        if m.get("flag") == "RED" or msg.startswith("RED FLAG"):
            red_laps.add(L)
        if m["category"] == "SafetyCar":
            if "VSC DEPLOYED" in msg or "VIRTUAL SAFETY CAR DEPLOYED" in msg:
                if state is None:
                    vsc_deploy.append(L); state, start = "vsc", L
            elif "SAFETY CAR DEPLOYED" in msg:
                if state != "sc":
                    sc_deploy.append(L); start = L if state is None else start
                state = "sc"
            elif ("ENDING" in msg or "IN THIS LAP" in msg) and state:
                for x in range(start, L + 1):
                    (sc_laps if state == "sc" else vsc_laps).add(x)
                state = None
    red = len(red_laps)
    if state:  # neutralised to the flag
        for x in range(start, total_laps + 1):
            (sc_laps if state == "sc" else vsc_laps).add(x)
    neutral = sc_laps | vsc_laps

    # ---- passes on track (pairwise swaps between consecutive laps)
    passes = []  # (lap, position_gained_to)
    for L in range(2, total_laps + 1):
        if L not in pos or L - 1 not in pos or L in neutral:
            continue
        prev, cur = pos[L - 1], pos[L]
        aff = pitaff[L] | pitaff[L - 1]
        ds = [d for d in cur if d in prev and d not in aff]
        for a in ds:
            for b in ds:
                if prev[a] > prev[b] and cur[a] < cur[b]:
                    passes.append((L, cur[a]))
    n_pass = len(passes)
    front_pass = sum(1 for L, p in passes if p <= 3)
    late_cut = int(total_laps * 0.75)
    late_pass = sum(1 for L, p in passes if L > late_cut)

    # ---- lead changes on track and number of leaders
    leaders = []
    lead_on_track = 0
    for L in range(1, total_laps + 1):
        if L not in pos: continue
        ld = min(pos[L], key=pos[L].get)
        if leaders and ld != leaders[-1]:
            if ld not in (pitaff[L] | pitaff[L - 1]) and leaders[-1] not in (pitaff[L] | pitaff[L - 1]) and L not in neutral:
                lead_on_track += 1
        leaders.append(ld)
    n_leaders = len(set(leaders))

    # ---- gaps at the line: close running, front gap trajectory
    green = [L for L in range(2, total_laps + 1) if L in cum and L not in neutral and L - 1 not in neutral]
    close_pairs = 0; close_front = 0
    p12_gap = {}
    for L in green:
        order = sorted(cum[L], key=lambda d: pos[L].get(d, 99))
        aff = pitaff[L] | pitaff[L - 1]
        for i in range(1, len(order)):
            a, b = order[i - 1], order[i]
            if a in aff or b in aff: continue
            g = cum[L][b] - cum[L][a]
            if 0 <= g < 1.0 and i < 15:
                close_pairs += 1
                if i <= 2: close_front += 1
        if len(order) > 1 and order[0] not in aff and order[1] not in aff:
            p12_gap[L] = cum[L][order[1]] - cum[L][order[0]]
    n_green = max(1, len(green))
    last10 = [p12_gap[L] for L in p12_gap if L > total_laps - 10]
    min_late_gap = min(last10) if last10 else 10.0

    # final margin P1-P2
    res_sorted = sorted(results, key=lambda r: int(r["position"]))
    t1 = int(res_sorted[0]["Time"]["millis"]) if res_sorted[0].get("Time") else None
    t2 = int(res_sorted[1]["Time"]["millis"]) if res_sorted[1].get("Time") else None
    margin = (t2 - t1) / 1000 if t1 and t2 else 30.0
    if total_laps in neutral:  # finished behind the safety car: the margin means nothing
        margin = min_late_gap

    # comebacks: best grid->finish gain among top 6 finishers
    comeback = 0
    for r in res_sorted[:6]:
        g = int(r["grid"]) or 22
        comeback = max(comeback, g - int(r["position"]))
    dnfs = sum(1 for r in results if not (r["status"] in ("Finished", "Lapped", "Did not start") or r["status"].startswith("+")))

    # strategy spread among top 10: distinct compound sequences
    stints = load(rawdir, f"o_stints_{sk}.json")
    sres = load(rawdir, f"o_session_result_{sk}.json")
    top10 = {r["driver_number"] for r in sres if r.get("position") and r["position"] <= 10}
    seqs = defaultdict(list)
    for s in sorted(stints, key=lambda s: (s["driver_number"], s["stint_number"])):
        if s["driver_number"] in top10 and s.get("compound"):
            if not seqs[s["driver_number"]] or seqs[s["driver_number"]][-1] != s["compound"]:
                seqs[s["driver_number"]].append(s["compound"])
    strat = len({tuple(v) for v in seqs.values()})

    # rain
    weather = load(rawdir, f"o_weather_{sk}.json")
    olaps = load(rawdir, f"o_laps_{sk}.json")
    starts = sorted(l["date_start"] for l in olaps if l.get("date_start"))
    t0 = starts[0] if starts else ""
    t1 = starts[-1] if starts else "9999"
    gauge_rain = sum(1 for w in weather if (w.get("rainfall") or 0) > 0 and t0 <= w["date"] <= t1) >= 2
    # The rain gauge can miss a wet race (track still wet from earlier rain, or rain only at the end).
    # The tyres don't: if a tenth of all laps were run on intermediates or wets, it was a wet race.
    rain = gauge_rain or wet_share(stints) >= 0.10

    # championship stakes: leader's points gap after this race, and whether the lead changed
    stakes = 0.0
    try:
        stand = jol(rawdir, f"j_stand_{rnd}")[0]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
        gap = float(stand[0]["points"]) - float(stand[1]["points"])
        stakes = max(0.0, 1 - gap / 75)  # 0 when the title gap is huge, 1 when level
    except Exception:
        pass

    # ---- per-lap intensity for the "watch from" pointer
    inten = defaultdict(float)
    for L, p in passes:
        inten[L] += 2.0 if p <= 3 else 1.0
    for L in sc_deploy + vsc_deploy:
        inten[L] += 3.0
    for L in p12_gap:
        g = p12_gap[L]
        if g < 1.0: inten[L] += 1.5
        elif g < 2.0: inten[L] += 0.5
    return {
        "laps": total_laps,
        "passes_per_lap": n_pass / n_green,
        "front_passes": front_pass,
        "late_passes": late_pass / max(1, total_laps - late_cut),
        "lead_changes": lead_on_track,
        "leaders": n_leaders,
        "close_per_lap": close_pairs / n_green,
        "front_close_share": close_front / n_green,
        "margin": margin,
        "min_late_gap": min_late_gap,
        "comeback": comeback,
        "dnfs": dnfs,
        "sc": len(sc_deploy), "vsc": len(vsc_deploy), "red": red,
        "late_sc": sum(1 for L in sc_deploy + vsc_deploy if L > late_cut),
        "strategies": strat,
        "rain": rain,
        "stakes": stakes,
        "intensity": [round(inten[L], 2) for L in range(1, total_laps + 1)],
    }

CACHE = os.path.join(HERE, "out", "signals.json")

def wet_share(stints):
    """Share of all race laps run on intermediate or full wet tyres."""
    tot = wet = 0
    for s in stints:
        if s.get("lap_start") is None or s.get("lap_end") is None: continue
        n = s["lap_end"] - s["lap_start"] + 1
        tot += n
        if s.get("compound") in ("INTERMEDIATE", "WET"): wet += n
    return wet / tot if tot else 0.0

def collect():
    """All scored races: cached signals plus any newly fetched race (raw<year>/held.json)."""
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    new = []
    for rawdir in sorted(glob.glob(os.path.join(HERE, "raw*"))):
        if not os.path.isdir(rawdir): continue
        tail = os.path.basename(rawdir)[3:]
        if not tail.isdigit(): continue
        year = int(tail)
        for m in load(rawdir, "held.json"):
            key = f"{year}-{m['round']}"
            if key in cache: continue
            try:
                s = race_signals(rawdir, m)
            except Exception as e:
                print("skip", year, m["name"], e); continue
            cache[key] = {**m, "year": year, **s}
            new.append(f"{year} R{m['round']} {m['name']}")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w"))
    print("NEW RACES:", ", ".join(new) if new else "none")
    return sorted(cache.values(), key=lambda r: (r["year"], int(r["round"])))

def z(vals, x):
    mu = st.mean(vals); sd = st.pstdev(vals) or 1
    return max(-2.5, min(2.5, (x - mu) / sd))

def main():
    races = [dict(r) for r in collect()]
    cur = max(r["year"] for r in races)
    pool = races  # baseline: both seasons

    def feat(r):
        import math
        return {
            "action": r["passes_per_lap"],
            "battles": r["close_per_lap"],
            "late_action": r["late_passes"],
            "front_fight": r["lead_changes"] + 0.5 * r["front_passes"] + 20 * r["front_close_share"],
            "finish": -math.log(0.3 + min(r["margin"], r["min_late_gap"] + 2)),
            "chaos": r["sc"] + 0.5 * r["vsc"] + 2 * r["red"] + 0.25 * r["dnfs"] + (1.5 if r["rain"] else 0) + r["late_sc"],
            "comeback": r["comeback"],
            "strategy": r["strategies"],
            "stakes": r["stakes"],
        }
    W = {"action": .16, "battles": .10, "late_action": .10, "front_fight": .16, "finish": .18,
         "chaos": .12, "comeback": .07, "strategy": .05, "stakes": .06}
    F = [feat(r) for r in pool]
    keys = list(W)
    cols = {k: [f[k] for f in F] for k in keys}
    for r, f in zip(pool, F):
        zz = {k: z(cols[k], f[k]) for k in keys}
        r["z"] = {k: round(v, 2) for k, v in zz.items()}
        r["score_raw"] = sum(W[k] * zz[k] for k in keys)
        r["front_raw"] = (zz["front_fight"] + zz["finish"]) / 2
        r["pack_raw"] = (zz["action"] + zz["battles"] + zz["comeback"]) / 3
        r["action_m"] = (zz["action"] + zz["battles"] + zz["late_action"]) / 3
        r["suspense_m"] = (zz["front_fight"] + zz["finish"]) / 2
        r["chaos_m"] = zz["chaos"]

    def pct(vals, x):
        return sum(1 for v in vals if v <= x) / len(vals)
    allscore = [r["score_raw"] for r in pool]
    for r in pool:
        p = pct(allscore, r["score_raw"])
        r["score"] = round(100 * p)
        r["tier"] = ("Snoozer" if p <= .30 else "Worth It" if p <= .80 else "Must Watch")
        for k in ["front_raw", "pack_raw", "action_m", "suspense_m", "chaos_m"]:
            vals = [x[k] for x in pool]
            r[k.replace("_raw", "").replace("_m", "") + ("_pct" if k.endswith("_raw") else "_meter")] = (
                round(100 * pct(vals, r[k])) if k.endswith("_raw") else max(1, min(5, 1 + int(pct(vals, r[k]) * 5 - 1e-9))))
        # watch-from pointer: smallest suffix (after lap 3) holding >=65% of race intensity
        it = r["intensity"]; tot = sum(it[3:]) or 1
        acc = 0; start = None
        for i in range(len(it) - 1, 2, -1):
            acc += it[i]
            if acc / tot >= .60:
                start = i + 1; break
        share = (len(it) - (start or 1) + 1) / len(it)
        if r["tier"] == "Snoozer":
            r["advice"] = {"kind": "recap", "text": "Recap is enough"}
        elif start and share <= .5:
            r["advice"] = {"kind": "from", "lap": start, "text": f"Start at lap {start} of {len(it)}"}
        else:
            # longest quiet stretch in the middle: every 3-lap window holds under 1 point of action
            n = len(it); best = (0, 0); run_start = None
            for i in range(3, n - 3):
                quiet = sum(it[i:i + 3]) < 1.0
                if quiet and run_start is None: run_start = i
                if (not quiet or i == n - 4) and run_start is not None:
                    end = i if not quiet else i + 1
                    if end - run_start > best[1] - best[0]: best = (run_start, end)
                    run_start = None
            if best[1] - best[0] >= max(8, int(.2 * n)):
                a, b = best[0] + 2, best[1] + 1  # 1-based laps, trimmed so no action is skipped
                r["advice"] = {"kind": "skip", "from": a, "to": b, "text": f"Skip laps {a} to {b}"}
            else:
                r["advice"] = {"kind": "full", "text": "Watch the whole thing"}
        r["intensity_profile"] = [round(sum(it[i:i + max(1, len(it) // 24)]), 1) for i in range(0, len(it), max(1, len(it) // 24))]

    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    season = [r for r in pool if r["year"] == cur]
    # per-factor breakdown for the "how it was scored" view: numbers only, no names or positions
    LABEL = {"action": "On-track passing", "battles": "Wheel-to-wheel running", "late_action": "Late-race passing",
             "front_fight": "Fight at the front", "finish": "Closeness of the finish", "chaos": "Chaos",
             "comeback": "Comeback drives", "strategy": "Strategy variety", "stakes": "Title stakes"}
    def stat(r, k):
        if k == "action": return f"{r['passes_per_lap']:.2f} passes per green-flag lap"
        if k == "battles": return f"{r['close_per_lap']:.1f} cars within a second of the car ahead, per lap"
        if k == "late_action": return f"{r['late_passes']:.2f} passes per lap in the final quarter"
        if k == "front_fight":
            close = round(100 * min(1.0, r["front_close_share"]))
            return (f"{r['lead_changes']} lead change{'s' if r['lead_changes'] != 1 else ''} on track, "
                    f"{r['front_passes']} pass{'es' if r['front_passes'] != 1 else ''} for podium places, "
                    f"top three nose to tail (under a second) on about {close}% of laps")
        if k == "finish":
            m = min(r["margin"], r["min_late_gap"] + 2)
            return f"Closest gap at the front late on: {r['min_late_gap']:.1f}s. Winning margin: {r['margin']:.1f}s"
        if k == "chaos":
            bits = [f"{r['sc']} safety car{'s' if r['sc'] != 1 else ''}", f"{r['vsc']} VSC{'s' if r['vsc'] != 1 else ''}"]
            if r["red"]: bits.append(f"{r['red']} red flag{'s' if r['red'] != 1 else ''}")
            bits.append(f"{r['dnfs']} retirement{'s' if r['dnfs'] != 1 else ''}")
            if r["rain"]: bits.append("rain")
            return ", ".join(bits)
        if k == "comeback": return f"Biggest climb by a top-six finisher: {r['comeback']} place{'s' if r['comeback'] != 1 else ''}"
        if k == "strategy": return "Everyone in the top ten ran the same tyre strategy" if r["strategies"] <= 1 else f"{r['strategies']} different tyre strategies in the top ten"
        if k == "stakes":
            return "Championship very close afterwards" if r["stakes"] > .7 else "Championship fairly close afterwards" if r["stakes"] > .35 else "Little title pressure"
    for r in pool:
        comps = [{"key": k, "label": LABEL[k], "weight": W[k], "z": r["z"][k], "pts": round(W[k] * r["z"][k], 3), "stat": stat(r, k)} for k in keys]
        r["detail"] = {"factors": comps, "raw": round(r["score_raw"], 3),
                       "raw_range": [round(min(x["score_raw"] for x in pool), 3), round(max(x["score_raw"] for x in pool), 3)]}
    keep = ["round", "session_key", "name", "date", "locality", "country", "laps", "score", "tier", "front_pct", "pack_pct",
            "action_meter", "suspense_meter", "chaos_meter", "advice", "intensity_profile", "detail"]
    json.dump({"season": [{k: r[k] for k in keep} for r in season],
               "baseline_races": len(pool), "baseline_years": sorted({r["year"] for r in pool}), "season_year": cur}, open(os.path.join(HERE, "out", "races.json"), "w"), indent=1)
    json.dump(pool, open(os.path.join(HERE, "out", "debug.json"), "w"), indent=1, default=str)
    for r in sorted(pool, key=lambda r: -r["score_raw"]):
        print(r["year"], r["round"], r["name"][:24].ljust(24), r["tier"].ljust(10), r["score"],
              "F", r["front_pct"], "P", r["pack_pct"], "| pass/l %.2f lc %d margin %.1f late %.1f sc %d vsc %d dnf %d rain %s" % (
                  r["passes_per_lap"], r["lead_changes"], r["margin"], r["min_late_gap"], r["sc"], r["vsc"], r["dnfs"], r["rain"]),
              r["advice"]["text"])

if __name__ == "__main__":
    main()
