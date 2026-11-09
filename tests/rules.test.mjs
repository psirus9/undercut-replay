import { initializeTestEnvironment, assertSucceeds, assertFails } from "@firebase/rules-unit-testing";
import { doc, runTransaction, writeBatch, getDoc, setDoc, collection, getDocs, query, where } from "firebase/firestore";
import fs from "fs";
const env = await initializeTestEnvironment({ projectId: "undercut-replay", firestore: { rules: fs.readFileSync(new URL("../firestore.rules", import.meta.url), "utf8"), host: "127.0.0.1", port: 8085 } });
const R = "2026-20";
async function vote(db, uid, k) {
  return runTransaction(db, async tx => {
    const bRef = doc(db, "ballots", `${R}_${uid}`), tRef = doc(db, "tallies", R);
    const b = await tx.get(bRef), tl = await tx.get(tRef);
    const was = b.exists() ? b.data().t : -1; if (was === k) return;
    const c = tl.exists() ? { c0: 0, c1: 0, c2: 0, ...tl.data() } : { c0: 0, c1: 0, c2: 0 };
    if (was >= 0) c["c" + was] -= 1; if (k >= 0) c["c" + k] += 1;
    tx.set(bRef, { race: R, uid, t: k }); tx.set(tRef, c);
  });
}
const ok = (n, p) => p.then(() => console.log("PASS", n), e => { console.log("FAIL", n, e.message); process.exitCode = 1; });
const alice = env.authenticatedContext("alice").firestore(), bob = env.authenticatedContext("bob").firestore(), anon = env.unauthenticatedContext().firestore();
await ok("alice votes Must Watch", assertSucceeds(vote(alice, "alice", 2)));
await ok("bob votes Snoozer", assertSucceeds(vote(bob, "bob", 0)));
await ok("alice changes to Worth It", assertSucceeds(vote(alice, "alice", 1)));
await ok("alice clears", assertSucceeds(vote(alice, "alice", -1)));
await ok("alice votes again", assertSucceeds(vote(alice, "alice", 2)));
await ok("anyone reads tallies", assertSucceeds(getDoc(doc(anon, "tallies", R))));
const t = (await getDoc(doc(anon, "tallies", R))).data(); console.log("tally", JSON.stringify(t));
if (t.c0 !== 1 || t.c1 !== 0 || t.c2 !== 1) { console.log("FAIL tally values"); process.exitCode = 1; }
await ok("alice reads own ballots", assertSucceeds(getDocs(query(collection(alice, "ballots"), where("uid", "==", "alice")))));
await ok("BLOCK signed-out vote", assertFails(vote(anon, "x", 2)));
await ok("BLOCK stuffing tally alone", assertFails(setDoc(doc(alice, "tallies", R), { c0: 1, c1: 0, c2: 99 })));
await ok("BLOCK ballot without tally", assertFails(setDoc(doc(alice, "ballots", `${R}_alice`), { race: R, uid: "alice", t: 0 })));
const b = writeBatch(alice); b.set(doc(alice, "ballots", `${R}_alice`), { race: R, uid: "alice", t: 0 }); b.set(doc(alice, "tallies", R), { c0: 5, c1: 0, c2: 0 });
await ok("BLOCK ballot with inflated tally", assertFails(b.commit()));
const b2 = writeBatch(alice); b2.set(doc(alice, "ballots", `${R}_bob`), { race: R, uid: "bob", t: 2 }); b2.set(doc(alice, "tallies", R), { c0: 0, c1: 0, c2: 2 });
await ok("BLOCK voting as someone else", assertFails(b2.commit()));
await ok("BLOCK reading others' ballots", assertFails(getDoc(doc(alice, "ballots", `${R}_bob`))));
await ok("BLOCK bad race key", assertFails(runTransaction(alice, async tx => { tx.set(doc(alice, "ballots", "hack_alice"), { race: "hack", uid: "alice", t: 2 }); tx.set(doc(alice, "tallies", "hack"), { c0: 0, c1: 0, c2: 1 }); })));
await env.cleanup();
