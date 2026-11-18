# Independent client playback integration

Internal development on the authoritative fork. Client work takes priority;
GPU-free server development is deferred while the user seeks a hosted test server.
The overall Windows/Linux Internet gameplay goal remains unmet.

Latest native result, 18 November: batching saved checks at `ef867aa6`
reduced checkpoint metadata requests but did not improve the observed source
cadence. Three samples were queued and sequence 1 was ACKed. Native sequence 3
was refused at a 287.300 m correction, with no running write. Initial alignment
again had zero readback error. Cleanup passed. Work stops here at the user's
request; resume only when the user is ready. See
[the paused checkpoint](#batched-checks-native-result-and-requested-pause-2026-11-18).

Earlier client increment, 18 November: both the independent bounded live-input
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

### Follow-up: the first pose comparison happens after takeover begins

A read-only audit at `ca05f146` compared the current source with the staged
files from native05. It identifies an unmeasured interval before INITIAL:

1. `authority_recovered_source_probe.run` requires an already running world,
   then verifies the context, binds and registers the source, and pulls its
   first sample. The reported phase durations therefore do not describe a
   client held paused throughout source setup.
2. `motion_client_owner.lua` starts saved-actor binding on the first BIND
   packet. In native05, only then does the private binder issue Wait. Three
   100ms delays precede its zero-velocity request and Bound response. Neither
   operation can prevent movement that already happened before this request.
3. After binding, `authority_recovered_client_motion.lua` constructs playback
   and reads INITIAL. Its first packet is enrollment only and is not buffered
   or applied. `PairedPlaybackEvidence.received` then compares the raw source
   and client positions and refuses the 88m separation.

Thus the client may simulate the saved actor independently before takeover;
the available positions do not measure its displacement during that interval.
The source-game/client-real clock-rate problem is separate: buffered playback
has not yet produced a target when this initial comparison fails. This rules
out buffer prediction as the cause of this particular refusal, but does not
identify the cause of the raw position difference.

The distinction between tracked and private code matters for Windows. The
tracked `authority_saved_baseline_motion_bind.xml` only resolves registry
references and reports Bound. It does not contain native05's Wait, zero-velocity
or release experiment. The Windows overlay installs that tracked binder; its
optional playback flag does not establish exclusive control of the actor.
The current Windows transport tests therefore cannot support an AI-takeover claim.

The smallest additional native observation would retain validated actor and
frame identity, sector position, own game time and local real time before Wait,
after Wait is confirmed, and one later tick after the zero-velocity request.
Native05's private bridge records only clocks for these early phases, and reads
positions only after STOP; neither that later read nor log timestamps fill the
missing early observations. A Lua event raised before a synchronous MD order is
not by itself proof that the Lua position read happened before the order.

The user has been asked to choose between a one-time, verified initial placement
on the isolated fixture and further read-only measurements. If approved,
initial placement must be a separate enrollment step with the existing identity,
sector, ownership and readback checks; it must not weaken the ongoing 50m
correction bound or silently change the wire clock. No such change has been
made. This audit launched no game, reparsed no save and repeated no tests.

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

## Shared fixture control option

The Linux and Windows client overlays now expose an explicit
`saved_replica_control_fixture="recovery_enh_870"` option. It requires the
matching saved-playback option, epoch `4ba7be438ebb04ec5bb85fdb95b5a488` and
single registry index 1318. The existing saved-reference binder remains
read-only. Default configurations install neither the new control module nor
its MD script.

After a successful read-only BIND, the motion owner enters `preparing`.
The separate controller captures the prior AI order, creates one finite Wait,
observes that Wait current and started across advancing UI/game samples, and
requests constant zero linear velocity. Only then does the owner construct
playback, read INITIAL and acknowledge BOUND. Later BINDs revalidate ownership
of the same temporary order. Initial enrollment still does not write a target;
packet arrival time, the 50 m bound and source-clock handling are unchanged.

STOP captures the playback drain/certainty state before disabling writers.
Only stale, certain playback permits release of an acquired local order.
The controller disables constant velocity and cancels only its captured Wait.
STOPPED is withheld until two advancing observations confirm that the Wait is
absent and the captured prior order is current and started. The enclosing pause
gate therefore also waits. Release polling remains bounded when order
resumption is pending. Unconfirmed ownership after a fault requires the
existing process fence; there is no automatic repair/retry.

This is a short internal trial: the Wait lasts 30 game seconds, and the local
controller refuses further work at 29 game seconds from its pre-request clock
sample. Release must finish before that bound. This is not a sustained gameplay
lease, a general AI suppression policy, or an exact restoration of the AI stack
or an unknown previous constant-velocity mode. A successful zero request is
not a physical velocity measurement. The new two-sample release check does not
reproduce native08's longer six-second observation span.

Focused checks exercise configuration forwarding, generated Linux/Windows
overlays, delayed preparation/release, packet correlation, deadlines, expiry,
fault uncertainty and the existing pause gate with fake engine behavior.
The new controller checks cover 13 simulated lifecycle scenarios and eight
native-adapter scenarios against a fake ABI, including exact hexadecimal
reference conversion. The new MD script passes the local game-schema validator;
schema validity does not establish runtime behavior.
The assembled test exposed an event-router assumption that BIND must return
immediately ready; the router now allows `preparing` only on the explicitly
enabled saved route. No full suite was repeated. At implementation commit
`e1cdd201`, the native08 private-script success above was only prior evidence
for the underlying operations. The following run checks the new shared path.

## Native shared-control smoke (2026-11-18)

One bounded Linux X4 run passed using the shared installer and explicit control
option at `e1cdd201`. Evidence is retained in
`.local/private-client-shared-control-native-20261118-01/`. The host engine
controls and trajectory were synthetic, with the existing authenticated
loopback TLS participant session and a real isolated X4 client.

The driver selected the shared option without replacing the read-only binder
or installing the old private Wait/release bridge. Installed Lua/MD hashes and
the rendered option were checked; the binder matched its repository source.
The 171-input manifest is
`.local/authority-client-shared-control-reviewed-20261118-01.json`, SHA256
`f6333b5c986fa926ed9008ca92bcbf6b662b04636fdbf184a0414ad50af64fee`.
Its companion source audit records the unchanged historical helpers and the
tracked inputs matching `e1cdd201`.

- INITIAL reported game time `7.405475807` and x `-116814.9375`.
  All 25 trajectory updates were delivered. STOPPED reported x `-116794.9375`,
  unchanged y/z, zero final target error, 694 observations and 585 native pose
  readbacks. The displacement was exactly 20 m in the recorded coordinates.
- STOPPED carried `drained=1`, `uncertain=0`, source sequence 26. In the pinned
  shared implementation, that acknowledgment requires completed preparation,
  drained playback and confirmed release: the temporary Wait is absent and the
  captured prior order is current and started across two advancing samples.
  This run did not separately record the intermediate MD responses or observe
  subsequent autonomous movement; the release conclusion relies on that
  executed acknowledgment gate, rather than an independent observer.
- The real client confirmed one resume and one subsequent pause. The host
  requested pause only after the playback-stop receipt. Native, participant,
  TLS, display and scope cleanup passed; reviewed inputs, checkpoint/source
  and Steam identity remained unchanged. Parent and native client exited zero;
  no X4 process remained.

This validates the new shared control path for the one Linux fixture. It does
not validate Windows execution, an actual source-X4 trajectory, initial
alignment, source/client clock mapping, sustained ownership, physical velocity,
exact AI-stack restoration, visual smoothness, WAN or gameplay. The existing
50 m bound and first-sample enrollment behavior remain unchanged. No full-suite
repeat was needed for this runtime check; earlier suite issues remain open.

## Windows shared-control smoke under Proton (2026-11-18)

The same shared control path subsequently passed in Windows X4 under
GE-Proton10-29, with sources at `de68a1a6`. The isolated Windows runner reused
the successful Windows control diagnostic's staging, mapped-process/socket
ownership and cleanup checks. It used the same verified checkpoint as the Linux
shared-control run, the shared Windows overlay, and the unchanged synthetic
trajectory. A Linux supervisor supplied motion directly through the existing
local IPC; this run did not exercise a server or TLS session.

- Raw observations contain one INITIAL, nine SUMMARY records and one STOPPED.
  All 25 updates were delivered. Initial x `-116784.6640625` became
  `-116764.6640625`, with unchanged y/z and zero final target error. STOPPED
  reported 1,034 observations, 769 readbacks, sequence 26, `drained=1` and
  `uncertain=0`.
- Resume request 1 and pause request 2 were confirmed without retries. Raw
  clock observations show running game time and paused state after STOPPED.
  The installed shared code gates IPC STOPPED on preparation and release;
  intermediate MD responses and later autonomous movement were not separately
  recorded. The cached final pose timestamp is not the release timestamp.
- The intended trajectory spans five seconds, but INITIAL-to-final cached
  pose time advanced **9.8218675 game seconds**. Scheduling delay was not
  isolated. This result establishes the client effect and lifecycle, not a
  five-second flight, smoothness, sustained delivery rate or engine capacity.
- All 369 reviewed input hashes matched before and after the run. Installed
  shared modules, the read-only binder and staged save matched their expected
  sources. Overlay/save integrity, owned cleanup and Steam identity checks
  passed. Config was retired only after owned shutdown; no owned group or
  matching private-prefix process remained. Unreadable unrelated processes
  remain outside this scoped cleanup claim.

Evidence: `.local/windows-shared-control-proton-20261118-01/`, especially
`result.json`, `motion-cycle.json` and the private profile's `x4authority.log`.
The private runner is
`.local/authority_windows_shared_control_proton_20261118_01.py`, SHA256
`afaf1fe475a87a3314bc8391f01270d762ab549215aa1cf0455185415da25de4`.
The final audit is
`.local/authority-windows-shared-control-proton-reviewed-20261118-02.json`,
SHA256 `4cb8b7914c6313d7208a48028d39a0d273470507bacb8935898184366c4db9b2`.
The earlier audit file is preserved. No full suite or unchanged engine test
was repeated. This is not native Windows/Windows CLI, actual source-X4 motion,
initial-alignment, physical-velocity, exact AI-stack, WAN or gameplay proof.

## Approved initial placement: opt-in implementation

The user approved one initial placement at the server position with native
readback on the isolated ship. The subsequent correction bound remains 50 m.
Linux and Windows configurations now accept
`saved_initial_alignment_fixture="recovery_enh_870"`, requiring both matching
playback and shared-control options. It defaults off and retains the fixed
registry epoch/index, ENH-870 identity, profile and actor/frame guards.

After shared preparation, the owner supplies the first sample with its original
sequence, source time and arrival time. It consumes the alignment attempt before
constructing playback. The native factory checks freshness and preparation,
reads the actual pose, sets the supplied XYZ while preserving orientation, and
reads back the pose. Readback must be within the existing 3 m endpoint tolerance.
Only then may the normal INITIAL and BOUND acknowledgments follow. A separate
`AUTH_CLIENT_INITIAL_ALIGNMENT` record retains pre-position, target, readback,
error and original sample timing for the next native comparison.

Expired/future samples or invalid native poses refuse before writing. A setter,
readback or observer fault after entering the write retains uncertainty even
before a playback object exists, including reentrant STOP. The current attempt
fails without retry or an age reset. No-option enrollment, later 50 m corrections,
velocity handling, clock mapping and the read-only binder remain unchanged.

Focused checks pass: 17 native-factory fake-ABI scenarios, three owner lifecycle
scenarios, configuration/forwarding checks, the assembled wrapper's 1,000 m
initial placement followed by a rejected excessive correction, and relevant
existing writer/owner/playback regressions. Review found and corrected a missing
finite-XYZ check on the native pre-write pose; its new refusal test passed.
These are simulated engine checks. Neither preceding native smoke enabled this
new option. Actual source-X4 placement/readback and sustained paired playback
remain to be demonstrated; no full suite was repeated.

## Actual-source initial alignment (2026-11-18)

One bounded two-Linux-X4 attempt at `dfa12f09` enabled both shared replica
control and the approved initial-alignment option. It used the real source
sampler, retained TCP participant and fresh join checkpoint. The ordinary
binder matched the tracked read-only file; no old private Wait binder or
release bridge was installed. The overall run failed and must not be counted
as passing paired playback.

The first source sample was captured before delivery, then correlated offline
with exactly one `AUTH_CLIENT_INITIAL_ALIGNMENT` preceding native INITIAL.
Sequence 1, source game time, epoch/index and all three target coordinates
matched. The original recipient arrival age at readback was 0.285612582 s.
The ship's pre-alignment offset was 77.405618998 m; measured readback error and
the subsequent source-to-INITIAL offset were both 0 m. The source's initial
velocity remained unknown. This establishes the one permitted initial
placement on this fixture using actual source-X4 data.

The second native observation was `phase=held`, sequence 2. It requested a
221.974737844 m correction while the actual client position remained at the
aligned position. The controller refused at `stage=distance`, `uncertain=0`,
before any running correction. The source-time interval was 1.431247294 s;
the client's INITIAL-to-failure interval was 1.175777276 s on each of its
local/game clocks. These are separate elapsed intervals, not a clock-origin
mapping or proof of equal rates. The second position is retained as the raw
client FAILURE target; a separate raw second-source capture was not saved.

Read-only code review identified two independent startup problems:

- The wrapper discards the first BIND as enrollment even after verified
  initial placement. It therefore does not seed the interpolation buffer.
  Sequence 2 becomes its only sample and is offered directly as a held pose.
- Seeding alone cannot repair this trace. Its 1.431 s source gap exceeds the
  existing 0.75 s buffer continuity limit. The original first arrival to
  failure interval also exceeds the existing 1 s local freshness limit.
  The run does not isolate the cause of the delivery delay. Guard and pull
  timings are diagnostic overhead measurements, not server simulation
  benchmarks.

The result records two prevalidated source samples and one confirmed client
receipt. No STOP, shared release, final departure save, sustained playback,
Windows execution, WAN, visual smoothness or gameplay was established.
Owned cgroup/process and Xauthority cleanup, unchanged source checkpoint,
selected source pins and Steam identities were confirmed. The source registry
still uses the approved experimental correspondence, without independent
historical identity proof. No native retry or full-suite repeat was made.

Private artifacts: `.local/private-paired-alignment-native-20261118-01/`,
including `first-source-before-delivery.json`, `trial-result.json`, the two
engine logs and `offline-initial-alignment-correlation.json`. The correlation
artifact SHA-256 is
`8d5e97edf2c07ded7a8f3cf7e4a39c6f589e53bf6d06a86140f545dddd1ba498`.
Reviewed manifest02 contains 487 pins, SHA-256
`d4539b2ff05af44e371e478c8d4f7d9fad414ab7fb525910f5c30ac83f9d3a7d`.
The private scope/trial/evidence helper hashes are respectively
`a67695f46860970058c633d0a6e695a602a7bbef4a5e9253b1c50cdcd16cd908`,
`ac35d4d9fd62bbecf7eab6c4ee4a97d4c8f550a1275c5ccd73a27f16ebae273f`,
`faae8ffa649237f27a370b7701cb974f3e38b3f1d7686c541fc045891cd8aaad`.
Four pure parser/correlation checks passed before launch; the run's partial
observation was recovered afterward from the preserved inputs because the
normal success-only final correlation was not reached.

### Follow-up: retain the verified starting sample

The wrapper now forwards the first sample to the playback buffer only when
initial alignment was explicitly enabled and its native factory succeeded.
The original source sequence, time and recipient arrival are preserved. The
ordinary enrollment path still discards its arbitrary target. This is a
startup continuity correction, not another position warp or a changed clock
policy.

The focused assembled-client check passed three simulated cases: ordinary
dummy enrollment remains excluded; dense follow-up samples interpolate from
the aligned position; and the observed sparse source/local intervals still
cause a distance refusal with no running write. The existing playback/pause
regression method also passed its 15 runtime and two pause cases. No native
rerun was made, because this change alone cannot repair the recorded gap.

A read-only delivery audit found that the paired fixture serializes native
PULL, validation, TCP delivery, the client's BOUND receipt and evidence checks
before requesting another sample. Its nominal 0.2 s cadence does not compensate
when those stages take longer. Existing latest-position source/transport APIs
offer a single-owner asynchronous path that this fixture does not yet use.
The next investigation is to connect that already-approved path while retaining
the first enrollment receipt, lifecycle fences and separate sample/receipt
accounting. Per-stage timing is needed before attributing the measured delay
to one component. No producer thread, clock change or threshold relaxation has
been introduced.

### Follow-up: explicit latest-position collection

The bounded fixture now exposes `--diagnostic-latest-playback`, requiring saved
playback and excluding the long diagnostic. The existing serialized path remains
the default. The new single-owner collector uses the existing asynchronous
source/latest-position transport: it protects the first frame from replacement,
queues 26 validated source samples, and records actual ACKs separately. Before
establishing the final motion barrier, it requires an increasing acknowledged
subsequence containing sequences 1 and 26, matching receipt digests, and drained
transport. Intermediate positions may be replaced; queue acceptance is not an
ACK.

Playback log inspection is deferred until collection completes so a log flush
cannot block the next source request. Source/helper lifetime checks under the
TCP reader lease do not pump or request checkpoint IPC; the existing full and
metadata checks remain at sample-operation and STOP boundaries. Separate
lifetime-check counters and collection timings are retained. Initial alignment,
original sample timing, clock mapping, the 0.75 s continuity and 1 s freshness
limits, later 50 m corrections and STOP/release gates are unchanged.

Focused validation, not a full-suite result:

- Nine running-source binder tests and six lifetime/window guard tests passed.
- Ten fake collector tests and nine focused evidence tests passed.
- Two real loopback UDP/TCP tests passed together in 13.625 s: a latest consumer
  delayed by 0.35 s, and the unchanged default delivery of all 26 samples.
- Two loopback mode/finish tests passed in 0.005 s. An initial test invocation
  lacked `PYTHONPATH=tests`; correcting that import setup resolved it without a
  product change.

No new native game run has exercised this integration. One fresh bounded native
attempt is planned; passing these checks does not establish delivery cadence,
sustained paired motion or a solution to the recorded sparse-gap failure.


## Actual-source latest-position attempt (2026-11-18)

One bounded two-Linux-X4 run at `3d88b804` exercised the explicit latest path,
shared replica control and initial alignment. The overall run failed. The
collector retained three queued source samples and one exact ACK (sequence 1).
The client recorded two accepted buffer samples, followed by a held target
from source sequence 3 and a distance refusal of 282.922322685 m. Its actual
position was still the initially aligned pose; running readbacks were zero and
uncertainty was zero. Sequence 3 reaching native playback does not imply a
successful ACK or write. The two accepted samples are consistent with sequence
2 being replaced by the latest transport; no sequence-2 native pose is recorded.
Sequence 2 was queued 0.258714023 s before the host observed ACK 1, establishing
that source collection no longer waits serially for that first receipt.

The original source gaps were 0.932711615 s and 0.814234745 s. Both exceed the
unchanged 0.75 s continuity limit, and the delivered 1-to-3 source gap was
1.746946360 s. Initial placement again matched the actual first source pose with
zero native readback error, after removing a 116.285769516 m initial offset
at an original recipient arrival age of 0.294062644 s. The client's
INITIAL-to-refusal elapsed interval was 1.657656261 s on its own local and game clocks; these intervals do not
establish a mapping to the source clock.

Collection lasted 3.036759084 s before the client-log refusal. Three source poll
calls consumed 1.534717814 s total (maximum 0.521126269 s); four begin calls used
0.318302698 s, 28 surrounding collector checks used 0.412190919 s and six TCP
pump calls used 0.095063349 s. Queue observations were separated by 0.919951081 s
and 0.841803357 s on the host clock. The broader probe's guard totals span
binding and registration too and may overlap; they must not be added as
independent CPU costs. These are diagnostic wall times, not a server simulation
benchmark or a quantified cause of the entire delay.

Code inspection localized remaining synchronous work: normal `poll_latest()`
does not select the no-IPC saved lifetime guard. Its nested `_check()` calls
still reach `saved_baseline_guard` -> `check_checkpoint` -> `check_metadata`,
which requests the helper and pumps while waiting. The TCP source guard already
uses lifetime-only checks. The next investigation is to retain substantive
checkpoint checks at explicit operation boundaries while avoiding duplicate
requests inside one operation. This has not yet been implemented or measured;
do not simply remove checkpoint validation or widen playback bounds.

Failure revealed a diagnostics bug: top-level legacy counters remained zero,
although the retained `latest_collection` correctly recorded three queued
samples, one ACK and four begin calls. Snapshot reporting now derives latest
counters from that detached progress, including empty pulls and last completed
begin-to-queue duration. One focused no-network regression method passed;
serialized counters remain unchanged. The original native artifact is preserved
as written and predates this reporting correction.

Owned cgroup/process and Xauthority cleanup, unchanged pinned source/code and
Steam identities were confirmed. No STOP, shared release, departure save,
sustained motion, native Windows, Internet, visual smoothness or gameplay was
proved. There was no native retry or full-suite rerun.

Private artifacts are `.local/private-paired-latest-native-20261118-01/`, with
both raw engine logs, `trial-result.json` and all three
`source-captures-before-delivery.json` samples. The latter SHA-256 is
`d5b8722c1cadacc32de2806caf630880ec51dcfb553f9dfb7458348d49a80997`.
Manifest `authority-paired-latest-reviewed-20261118-01.json` contains 488 pins,
SHA-256 `eec01045aeb9d4a254a0e3f402ad2035a9b2551aaf389eaacbac27870b2777b7`.
Private scope/trial/evidence helper hashes are respectively
`0d5c6b428ff215e9ad9dbacbd82672ede1e31aab8e6d5025d442603234b0d72c`,
`6025aad95931efab33d58e4705ef06221dbaf4c520b4bc71628351f2fc1d8405`,
`10edb92e4e79305cc7d8952924bc87a549ea1dfe2f7e5444a193f2160606e8f4`.

Offline correlation independently matches all three raw captures to the queued
ledger and matches native FAILURE sequence 3, time and XYZ to source sample 3.
Artifact `offline-correlation.json` has SHA-256
`07eed910b74303713ed9e5ad7fb55f2e707065b96f47431615fce3818635ffbd`.
The first source callback-to-queue interval was 0.402678544 s and includes the
private first-capture flush as well as validation/queue work; it cannot be
attributed entirely to checkpoint IPC. If finer attribution is needed, record
nested operation spans with inclusive/self-time separation before choosing an
optimization. Never infer CPU utilization from these wall-time aggregates.


### Follow-up: batch saved checks inside one latest operation

`ExperimentalSourceMotionIPC` now accepts default-off
`batch_latest_saved_checks=True`, requiring latest mode and both substantive
saved-state and lifetime callbacks. The bounded latest-playback fixture opts in;
other callers retain their previous behavior. Normal `begin_latest()` and
`poll_latest()` calls run substantive saved checks at entry and successful exit.
Nested checks still validate process, socket, state and saved-helper lifetime,
but do not request the same saved-state assertion repeatedly. Callback ownership
remains fenced. Exit checks run before a return; an exit failure after UDP
request or queue insertion fences the source and host, without reporting success.

An obsolete reply after a lifecycle barrier retains the existing lifetime-only
validation and discard behavior, including at operation boundaries. Guard mode
is restored in `finally`. Registration, STOP, outer full digest checks and
playback timing/bounds remain unchanged. These are sampled checks, not atomic
protection against transient changes between boundaries. The fixture result
records that batching was configured, even if the later attempt fails.

Focused checks passed: seven new real-loopback boundary/fault tests in 3.810 s;
nine existing latest-source regressions in 3.209 s; three binder/default/refusal
tests in 0.011 s; and the 26-source-sample slow-recipient UDP/TCP integration in
7.212 s. One additional real checkpoint-helper/window/UDP/TCP integration passed
in 0.256 s: exactly two helper requests per normal operation, nested lifetime
checks, no TCP reader reentry during helper requests, exact ACKs from both
recipients, then source close and full helper STOP/window close. These tests
simulate the game source and do not establish native timing or gameplay.
No full suite was rerun. A fresh bounded two-X4 attempt is prepared to evaluate
the changed call path; no native success is claimed for this implementation yet.


## Batched-checks native result and requested pause (2026-11-18)

One two-Linux-X4 run of `ef867aa6` exercised the configured batching and failed
at native playback distance validation. Three actual source samples were queued;
only sequence 1 has a confirmed host ACK. Native sequence 3's time and target XYZ
match the original third capture exactly. It requested 287.299942264 m while the
client remained at its aligned initial position, with zero running readbacks
and `uncertain=0`. Initial alignment removed 105.952209082 m at an original
arrival age of 0.278725612 s with zero readback error. Client INITIAL-to-failure
elapsed time was 1.825166713 s on its own local clock. There is no ongoing paired
movement, STOP/release, departure-save, Windows, WAN or gameplay proof.

The source intervals were 0.993531693 s and 0.864827578 s, still above the existing
0.75 s continuity limit. Batching was active: across the full probe, checkpoint
metadata checks fell from the preceding run's 54 to 21, and lifetime checks rose
from 3 to 50. However, three polls still took 1.481931000 s total versus
1.534717814 s previously; four begins took 0.573664661 s versus 0.318302698 s.
Collection took 3.256245527 s versus 3.036759084 s. These two separate attempts
do not demonstrate a cadence improvement. Counts prove the changed path ran;
they do not isolate why wall-time cost stayed high. Full-guard aggregates are
inclusive and must not be summed with nested helper costs or treated as CPU
utilization. The corrected failure counters now report 3 samples, 1 ACK and
4 begin attempts consistently with the retained ledger.

Do not repeat this unchanged test. On resumption, first profile remaining
per-operation costs using nested inclusive/self-time measurements and the
retained traces; avoid assuming checkpoint IPC alone explains the delay. The
expensive bootstrap/registry work is separate from steady-state sampling.
Do not widen playback bounds, alter the pending clock policy or choose a new
server architecture without the user's agreement. GPU-free server work remains
deferred; the complete persistent Linux/Windows Internet gameplay goal is unmet.

Both test games and the owned cgroup were cleaned up; Xauthority cleanup,
unchanged pinned source/code and Steam identities were confirmed. A post-run
process scan found no X4 instance. Normal profiles/saves were not used. The user
requested a checkpoint and goal pause after this run to use the PC. No further
native test or implementation work is to start until the user resumes.

Artifacts: `.local/private-paired-batched-native-20261118-01/`, including both
engine logs, `trial-result.json`, all three `source-captures-before-delivery.json`
samples and `offline-correlation.json`. Correlation SHA-256:
`df0cfa1038a948753d0d6f79540c3ba70610aa86c863e1f352f87f3af506ed5b`.
Manifest `authority-paired-batched-reviewed-20261118-01.json` has 488 pins,
SHA-256 `acbc700c985d05dee9584fdd0e2c5f402a4be427fa22568f1727503cd7c3b969`.
Scope helper `authority_paired_batched_scope_20261118_01.py` SHA-256:
`da992f048a6090390afbff05b6e3bab793713ac6abe22d440d4c228ed588cf2d`.
The trial and alignment-evidence helpers are unchanged from latest attempt 01.

## Resumed cost investigation (2026-11-18)

The user explicitly resumed the goal after `b361ebb4`. Review confirms that
each source check still invokes the full context and peer validators twice;
peer validation scans UDP tables and the owned process's descriptors. Full
context verification also checks server/client files and process identities.
Collector operation timings exclude entry/exit of the outer process-discovery
scope. Their inclusive nested totals therefore cannot isolate the cause of
the remaining delay.

The next native attempt is for measurement: capture a function profile only
around collection, including its outer scopes, and preserve it after supervisor
cleanup. All current guards, thresholds and deadlines remain unchanged. The
profiler adds overhead, so its timings will locate costs rather than establish
unprofiled throughput or successful gameplay. No full suite repeat is planned.

## Bounded collection profile (2026-11-18)

One fresh two-Linux-X4 attempt at `42aab58a` profiled only
`collect_latest_playback`, including its outer identity scopes. The wrapper
records exactly one invocation, disables profiling on return or exception,
and exports the profile after supervisor cleanup. No production behavior,
guard, deadline, playback bound or clock mapping changed.

The collector failed again: two source samples queued, only sequence 1 ACKed,
sequence 2 refused at 249.073727476 m with `phase=held`, zero running readbacks
and `uncertain=0`. Its source time and target XYZ equal the original second
capture; both captures equal the queued ledger. The source interval was
1.561224082 s. The profiler perturbed execution, so this is not a comparable
unprofiled cadence measurement or a successful movement test.

The profile contains 5,806,741 calls (5,804,977 primitive) and 3.825380556 s of
attributed self time. Important **inclusive, overlapping** costs:

| Function/path | Calls | Inclusive seconds |
| --- | ---: | ---: |
| Full source `active_guard` | 112 | 2.446 |
| Retained participant `check_active` | 112 | 1.737 |
| Client `check_live_context` | 668 | 1.380 |
| Scoped process `_targeted` | 9,514 | 1.254 |
| Scoped process `_read` | 19,028 | 1.210 |
| Full `owned_group_members` scans | 48 | 0.882 |
| Protected-file `sha` | 27,174 | 0.545 |
| Source `socket_owner` | 90 | 0.088 |

The principal repeated chain is `active_guard -> verify_diagnostic ->
check_active -> registry_context -> client_context -> check_live_context`.
Registry verification brackets its observation with context checks, and the
motion-log watcher adds another context check. Those contexts reread both
game identities and protected files. Outer discovery scopes independently scan
all process entries. The socket-table/descriptor scan is a small part of this
particular profile, not the first optimization target.

Selected **self** costs are 0.722 s for 86,993 `_io.open` calls, 0.305 s for
59,372 text reads, and 0.246 s for 72,657 `posix.stat` calls. These are calls,
not distinct files. Path construction and conversion also contribute. The
next narrow experiment is to remove repeated pathname-object allocation while
still rereading the same process fields at every existing boundary. No caching
of process identity, widening of scopes or removal of guards is implied.
Microbenchmarks must run without the profiler before another native attempt.
These costs belong to the Python test/control path and do not demonstrate a
CPU bottleneck in X4's universe simulation or rented-server performance.

The supervisor and outer scope both terminated; owned-cgroup/Xauthority cleanup,
pinned source/code preservation and Steam identity preservation passed. A final
process scan found no X4. Normal profiles were not used. The complete goal,
including ongoing motion, Windows/WAN, combat, trade and boarding, remains unmet.

Artifacts: `.local/private-paired-profiled-native-20261118-01/`, including
`latest-playback-collection.pstats` (SHA-256
`9f976bad1b38b1de6af00c8dc16d63338b671a5b4f7ea7393357cf8d5a4399ac`)
and `profile-analysis.json` (SHA-256
`1d091f650b04dffba8ae02e7bcd2100d4e4add2ab0e4f714570d40ca0cfa24d3`).
The latter retains function rows, correlated source/failure values and cleanup
results. The 488-pin manifest is
`.local/authority-paired-profiled-reviewed-20261118-01.json`; the private runner
and scope have the corresponding `authority_paired_profiled_*_20261118_01.py`
names. No full test suite was rerun.

## Process-query path allocation optimization

Three hot helpers now use direct string paths and ordinary `open`/`os.stat`
instead of repeatedly constructing Path objects. `owned_process_identity`
still reads and parses the process stat record before obtaining its current
UID. `OwnedGameDiscovery._read` still rejects an exited process or wrong UID
before obtaining its current executable device/inode. `owned_group_members`
still scans the complete process directory, snapshots matching names, and
reads each stat record before checking UID, group and start time in the same
order. It does not use cached DirEntry metadata. Error handling and sorted
membership results are retained. No identity result is cached; no guard,
scope, callback boundary, protocol, deadline or playback threshold is removed.

Unprofiled, alternating non-game microbenchmarks measured the following median
costs. They do not predict the speedup of the complete native collector:

| Operation | Original | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| One process identity read | 19.358 us | 14.495 us | 25.1% |
| Combined discovery identity/executable read | 27.142 us | 18.818 us | 30.7% |
| Complete process-group scan | 8.966 ms | 7.039 ms | 21.5% |

The identity benchmark alternated eight batches over self and a settled owned
sleep process, checking field equality. An initial equality check encountered
the child's startup transition; that observation was not used as timing data.
The scan benchmark alternated ten batches of eight scans per implementation
against one owned non-game parent/child group. All 160 measured scans found
exactly those two members, and the parent exited cleanly. Concurrent unrelated
process changes remain possible; these are sequential observations, not an
atomic process snapshot. Scan evidence is retained in
`.local/owned-group-scan-comparison-20261118-01.json`.

Nineteen existing discovery/cleanup tests and eleven snapshot tests passed.
The latter include two added cases for UID/group/start filtering, malformed or
disappearing entries, digit-prefix names and an unreadable process directory.
Independent review found no blocker; `git diff --check` passed. The full suite
was not repeated. One fresh unprofiled two-X4 attempt is needed to determine
whether these small changes help the measured source cadence; no native
improvement or successful movement is claimed yet.

## Unprofiled process-helper comparison (2026-11-18)

One fresh two-Linux-X4 run at `2911ee82` stopped with
`client log changed during registry observation`. One source sample queued;
no host receipt was recorded. The client performed initial alignment with
zero readback error and logged INITIAL. No running movement was demonstrated.
The sample matches the queued ledger. With only one sample there is no source
interval or useful cadence comparison; one 0.454 s poll does not establish a
native performance gain.

The registry verifier requires two independently stable log captures to be
identical, so a complete unrelated append between them can trigger this exact
error. Deterministic regressions reproduce that mechanism. The failing run did not
retain both read tuples, so the exact intervening append cannot be reconstructed
from its final log. This result is not the earlier 50 m correction rejection.

Cleanup, Xauthority removal, pinned sources and Steam identity preservation all
passed. The supervisor lists no owned processes remaining; a separate readable
`/proc/*/exe` scan found no X4 executable. Normal saves were not involved.
Artifacts: `.local/private-paired-proc-native-20261118-01/`, including
`offline-correlation.json`, source captures, both engine logs and process scan.
Correlation SHA-256: `fb19eaf6b6c01f76834e6a8940079561bc1be539e21d645b9b9aefc7236ffc86`.
The unprofiled comparison is complete but inconclusive about cadence. Do not
repeat it unchanged. The user has now approved the separate capture-clock
protocol direction; see [the clock contract](AUTHORITY-MOTION-CLOCK-BASIS-20261118.md#approved-direction-2026-11-18).

### Registry observation correction

The verifier now accepts two individually stable captures of the same inode
when the second contains the exact first byte prefix followed only by complete,
unrelated rows. It validates the newer capture again. Replacement, truncation,
rewritten prefixes, metadata-only changes, appended relevant receipts/errors,
and partial tails remain failures. In-read instability still fails without a
retry. Independent review found no blocker. Six focused receipt/log tests pass,
including both load gates, normal append and 28 mutation/tail cases. This is a
reproduced verifier fix, not proof that the precise native append was captured.
No further native run has been started for this change.
