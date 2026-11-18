# Independent client playback integration

Internal development on the authoritative fork. Client work takes priority;
GPU-free server development is deferred while the user seeks a hosted test server.
The overall Windows/Linux Internet gameplay goal remains unmet.

Current client increment, 18 November: both the independent bounded live-input
path and an explicit paired-supervisor playback path are now wired in code.
The paired path uses the existing retained TCP owner and fresh join checkpoint.
Native paired attempt 03 exercised the synchronous-guard optimization: source
binding fell from 34.062s to 2.787s and initial verification from 6.905s to
1.272s. The run still hit the source diagnostic deadline in collection after
25.348s, with one prevalidated sample and zero confirmed client receipts; it
does not establish TCP transmission or a native client refusal. Its 24
checkpoint metadata checks took 12.718s, 192 full guards 11.360s, and source
collection 15.051s. Cleanup, Xauthority cleanup, and pinned-source preservation
were confirmed. The optimization was exercised, but paired movement was not.
Native08 remains the latest passing client playback, using synthetic host
controls. Windows and Internet gameplay remain unproven. The separate offline
[clock-basis observation](AUTHORITY-MOTION-CLOCK-BASIS-20261118.md) records a
playback errors under synthetic unequal clock rates; the user's protocol decision is pending and
no protocol change has been made.

## Native paired attempts, 18 November

Attempt 01 published a fresh server checkpoint but rejected its changed registry
mapping hash before launching the client. The correction in `ba16b0e7` keeps
exact typed ready-state, epoch and count checks and accepts the fresh mapping
already admitted by the checkpoint/witness guard. Eight focused tests passed in
0.020s and a read-only preflight against the retained client inputs passed.
Evidence: `.local/private-paired-playback-native-20261118-01/` and
`../x4-paired-playback-lineage-20261118/.local/retained-playback-lineage-preflight-20261118.json`.

Attempt 02 used the same pinned private Wait/release artifacts and the corrected
installer. The native client loaded the new `save_009` and reported the expected
marker, 10,082-entry register and paused state. The source diagnostic then
failed with `playback sampling deadline expired` during `register_source`:

- 60.044 seconds elapsed: initial verification 6.905s, source binding 34.062s,
  and registration 19.078s.
- 59 aggregate guard calls accounted for 42.691s; two checkpoint metadata
  requests accounted for 11.155s. These are diagnostic timings, not isolated
  component benchmarks or universe simulation performance.
- Zero source samples, pull attempts or client receipts were recorded. No
  playback, release observation or successful departure save is established.

Both failed attempts confirmed source/pin preservation, Steam identity and
owned-process/Xauthority cleanup. Attempt 02 left no X4 executable process or
global X4 lock. Evidence:
`.local/private-paired-playback-native-20261118-02/{result.json,trial-result.json,paired-server/result.json}`.
The follow-up audit found repeated full `/proc` discovery inside nested guards.
Five harmless measurements with 478 current processes averaged 9.64ms per scan.
Static call expansion estimates about 62 scans per aggregate source guard,
consistent with its measured 0.724s average. This supports the diagnosis but
is not native per-function timing attribution.

The correction exercised in attempt 03 (`e0f6f9e1`) uses full discovery at entry/exit of each synchronous
aggregate guard, with fresh targeted launcher/X4 PID, start time, UID,
executable, group and session checks inside. It is enabled only for paired
playback and never spans a socket wait or the entire sampling window. It
assumes exclusive ownership of the private process set: an extra X4 process
that appears and exits between those boundaries can be missed. The normal
path is restored before client teardown; protected-file and save checks and
all timeouts are unchanged. `8f5530c9` also retains cancellation combined with
an exit-check failure in the failed supervisor result.

Seven final guard/lifecycle tests passed in 0.111s, including two harmless real
Python process groups, identity changes, teardown, and cancellation/exit failure.
The existing real local UDP/TCP 26-sample fixture also passed with its actual
checkpoint pump invoking the scope (earlier seven-test batch: 6.498s).
Logs: `../x4-playback-discovery-scope-20261118/.local/discovery-scope-cancellation-focused-20261118.log`
and `discovery-scope-focused-20261118-02.log` in the same directory. These are
not X4 results. Attempt 03 subsequently exercised the correction in X4.

