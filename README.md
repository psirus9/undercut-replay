# Undercut Replay

Spoiler-free ratings for every Grand Prix. Each race gets one of three verdicts, Snoozer, Worth It or Must Watch, so someone who missed it knows whether to watch the full race or just the recap. Results and winners never appear on the page.

## How it works

- `pipeline/` fetches timing data from OpenF1 (and Jolpica-F1 once it posts), scores each race, and builds the page.
- `site/index.html` is the built page, served by Firebase Hosting (`firebase.json`).
- `.github/workflows/refresh.yml` runs the pipeline on race weekends and commits the new page, and `deploy.yml` publishes it to Firebase. Deploys need a `FIREBASE_SERVICE_ACCOUNT_UNDERCUT_REPLAY` repository secret.

## Run it yourself

```
cd pipeline
bash run.sh
```

The last line says `PUBLISH: yes` when a new race was scored or the pre-race guess changed. Raw downloads go in `pipeline/raw<year>/` and are not committed. Scored races are cached in `pipeline/out/signals.json`, so only new races are fetched.

## Not yet wired up

Fan voting currently uses Claude's built-in storage, so it only works inside Claude. On the public site the vote buttons show a notice instead. Moving votes to Firebase or Supabase is the next step.

Not affiliated with, endorsed by or connected to Formula 1, the FIA or any team.
