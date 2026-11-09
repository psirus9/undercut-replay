#!/bin/bash
# Replay Worthy refresh: score any newly finished race (OpenF1 first, Jolpica when posted),
# update the next race's pre-race guess, draw circuits, rebuild the page.
# Last line says whether there is anything to publish.
set -e
cd "$(dirname "$0")"
python3 fetch.py || { code=$?; [ $code -eq 3 ] && echo "NEW RACES: none (data locked, a session is live)" && echo "PUBLISH: no"; exit $code; }
python3 score.py > out/scored.txt
NEW=$(grep "^NEW RACES:" out/scored.txt); echo "$NEW"
PROV=$(python3 provisional.py); echo "$PROV"
python3 tracks.py | tail -1 || true
python3 build.py
if [[ "$NEW" != "NEW RACES: none"* ]] || [[ "$PROV" == "PROVISIONAL CHANGED"* ]]; then echo "PUBLISH: yes"; else echo "PUBLISH: no"; fi