Attempt 03 again loaded the fresh join checkpoint and reported its marker,
registry and paused state. The source returned one valid UDP sample, but
`source diagnostic deadline` ended the first pull after 15.051s. No client
Wait/playback/motion records or confirmed receipts followed the load/pause
records. The retained counters do not distinguish pre-send checks from a TCP
exchange already in progress, so neither TCP dispatch nor native refusal is
established. Its 24 checkpoint requests invoked 225 client pump checks;
repeated nested validation remains the next performance investigation.
All owned processes were cleaned up; a subsequent read-only check found no
X4 process or global X4 lock. Evidence:
`.local/private-paired-playback-native-20261118-03/{result.json,trial-result.json,paired-server/result.json}`.

A bounded offline trace of the existing real TCP/UDP fixture subsequently
counted actual socket sends and confirmed sample observations:

| Boundary | Aggregate guards | Checkpoint checks |
| --- | ---: | ---: |
| First TCP snapshot send | 192 | 24 |
| First confirmed sample | 228 | 30 |
| Each later confirmed sample, delta | 142 | 23 |
| Complete 26-sample flow | 3,841 | 611 |

The native03 counters coincide with the fixture's first-send boundary. This
narrows the investigation but still cannot show whether the native send occurred.
The fixture's baseline took 6.423s. A private variant with two harmless real
Python process groups and full discovery around each pull completed in 12.014s
(828 full group discoveries). It uses one fixture pump per checkpoint, whereas
native03 averaged 9.375 pumps per request. Protected-file checks are stubs and
there is no real checkpoint helper or `PlaybackSamplingWindow` in this variant.
Neither time predicts native performance. Reproduction and JSON counters:
`../x4-playback-discovery-scope-20261118/.local/measure_paired_guard_counts_20261118.py`
and `guard-counts-{counts,pull_scope}-20261118.json` in that directory.

The source probe now applies that discovery scope to each single playback pull,
including its UDP/TCP waits. Nested checks still reread known process identities;
an additional X4 may be discovered only after a client effect, or missed if it
exits before the boundary. This relies on exclusive ownership of the isolated
processes. Scope exit is charged to the unchanged sampling deadline; normal
checks remain outside pulls. The actual changed 26-sample TCP/UDP fixture passed
in 6.426s (`.local/paired-pull-scope-focused-20261118.log`). This test checks
scope nesting and observation after exit, with simulated engine edges. Review
caught the optional scope callback being called unconditionally; the correction
retains the unscoped path. A separate real TCP/UDP test of that path passed in
6.421s (`.local/paired-pull-no-scope-focused-20261118.log`). No new
native run has been performed; remaining helper/file costs need accounting
before deciding whether another expensive native attempt is justified.

A subsequent bounded helper measurement used the actual `WitnessGuardClient`,
`WitnessGuardPump` and `PlaybackSamplingWindow`, tiny synthetic valid checkpoints,
and two harmless Python process groups. Its 598 metadata calls (26 batches of
23) took 4.524s; total open/check/STOP/close time was 4.634s. Each request invoked
nine pump checks (5,382 during metadata requests). The batches used 104 full
group discoveries and took 0.172–0.178s each. Full STOP, window close and reader
release succeeded under the existing 10s window and 20s helper deadlines.
There was no TCP flow in this fallback; protected/native context checks remained
stubs apart from real process identities and save pins. It measures helper cost,
not native performance. Evidence in the same measurement worktree:
`.local/guard-counts-real_window-20261118.json` and
`.local/guard-real-window-measurement-20261118.log`.

The following private diagnostic change removes repeated full-context checks
inside peer validation and helper wait pumps. `check_active_liveness` retains
the same worker, admitted membership and IPC checks, bracketed by game identity
and deadline checks. Its lifetime is the existing retained-worker callback;
cleanup and worker STOP invalidate both entry points. The source IPC retains
full guards before and after checkpoint calls. Window-open and checkpoint-STOP
are enclosed by the outer full guards; worker STOP uses its original path.
Protected file, registry and client-log changes during a final lightweight peer
check are detected at the next full boundary, potentially after dispatch. The
ordinary path and all diagnostic deadlines are unchanged.

Focused offline tests covered worker exit, membership loss, unexpected IPC,
identity loss, cleanup, source socket ownership and the full 26-sample TCP/UDP
flow with ordered drain. The new adapter test initially omitted the source UDP
connection; after correcting that fixture, its five fault variants passed.
An independent read-only review found no unguarded helper operation or lifecycle
leak. These tests use simulated X4 processes and do not establish native motion.

