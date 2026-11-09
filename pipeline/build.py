import json, os
H = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(H, "out", "races.json")))
tp = os.path.join(H, "out", "tracks.json")
tracks = json.load(open(tp)) if os.path.exists(tp) else {}
for r in data["season"]:
    r["track"] = tracks.get(str(r["session_key"]))
    del r["session_key"]
pp = os.path.join(H, "out", "provisional.json")
prov = json.load(open(pp)) if os.path.exists(pp) else None
season_keys = {f"{data['season_year']}-{r['round']}" for r in data["season"]}
data["provisional"] = prov if prov and prov["key"] not in season_keys else None
cp = os.path.join(H, "out", "classics.json")
data["classics"] = json.load(open(cp)) if os.path.exists(cp) else None
t = open(os.path.join(H, "template.html")).read()
page = t.replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
# Claude adds its own document wrapper to replay-worthy.html; the public site needs a full document.
open(os.path.join(H, "out", "replay-worthy.html"), "w").write(page)
head = open(os.path.join(H, "site_head.html")).read()
open(os.path.join(H, "out", "site.html"), "w").write(head + page + "\n</body>\n</html>\n")
print("built")
