# Independent client playback integration

Internal development on the authoritative fork. Client work takes priority;
GPU-free server development is deferred while the user seeks a hosted test server.
The overall Windows/Linux Internet gameplay goal remains unmet.

## Implementation

Commits `fb47c479` and `03ad32ea` connect the buffered motion controller to the
recovered-client installer and independent Linux native client. One existing
update owner drives playback. The private runtime first resolves the saved ship
and observes its actual initial position without applying the enrolment target.
Subsequent increasing XYZ samples include velocity for buffered prediction.
Native orientation transfer, constant velocity and AI suppression are not added.

The optional CLI path verifies the marked load and registry before claiming
admission. A separate worker owns the local motion UDP bridge; the main thread
continues polling admission and native participant controls. Playback starts only
after confirmed server resume. Source silence drains the final readback before
STOP; a server pause is refused until acknowledged STOPPED and validated final
evidence. Native cleanup precedes worker release and configuration redaction.

The private test source is the retained ENH-870 witness checkpoint, with registry
count 10082 and index 1318. Four archived saved MD scripts and the full content
configuration are pinned. This is a one-ship playback test, not a 10082-ship
synchronization test. The trajectory is synthetic: 25 position/velocity samples
over five seconds, requesting 20 metres along X from the native initial position.
The test requires the final sequence and an actual endpoint within three metres.

## Focused validation

The runtime/installer batch ran 31 tests: 30 passed and the new runtime test
initially failed because its fake UDP module lacked the required monotonic clock.
After fixing only the test double, that test passed all 12 subcases. The unchanged
batch was not repeated. The independent CLI/helper passed 15 focused tests with
zero skips, including real local UDP and the race where STOPPED arrives before
the final log record. No full-suite rerun was performed; earlier suite failures
and missing prerequisites remain open.

Logs remain in `../x4-client-playback-runtime-20261117/.local/` and the independent
client worktree. They establish component behavior, not native or cross-platform
success.

## Native attempt 01

`.local/private-client-playback-native-20261118-01/` loaded the checkpoint,
observed its marker and registry, and received admission. It failed before motion:
the reused UDP library from the older load-only harness lacked `socket.pending`.
The runtime correctly rejected it at `authority_recovered_client_motion.lua:182`;
resume then timed out. No playback movement was observed.

Owned processes, host thread, TLS, cgroup and private Xauthority were cleaned up.
Selected source pins, source checkpoint and Steam identity remained unchanged.
The failed result is retained. The directory date labels follow the prior harness
convention; this attempt ran on 17 November 2026.

The correction is a fresh library built from current `src/native/net.c`:
source SHA-256 `143185e4e0ef5e32aca4b000814b420ea71c374faa6dc3a193dcc3ca2e813191`,
binary SHA-256 `e325f982a2a34df045e3bca756dd4d2d9a91252cf3a5198fc1aa3f15eac0f032`.
The exact binary passed the existing real UDP pending/receive test and 1000
finite nondecreasing monotonic clock reads before a further native attempt.
Build arguments and proof are retained in
`.local/client-playback-native-library-20261117-01/proof.json`.

## Native attempt 02

`.local/private-client-playback-native-20261118-02/` used the corrected library.
It loaded, admitted and confirmed native resume. INITIAL and five summaries
recorded actual X4 playback: the last summary contained 618 readbacks and an X
position 19.3828125 metres beyond INITIAL. The five sampled readback errors were
below 0.004 metres. All 26 BIND messages (including enrolment) had arrived.
These summaries do not establish a maximum error across every frame or prove
visual smoothness.

The runtime faulted roughly 0.21 game seconds after the final sample, before
source-age draining and STOP confirmation. No successful final endpoint or pause
cycle was observed; the whole test failed. The generic fault erased the native
substage, so its cause is not established. A bounded offline reproduction using
the same initial XYZ, native float rounding, sample timing and final zero velocity
completed 667 readbacks and drained STOP. End-of-stream rounding alone therefore
has not reproduced the native fault. More precise fixed-stage diagnostics are
required before another native attempt.

Native processes, worker, host thread, TLS and outer cgroup were stopped. A
helper cleanup bug re-raised the already recorded operational error before
configuration redaction; its focused correction separates failure reporting from
teardown and preserves the failed result. Twelve helper tests passed. The empty
retained test lock was released only after checking recorded cleanup, absence of
X4 processes, ownership, timestamp and inode; `cleanup-reconciliation.json`
records that separate action. Original trial results were not changed.

## Diagnostic correction

Commit `25b18886` preserves the first fixed controller stage and native guard
substage through failure and STOP callbacks. Only allowlisted values are logged;
exception text, actor handles and connection tokens are excluded. No guard or
movement acceptance threshold was relaxed. Twenty-six affected tests passed in
0.530 seconds, including native-ABI zone/docking/fixture failures and reentrant
or throwing diagnostic observers. This enables a useful subsequent native test;
it does not by itself correct the unknown cause from attempt 02.

## Native attempt 03 and current boundary

`.local/private-client-playback-native-20261118-03/` used the fixed diagnostics
and cleanup, with the same current UDP library. On 18 November it again loaded,
admitted and resumed. The last of five summaries reported 623 readbacks,
19.390625 metres of X displacement, and sampled errors below 0.003 metres.
It then failed with `reason=owner_playback stage=distance native_stage=unknown`.
The next correction exceeded the 50-metre bound; this was not a failed native
identity, zone or docking check. The bound remains unchanged. The trial failed:
there was no drained STOP acknowledgement or final native pause cycle.

The cause of that large correction remains open. Native NPC motion is a plausible
interference source because this adapter only sets position and leaves the
client's simulation active. The log does not establish why the discrepancy arose
or retain the actual/target pair at the failed frame. A next diagnostic should
record that existing portable observation once on failure, without another native
read or unbounded per-frame logging. Do not rerun the unchanged trial or raise the
correction limit merely to obtain a passing result.

This run confirmed worker join, motion-configuration redaction and native/helper
cleanup despite the operational failure. Final evidence correctly stayed failed.
The conservative lock policy retained the empty test lock; recorded cleanup and
absence of X4 were independently checked before releasing it. The separate
`cleanup-reconciliation.json` preserves that audit. The checkpoint, selected
sources and Steam identity were unchanged; original results remain untouched.

A focused review of `../x4-playtest7/extension/x4_lan_lab/` found two relevant LAN
mechanisms. `ui/universe_game.lua` removes native NPCs and spawns separate inactive
replicas; this does not preserve the existing saved actor. `ui/coop_game.lua` and
`md/x4lan_coop.xml` instead refresh a short-lived constant velocity with expiry and
context checks. Neither reviewed path demonstrates suspend/resume of the same
saved NPC's AI. They are investigation inputs, not an adopted replacement for the
registry design. Discuss a change to actor identity or simulation ownership with
the user before adopting it.

All runs here used one actual Linux client, a synthetic trajectory and synthetic
host engine controls over loopback TLS. None tested a Windows client, WAN,
native server, visual smoothness, remote orientation, AI suppression, cross-sector
movement, trade, combat or boarding. The complete shared-world goal and earlier
full-suite issues remain unresolved.

Private manifests: `.local/authority-client-playback-reviewed-20261118-01.json`
through `-03.json`; private runner/trajectory files:
`.local/authority_client_playback_{trial,driver}_20261118.py`. Scope launchers for
02/03 have matching suffixes. These files, binaries, saves and private credentials
are not committed. Selected dependencies are checked before and after runs;
intermediate mutation and external cgroup migration are outside that evidence.