A single updated count trace recorded 94 full guards at the first actual TCP
send, 106 at the first ACK, and 1,395 for the complete flow (previously 192, 228
and 3,841). The complete flow still made 611 checkpoint calls. It made 3,057
lightweight checks and 6,114 source process checks, with one simulated helper
pump per checkpoint. It passed in 6.420s, but protected context and helper costs
are stubs in this trace. Evidence:
`.local/paired-liveness-count-20261118/guard-counts-liveness-counts-20261118.json`;
reproduce from the repository root with
`X4_MEASURE_CODE_ROOT="$PWD" python .local/paired-liveness-count-20261118/measure.py counts`.
A subsequent single offline profile executed the actual `check_live_context`
ten times within one discovery scope: two real Python groups stood in for X4,
Steam identity was checked live, and 30 retained client files (211,131 bytes)
were hashed on each invocation. Median/max were 0.787/0.850ms. The complete
scope took 43.476ms, including its two group scans. The latter is one observation,
not a representative distribution. Real save metadata was replaced by a small
private file stat; registry/log, witness/server and IPC checks were excluded.
Six such contexts per aggregate guard would account for roughly 6.59s over the
counted flow; this is a partial cost estimate, not an end-to-end prediction.
Evidence: `.local/private-client-context-profile-20261118/context-profile-result.json`.

Paired native attempt 04 ran with manifest
`.local/authority-paired-playback-reviewed-20261118-05.json`, unchanged time limits
and success criteria. It **failed** with
`paired playback initial offset exceeds fixture bound`. Unlike attempt 03, it
confirmed one actual client receipt and logged client Wait/timing/zero-velocity
request and INITIAL records. The first source pull completed in 1.341s; the
observer rejected the initial source/client distance as greater than 50m.
This is total pull time including validation, not isolated network latency.
The complete diagnostic took 11.561s: initial verification 1.220s, bind 2.916s,
register 5.963s and collection 1.462s. It recorded 114 aggregate guards and 34
checkpoint checks. Only one source sample was prevalidated and one receipt
confirmed; zero samples passed the playback observer. No continuous source-led
movement, full 26-sample timing, STOP/release or departure save was demonstrated.

The client INITIAL position was (-115822.9140625, -5642.81982421875,
127614.65625) at client game time 20.995694222. The source sample was not retained
on this error path, so the exact distance, direction and source sampling time
cannot be reconstructed from these artifacts. Independent client motion during
binding is a hypothesis, not an established diagnosis. The fixture bound remains
50m. A follow-up now retains a bounded source/client comparison before enforcing
that bound, including both positions, game times and measured separation; it
does not count a rejected sample as accepted. All six evidence tests passed.
The diagnostic addition was subsequently exercised in attempt 05 below.

An independent read-only comparison found that the source descriptor and client
adapter both read XYZ through `GetObjectPositionInSector` with the same
`UIPosRot` float structure; the sampler transfers XYZ unchanged. No axis swap,
unit multiplier or zone/world conversion is visible in that path. This does not
independently prove cross-process frame or actor identity. The comparison is
also not simultaneous: the source is sampled before transport/binding, whereas
client INITIAL follows binding and the private Wait/timing intervention. That
asymmetry supports investigating simulation drift, but the missing source pose
and time prevent attributing native04's rejection to it.

Outer cleanup, Xauthority cleanup, source preservation, source-code pins and
Steam identity checks passed. A subsequent process scan found no X4 process or
global X4 lock. The run remains an overall failure. Evidence:
`.local/private-paired-playback-native-20261118-04/{result.json,trial-result.json,paired-server/result.json}`.

### Paired native attempt 05: measured initial offset

One further two-X4 Linux attempt used manifest
`.local/authority-paired-playback-reviewed-20261118-06.json`. It **failed** the
unchanged 50m initial alignment bound after one prevalidated source sample and
one confirmed client receipt. Zero samples passed the playback observer. The
new error-path diagnostic retained the comparison in both the supervisor and
trial results:

| Observation | Source sample | Client INITIAL |
| --- | ---: | ---: |
| X (m) | -115815.375 | -115773.5234375 |
| Y (m) | -5625.779296875 | -5565.68505859375 |
| Z (m) | 127603.671875 | 127554.71875 |
| Own game time (s) | 20.784212683999964 | 21.672679077999963 |

