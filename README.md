# Replay Undercut

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

## Fan votes

On the public site, fans sign in with Google and vote Snoozer, Worth It or Must Watch. Votes live in Firestore: one private ballot per person per race, plus public counts. `firestore.rules` makes sure a ballot and its count always change together, so the counts can't be stuffed. `tests/` checks this against the emulator. Inside Claude, the page uses Claude's own storage instead.

Rules are not deployed by the workflows. After changing `firestore.rules`, paste it into Firestore > Rules in the Firebase console and publish.

Not affiliated with, endorsed by or connected to Formula 1, the FIA or any team.
