# Vote rules test

Checks `firestore.rules` against the Firestore emulator: normal voting, changing and clearing a vote, and that cheating is blocked (stuffing counts, voting as someone else, voting signed out, reading other people's ballots).

```
npm i firebase-tools@13.29.1 @firebase/rules-unit-testing@3.0.4 firebase@10.12.2
npx firebase emulators:exec --only firestore --project undercut-replay "node tests/rules.test.mjs"
```
Needs Java. The test reads `firestore.rules` from the folder you run it in.