The measured separation was **88.08677088848634m**. These observations were not
simultaneous: source sampling precedes transport and client binding. Their game
times differ by about 0.888s, but are separate simulation clocks; dividing the
distance by that difference would not establish ship velocity or network delay.
There is no earlier matched pose pair for this attempt, so it does not isolate
load-time divergence, later independent NPC movement, or frame/identity error.

A subsequent read-only inspection used the checkpoint actually offered and
staged for this client, SHA-256
`2ebbcea67f4993c8da7f93661779ca8f3a9539d1f59a865ca811b71f852e7af0`.
Its forward and reverse registry entries map index 1318 to saved component
`[0x7841d]`, the Antigone ship ENH-870, and back. The saved game-time attribute
is `7.09`. Its parent is `zone003_cluster_06_sector001_macro`; the ship-offset
position is (-31102, -7052.023, 35448.031), while the distinct movement read/write
position is (-31082.139, -7038.869, 35429.68), with stored linear velocity
(101.213, 67.1674, -93.801). These are raw saved fields, not live measurements.
The zone offset uses `default="1"`; the zone-to-sector transform and the meaning
of the two position fields were not established. Thus these values cannot yet
be directly compared with the live sector positions or diagnose the 88m gap.
No X4 run or save modification was made for this inspection. Selected evidence
and the executed query bodies are retained in
`.local/paired-initial-save-evidence-20261118-01/`; its `result.json` SHA-256 is
`1947153befeb5ef6ffaa348716dd9329a50e150c6c3a18c903e4c9b0577f18e5`.

The client logged Wait ready, a later-tick observation, a zero-velocity request,
then INITIAL. Those records do not prove the physical effect of the velocity
request. No continuous paired playback, 26-sample sequence, STOP/release or
departure save was reached. The complete source diagnostic took 12.100s;
initial verification, binding, registration and collection took 1.276s, 3.077s,
6.266s and 1.481s. The first pull took 1.353s including validation. The record
contains 114 aggregate guards and 34 checkpoint checks. These are diagnostic
costs, not a representative gameplay or dedicated-server benchmark.

Outer cgroup and Xauthority cleanup, unchanged code pins, original source
preservation and Steam identity checks passed. The supervisor recorded no owned
processes remaining; a subsequent independent executable scan found no X4 and
the global X4 lock was absent. The coordinator's
`display_released_after_runner` remains false: its graceful display release is
conditional on runner success, which did not occur. Outer cleanup is separate.
Both outer `observation_valid` and overall `success` remain false.

Private evidence root: `.local/private-paired-playback-native-20261118-05/`.
SHA-256 values:

- `result.json`: `0b8ce23d765adc77f64c776ad2720867f0f9ccd04c2cb57315e2ecf3b0f31c9a`
- `trial-result.json`: `7c52fbfe7aba5321f1f1318390c6f4d06151bd6b6cea3de80f8781a2c09c57fc`
- `paired-server/result.json`: `0007ee7fed11c8e611f6eeab8b2672f247c79daf4f080c6e80460e5c862a39a7`

The earlier LAN client uses a different takeover method. In the local reference
`../x4-playtest7/extension/x4_lan_lab/ui/universe_game.lua`, lines 193–200 spawn
a separate replica at the received pose, call `ActivateObject(replica, false)`
and correct its pose; lines 225–231 remove local NPC originals. The retained
`sensor-fix-motion-guest-bc90d2e/result.json` reports 201 NPC samples and maximum
position error 1.473m. That supports the old replica path, not safe takeover of
the same saved actor. The current private paired binder instead requests Wait
and zero velocity on the existing actor, after binding begins. Replacing saved
actors, introducing an initial snap, or changing the motion clock has not been
authorized by this test. The outstanding user decisions remain pending; no
threshold or protocol change was made, and no repeat run was started.

A separate read-only code review tightened intermediate native readbacks:
each SUMMARY now independently checks actual-to-target distance, and log reads
must finish within the local/overall deadline with the guard still valid.
All six tests in `tests.test_authority_paired_playback_evidence` passed. This
change was integrated after attempt 02. Attempt 03 did not reach client readbacks.

## Paired source and client integration, 18 November

The shared supervisor accepts `--diagnostic-saved-playback` only for one private
witness-join client, registry index 1318, and ordinary repeated source sampling.
Local-pair and one-shot setter modes are mutually exclusive with playback.
The fresh join ticket, marker and saved registry remain verified by the existing
admission path. Playback pins the content XML and four compatible MD scripts;
registry lineage requires exact typed ready-state, epoch and count fields plus a
valid lowercase mapping hash bound through the fresh-checkpoint witness. It does
not substitute the historical native08 save hash for the fresh checkpoint.

