"""Infer neutralised laps (safety car / VSC / red flag) and pit laps from lap times alone.

Used for races before the timing feeds had race control and pit data.
"""
import statistics as st

def neutral_laps(laptimes, total_laps):
    """laptimes: {lap: {driver: seconds}}. Returns (set of neutral laps, list of deployments, red_flags)."""
    med = {}
    for L in range(1, total_laps + 1):
        t = [v for v in laptimes.get(L, {}).values() if v]
        if len(t) >= 3:
            med[L] = st.median(t)
    if len(med) < 5:
        return set(), [], 0
    # green pace: lower-quartile of lap medians, robust to SC laps and fuel burn
    base_all = sorted(med.values())
    base = base_all[len(base_all) // 4]
    neutral, red = set(), 0
    for L, m in med.items():
        if L == 1:
            continue
        if m > base * 2.5:
            red += 1; neutral.add(L)
        elif m > base * 1.16:
            neutral.add(L)
    # deployments = starts of runs of neutral laps
    deploy = [L for L in sorted(neutral) if L - 1 not in neutral]
    # a neutral period is followed by a slow restart lap; single isolated slow laps that are
    # really weather or traffic are kept, they still mean the field bunched up
    return neutral, deploy, red

def pit_laps(laptimes, neutral):
    """Infer in-laps per driver: a lap far slower than that lap's median, outside neutral laps."""
    pit = {}
    for L, row in laptimes.items():
        t = [v for v in row.values() if v]
        if len(t) < 3 or L == 1:
            continue
        m = st.median(t)
        thresh = m + (12 if L not in neutral else 18)
        for d, v in row.items():
            if v and v > thresh and v < m * 2.5:
                pit.setdefault(L, set()).add(d)
    return pit
