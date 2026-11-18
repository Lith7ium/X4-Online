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