This path uses `LazyMotion` directly, not the independent `NativePlayback`
worker or its queue. The first actual source packet, sequence 1, is unchanged
and serves only as enrollment; Lua discards its pose. After its TCP receipt,
the observer requires client INITIAL and an initial source/client distance no
greater than 50 metres. Source packets 2–26 retain their sequence, generation,
game time, XYZ and nullable velocity. There is no synthetic enrollment packet
or sequence translation in this paired path.

The diagnostic attempts 26 confirmed source samples, paced at 0.2 real seconds,
within a 15-second sampling deadline. Source STOP precedes a 1.25-second silence,
the checkpoint helper's full-check STOP, and client worker STOP. Read-only log
correlation requires native movement and a final frozen target consistent with
the last actual source pose and the existing 0.35-second prediction horizon.
TCP receipts alone cannot pass this check. The departure pause and save must
still succeed before the overall supervisor result succeeds.

Repeated compressed-save hashes were identified in the diagnostic guard path;
this is harness overhead, not evidence of excessive X4 universe simulation cost.
`PlaybackSamplingWindow` pins the two private read-only input saves and brackets
at most 60 seconds with full digest checks. During that phase it checks file
identity/metadata, original checkpoint pointers/manifests and the fresh checkpoint
helper, retaining process, membership, script and IPC checks. Its helper request
scope permits the existing pump's nested local-save check without adding a
reader. Failure remains sticky. This assumes exclusive writers and FD ownership;
metadata is not proof that all intervening bytes were unchanged.

The private native08 Wait/velocity intervention and release observer are not
installed by this new switch. Native paired attempt 01 failed before the client
was launched, so it produced no source samples, playback, release observation
or departure pause/save. The runner did confirm unchanged source pins and
owned-scope/Xauthority cleanup. The narrow fresh-mapping-hash fix is covered by
8 focused tests (0.020s), a passing retained-checkpoint preflight and attempt
02 progressing through native client load. The subsequent diagnostic timeout
is detailed above. General NPC authority and exact AI/velocity restoration
remain unresolved.

Focused validation, without an expensive full-suite rerun:

- Paired client configuration/installation and real TCP-to-UDP forwarding:
  **40 tests passed in 6.115s**. Log:
  `../x4-paired-client-playback-20261118/.local/paired-playback-focused-20261118.log`.
- Source probe regression: **20 tests passed in 7.245s**, including the real
  local TCP/UDP 26-sample flow, with simulated source and client engine edges.
  Log: `.local/paired-source-regression-20261118.log`.
- Supervisor gates/finalization: **36 tests passed in 0.289s**. Log:
  `.local/paired-supervisor-only-20261118.log`. The preceding combined command
  passed its 12 playback tests but failed to import the supervisor tests without
  `PYTHONPATH=tests`; only the affected supervisor module was rerun.
- After the helper STOP hook was connected, **15 final focused tests passed in
  7.132s**: the 26-sample source flow, evidence parser and metadata window. The
  real checkpoint helper exercises its production pump and retained client
  save checks through CHECK, metadata CHECK and full STOP. Log:
  `.local/paired-playback-final-20261118.log`.

No tests in these batches were skipped. Readback logs/engine behavior in these
new tests are simulated; native08 evidence remains separate. Earlier full-suite
failures and unavailable prerequisites have not been resolved by these checks.

## Live input integration, 18 November

`LiveSourceInput` accepts unchanged portable source samples through either its
explicit producer API or the existing admitted TCP motion callback. The worker
keeps the original source sequence/time/velocity in bounded provenance while
mapping enrollment and deliveries to its local UDP sequence. Unknown initial
velocity remains unknown. It rejects a first correction beyond the existing
50-metre fixture bound, stale input, overflow, changed identity and regressing
source times. EOF enters the existing silence/readback/STOP sequence. The
temporary NPC control intervention remains private and is not installed here.

Queue acceptance, local UDP binding and native movement are separate outcomes.
Partial dispatch evidence survives failure. Producer failures remain visible
after STOP, and a failure discovered during worker join now makes the outer
result fail even when resource cleanup succeeds. No native outcome from an older
trial is attributed to this input path.

Validation was split to avoid repeating unchanged checks:

