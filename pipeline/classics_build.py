"""Turn out/classics_signals.json into the page's Classics data: out/classics.json.

Past seasons only (the current season lives on the main board). Keeps the overall top 25
plus each era's top 10, with spoiler-free fields only.
"""
import json, os, sys
import classics

H = os.path.dirname(os.path.abspath(__file__))

def advice(it):
    tot = sum(it[3:]) or 1; acc = 0; start = None
    for i in range(len(it) - 1, 2, -1):
        acc += it[i]
        if acc / tot >= .60:
            start = i + 1; break
    if start and (len(it) - start + 1) / len(it) <= .5:
        return {"kind": "from", "lap": start, "text": f"Start at lap {start} of {len(it)}"}
    return {"kind": "full", "text": "Watch the whole thing"}

def main(current_year):
    R = [r for r in json.load(open(os.path.join(H, "out", "classics_signals.json"))) if r["year"] < current_year]
    classics.mark_wet(R)
    classics.score(R)
    R.sort(key=lambda r: -r["score_raw"])
    for i, r in enumerate(R, 1):
        r["rank"] = i
    by_era = {}
    for r in R:
        by_era.setdefault(classics.era_of(r["year"]), []).append(r)
    keep = {id(r) for r in R[:25]}
    for era, rs in by_era.items():
        for i, r in enumerate(rs, 1):
            r["era_rank"] = i
        keep |= {id(r) for r in rs[:10]}
    out = []
    for r in R:
        if id(r) not in keep:
            continue
        it = r["intensity"]
        step = max(1, len(it) // 24)
        out.append({
            "rank": r["rank"], "era_rank": r["era_rank"], "era": classics.era_of(r["year"]),
            "era_size": len(by_era[classics.era_of(r["year"])]),
            "year": r["year"], "name": r["name"], "locality": r["locality"], "country": r["country"],
            "laps": r["laps"], "wet": r["wet"], "title_live": r["title"] >= 3,
            "advice": advice(it),
            "profile": [round(sum(it[i:i + step]), 1) for i in range(0, len(it), step)],
        })
    eras = [{"label": label, "from": a, "to": min(b, current_year - 1), "races": len(by_era.get(label, []))}
            for a, b, label in classics.ERAS if label in by_era]
    json.dump({"races": out, "eras": eras, "total": len(R), "first_year": min(r["year"] for r in R),
               "last_year": max(r["year"] for r in R)}, open(os.path.join(H, "out", "classics.json"), "w"))
    print(len(out), "classics kept from", len(R), "races")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