- The stream/playback worker batch passed **22 tests in 4.197 seconds**. It uses
  the real worker with simulated IPC/native edges, plus the existing local UDP
  playback test. Log: `../x4-client-live-source-20261118/.local/live-source-focused-20261118.log`.
- After integration, the owner/native-orchestration batch passed **26 tests in
  4.049 seconds**. Real TCP tests verify original samples through admission into
  the queue and refuse receipts for unready, closed or overflowing input. Native
  load/lifecycle is simulated; existing local UDP control is also covered.
  Log: `.local/client-live-input-integration-20261118.log`.
- Both batches passed with no skips. No X4, Windows, WAN or full-suite rerun was
  performed. Earlier full-suite failures and missing prerequisites remain open.

The paired integration above reuses the one-lock/two-process ownership in
`authority_recovered_loopback_server.py` and `authority_recovered_server_client.py`.
Launching two independent CLIs would conflict with their ownership checks. That
supervisor already verifies the fresh join ticket/marker against the confirmed
checkpoint. It connects registry and compatible-script lineage to the playback
fixture without replacing the old pinned save hash. It uses the normal source
sampler for repeated actual samples: optional `local_pair` delivery stops
after one two-point estimate. Keep source STOP, client drain/STOP, private release
observation and pause ordered. Native verification of the paired path remains
outstanding; no new native trial has been attempted.

## Implementation

Commits `fb47c479` and `03ad32ea` connect the buffered motion controller to the
recovered-client installer and independent Linux native client. One existing
update owner drives playback. The private runtime first resolves the saved ship
and observes its actual initial position without applying the enrolment target.
Subsequent increasing XYZ samples include velocity for buffered prediction.
The production path adds no native orientation transfer, constant-velocity
override or AI suppression.

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

## Native attempt 03

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

## Native attempt 04: actual position discontinuity

Commit `5197fe0c` adds one fixed-schema distance-failure observation, captured
before STOP or logging callbacks. It uses the existing pre-write observation,
without another native read. Twenty-three affected component tests passed in
0.476 seconds, including an error logger that changes the fake native position,
reenters playback and throws. The recorded observation remains unchanged and
appears once. Movement limits and simulation ownership are unchanged.

`.local/private-client-playback-native-20261118-04/` repeated the same trajectory
with this diagnostic. It loaded, admitted and resumed, then failed again. At
game time 12.340859136 the actual position was
`(-116447.15625, -6606.46630859375, 128369.34375)` and the target remained
`(-116819.9609375, -7030.31640625, 128794.09375)`: exactly INITIAL plus the
commanded 20 metres along X. The measured discrepancy was 706.431031882 metres,
with source sequence 26, phase `extrapolated` and `uncertain=0`.

This identifies a discontinuity in the position read from X4, rather than a
jump in the computed target. It does not identify which engine activity moved
the actor. The complete playback/STOP/pause test still failed. Owned process,
helper, host, TLS and display cleanup were confirmed, and checkpoint and selected
sources remained unchanged. The empty retained lock was independently reconciled;
original failed results remain intact.

Local X4 schema and installed `order.wait.xml` support a finite immediate Wait
order on the existing ship. That is a candidate for one disposable interference
diagnostic. Immediate orders restart the interrupted order afterward; they do
not promise exact AI-stack restoration, physics suppression or immediate entry
when the prior order is critical. No general client NPC policy has been adopted.

## Native attempt 05: finite Wait is insufficient

The private binder override in `.local/private-client-playback-native-20261118-05/`
created one immediate Wait on the same verified saved ship, with a 15-second
game-time timeout, no fidget/alignment and no attack response. A later callback
observed the captured order as current before allowing binding and INITIAL.
The default installer/runtime have no Wait feature. The override was installed
before protected hashing, with pinned source bytes, a successful full MD schema
validation and two focused real-installer tests. No ship was replaced or saved.

X4 reported WAIT READY at game time 7.20536. Playback again failed: source
sequence 26 targeted exactly INITIAL plus 20 metres, but the native position
differed by 713.410317334 metres at game time 12.401091873. A confirmed finite
Wait alone therefore did not prevent this discontinuity. The test ended before
expiry observation; AI-state restoration was not tested or claimed.

Commit `15d08e86` separates invalid final evidence from cleanup failures. Seven
focused CLI tests passed, including seven evidence-failure/cleanup scenarios. Native05
confirmed the intended failure path: evidence remains failed, native/helper/host/
TLS/display cleanup and source integrity pass, and the original owned lock is
released automatically. Unknown cleanup or changed inputs/Steam/lock identity
still prevent release. The failed run was not reclassified as successful.

An existing NPC constant-velocity experiment had used an invalid `0m / 1s`
expression. Its correction uses the installed stock zero-vector expression;
four affected tests passed. Its historical native result remains inconclusive.
Stock game scripts also defer velocity assignment until two frames after a Wait
order to avoid replacement of the velocity controller. This motivated the
following private Wait-plus-zero-velocity contrast, without choosing a general
NPC ownership mechanism.

## Native attempt 06: bounded playback succeeds with a private override

`.local/private-client-playback-native-20261118-06/` added one request for
constant zero linear velocity to the private finite-Wait binder. It used the
stock `vector.[0m, 0m, 0m]` syntax, left angular velocity untouched, and retained
the same actor/registry/sector/zone/player/docking checks and movement bounds.
The private XML/wrapper were separately pinned; XML well-formedness and two
focused installer tests passed. No production NPC policy was installed.

The bounded trial passed: native load/admission/resume, 25 delivered trajectory
samples (26 received including enrolment), 752 observations and 644 readbacks,
an exact INITIAL-plus-20-metre endpoint, and STOPPED with `drained=1 uncertain=0`.
The final endpoint error was zero in the reported float coordinates. One native
resume and one later native pause were confirmed; this does not establish a
second native resume after that pause. Native, worker, host, TLS and display
cleanup passed, no X4 process or test lock remained, and source checkpoint,
selected pins and Steam identity stayed unchanged. A passing raw result is
supported here by those checked records, not only its success flag.

Two limitations affect the intervention itself. WAIT READY and
ZERO_VELOCITY_REQUESTED both reported game time 7.21725, despite nested cue
delays intended to separate them. The intended two-frame delay is **not proven**.
Local `md.xsd` defines delays relative to cue activation or a preceding actions
block; it does not guarantee separate UI frames for these nested child cues.
A future timing probe should use sequential actions/delay blocks in one cue and
require both increasing game time and a measured UI-update counter. The cause
of the same-time receipts remains unknown from the schema alone.
Also, equality with the captured current order does not establish its `started`
state: the schema distinguishes an enabled `ready` order from a started script.
Even `started` would not prove that `stop_moving` executed or that physics was
disabled. No expiry observation, velocity release, native velocity measurement
or AI-state restoration occurred before process cleanup. The result supports
this particular combined intervention; it does not isolate a universal cause
or establish that either operation alone is sufficient.

Startup read-only-config, unsigned-extension and FSR3 diagnostics remain in the
engine log. No MD expression/order error was observed in this run. The result
does not claim a clean renderer log or visual smoothness. The next useful work
is to establish order execution/timing and reversible control of the same actor;
repeating this unchanged successful trial would add little evidence.

## Native attempt 07: timing established, release observation failed

The private variant in `.local/private-client-playback-native-20261118-07/`
retained the same trajectory and actor. It required the exact captured Wait to
be current and `started`, used sequential MD action/delay blocks, and measured
both game time and a counter in the existing UI update owner. The Wait timeout
was 30 game seconds. After clean drained STOP, it requested `constantvel=false`
without linear/angular components and cancelled only its captured Wait order.
Seven subsequent read-only position observations were intended to cover at
least six game seconds and check whether the exact prior order was current and
started again. This remains a private experiment, not a general NPC policy.

The timing records advanced from UI ticks 9 to 23 to 36, with corresponding game
times 7.150647128, 7.257397182 and 7.357906697. They preceded INITIAL at
7.458379222. The complete trial **failed**, but these observations establish the
previously missing timing separation and sampled current/started order checks.
Playback again reached exactly INITIAL plus 20 metres, with 25 delivered
trajectory samples, 746 observations, 638 readbacks and STOPPED at sequence 26,
`drained=1 uncertain=0`.

The release request was logged at game time 13.741809835. The first subsequent
UI bridge observation failed at approximately 13.85, before any release sample
was recorded. Neither restored native motion nor return to the prior order is
established. The host correctly withheld its subsequent pause request. The
generic bridge failure does not identify its internal failing operation;
object-reference conversion is an investigation lead, not a proven native cause.
Native/helper/host/TLS/display cleanup, checkpoint/source pins and Steam identity
checks passed; no X4 process or native lock remained afterward.

Preparation used four synthetic bridge scenarios with real native inspection
closures and a fake C ABI, two real-installer tests and three fake-log observer
tests. They do not execute X4's MD scheduler. A prior variant07 XML passed full
schema validation; subsequent changes redirected diagnostic logging through
existing Lua-event elements and received well-formedness validation only.
Lua logs preserve native float values with `%.17g`; MD's rounded text is not
used to reconstruct post-release displacement. The independent observer checks
record order, native STOP, advancing counters/clocks, measured displacement and
final log identity/content after process exit. It retains negative evidence.

## Native attempt 08: bounded playback, release and pause succeed

The variant07 bridge passed hexadecimal MD references directly to
`ConvertStringToLuaID`, whereas the established native binder first parses the
hexadecimal value into an exact decimal key. An offline regression using the
real native inspection factory and a fake engine that rejects hexadecimal
conversion input reproduced variant07's first post-STOP failure. Variant08 uses
the existing exact `parse_hex` conversion and adds fixed failure-stage labels.
Four lifecycle cases, two failure-stage cases and a fresh real-installer check
passed. This supports correcting that input contract; the generic native07 log
cannot independently prove its historical failure's exact cause.

`.local/private-client-playback-native-20261118-08/` changed only that private Lua
bridge and its diagnostic labels. It retained the same XML, installer, host
observer, trajectory, movement bounds and final success criteria. The complete
bounded trial passed, including final native and release-log revalidation:

- The Wait was current and started at the guarded timing steps. Measured UI
  ticks advanced 8 → 22 → 35, with increasing game times before INITIAL.
- Twenty-five delivered trajectory samples reached exactly INITIAL plus 20
  metres. There were 749 observations and 639 readbacks. STOPPED reported source
  sequence 26, `drained=1 uncertain=0`, and zero endpoint error in the reported
  float coordinates.
- After the release request, seven native position samples covered
  6.651520434 game seconds. The captured temporary Wait was absent and the exact
  captured prior order was current and started in every sample. Independently
  recomputed displacement between the first and last samples was
  647.320048983 metres. These observations were read-only; the playback owner
  had stopped before release.
- The host requested pause only after the positive release receipt. One native
  resume and one later pause were confirmed. Native/helper/host/TLS/display
  cleanup and checkpoint/source/Steam integrity checks passed. No X4 process or
  native lock remained, and the reviewed source pins still matched afterward.

The additional independent check is retained as
`release-independent-observation.json` inside that run directory. This proves
the tested combined control/release sequence for this one existing NPC. It does
not prove exact AI-stack restoration, restoration of a previously unknown
constant-velocity mode, a native velocity readback, or a second resume after the
final pause. It also does not isolate which release action enabled subsequent
movement. No general NPC suppression or ownership policy has been installed.

The next integration target is actual source-X4 motion feeding this native
client. Existing `authority_source_motion_pair_live.py` and
`authority_source_motion_tcp_worker.py` previously delivered two real source
samples into a client buffer, without native playback; their actor/frame
correspondence was not proven. Reuse that exporter while establishing that both
ends refer to the same registered saved actor and sector coordinate frame.
Do not repeat the unchanged successful synthetic trajectory as a substitute for
that missing integration. The earlier full-suite issues remain unresolved;
these focused changes did not justify repeating the unchanged full suite.

All runs here used one actual Linux client, a synthetic trajectory and synthetic
host engine controls over loopback TLS. None tested a Windows client, WAN,
native server, visual smoothness, remote orientation, general AI suppression,
cross-sector movement, trade, combat or boarding. The complete shared-world goal and earlier
full-suite issues remain unresolved.

Private manifests: `.local/authority-client-playback-reviewed-20261118-01.json`
through `-08.json`; private runner/trajectory files:
`.local/authority_client_playback_{trial,driver}_20261118.py`. Scope launchers for
02 through 08 have matching suffixes; 05/06 also pin separate private driver,
binder and installer-wrapper variants. Their `wait-diagnostic-observation.json`
records preserve the independently checked outcome and limits. Variants07/08
also pin the Lua timing/release bridge and `release_observer_20261118.py`; both
use the new private `authority_client_playback_trial_20261118_07.py` host gate.
Variant08's bridge SHA256 is
`3c7f32f21fb7bc3e06e56483b8549408de5cec48b00cb2bfe8493dd12de30c44`.
These files,
binaries, saves and private credentials are not committed. Selected dependencies
are checked before and after runs;
intermediate mutation and external cgroup migration are outside that evidence.
