# Source clock and playback: bounded offline observation

At the measured checkpoint, the paired source sent **source X4 game time**, while the playback
buffer maps the source timestamp onto the client's real-time clock using an
offset and slew. That mapping does not establish that the two clocks advance at
the same rate. A deterministic offline experiment with the actual Lua buffer
and playback controller shows divergent reconstructed positions when the
source game clock advances at a different rate or temporarily stops.

## Existing contract and paired path

- `src/authority/SOURCE_MOTION_SAMPLER.md:39–43` defines `source_time` as
  source game time after the position read, with optional velocity in metres
  per source game second. `src/authority/EXPERIMENTAL-TCP-MOTION.md:14–20`
  carries the same meaning on the snapshot transport; unknown velocity is
  null rather than zero.
- `tools/dev/authority_job_descriptor_probe.lua:149,159–160` reads
  `GetCurrentGameTime()` around the source pose;
  `src/authority/lua/source_motion_sampler.lua:125,165` uses the post-pose
  game time in the snapshot. The paired source/receipt path retains this
  `source_time` and velocity for the client's motion playback.
- `src/authority/lua/motion_playback.lua:2` currently describes source time as
  remote real time. `src/authority/lua/motion_buffer.lua:124–128,149–168`
  calculates and slews an additive offset between source time and local
  arrival/render time, and `:203–210` applies the supplied rate for bounded
  prediction. `docs/AUTHORITY-CLIENT-PLAYBACK.md:138–152` already notes that
  observed game-time/receipt-time ratios do not prove equal simulation rates.

## Synthetic measurement

The experiment uses the actual `motion_playback.lua` and `motion_buffer.lua`
at commit `c202ceb4`, with synthetic clocks, immediate local sample delivery,
and a fake position setter. It sends one sample every 0.2 local seconds and
ticks every 0.05 local seconds. Source motion is 10 m per source game second;
the first sample has unknown velocity and later samples carry that known rate.
The normal buffer's 0.15-second render delay and 0.35-second prediction horizon
remain unchanged. Distances below compare with the **current** source position,
not with an ideal delayed reference.

| Source game time versus local real time | Local time | Current source X | Playback X | Playback phase |
| --- | ---: | ---: | ---: | --- |
| 0.5× | 3.0 s | 15.0 m | 18.5 m | frozen |
| 1× control | 3.0 s | 30.0 m | 28.5 m | interpolated |
| 2× | 3.0 s | 60.0 m | 52.95 m | interpolated |
| 1× with a 0.8 s game-clock stall from local 1.0–1.8 s | 2.0 s | 12.0 m | 15.5 m | frozen |

The 1× control trails by the configured delay. In the half-speed and stalled
cases the model can predict ahead and freeze despite later updates; the
double-speed case shows lag and offset adjustments. These are values for the
specified deterministic inputs, **not** measurements of X4's native clock
rates, Windows, Internet jitter, displayed smoothness, or multiplayer play.
The fake setter is immediate and models no native physics or other writers.

Private local reproduction artifacts are under
`.local/clock-basis/measure.lua`, `.local/clock-basis/measure.py`, and
`.local/clock-basis/result.json` in the isolated
`work/x4-authoritative-server-20261115/.local/motion-clock-basis-audit`
worktree. Run `python .local/clock-basis/measure.py` from that worktree to
regenerate the complete rows. These ignored artifacts are local and are not
part of this report's commit.

## Approved direction (2026-11-18)

The user approved retaining source game time and adding a monotonic source
capture timestamp with explicitly real-second motion rates. The alternative
of estimating clock progression only from arrival times was not selected.
The performance comparison continued with the old protocol and is now complete;
it did not test the new timing contract.

Implementation uses a distinct position-only snapshot version 3. `source_time`
remains X4 game seconds; `capture_time` is read adjacent to the pose using an
explicit source monotonic clock; `real_velocity` is metres per real second.
The distinct field name prevents treating legacy game-second velocity as a
real-second rate. Versions 1 and 2 retain their original schemas and units.
A track cannot switch versions in place. Version 3 capture time must increase,
while game time may stay equal but cannot regress. Equal game time does not
imply a stationary pose: rates derive from observed position differences.

First samples, frame changes and unusable derivative intervals carry an unknown
rate. Capture origins need not equal client clock origins. Source lifecycle and
generation boundaries still fence clock resets. Actual X4 capture-clock behavior,
client playback integration and Internet behavior require their own evidence;
schema and synthetic-clock checks alone cannot establish those outcomes.

## First implementation checkpoint

The position-only V3 contract, pose-adjacent capture, real-second derivative,
Lua source encoder, Python source bridge and generic TCP receiver are now
implemented. [The contract and integration boundary](../docs/AUTHORITY-MOTION-V3.md)
separate this checkpoint from native playback, which then still refused V3. The source
session does not opt in automatically. Shared schema acceptance required
explicit refusal in older client-authority paths to prevent accidental unit
mixing. A track pins its snapshot version.

Focused validation, without a native X4 launch:

- The new schema/progression/transport checks and existing motion/latest tests
  passed together: 54 tests. They cover exact fields, both-clock digests,
  source-clock stalls/regressions, version switches and legacy native-apply refusal.
- Two sampler wrappers passed; the pure sampler wrapper passed again after the
  independent review added cross-track and hidden capture-before regression cases.
  Synthetic game clocks at 0, 0.5, 1 and 2 times the capture rate preserve the
  capture-based derivative. These are sampler checks, not playback checks.
- Five descriptor tests passed, including capture-enabled fake native ABI calls,
  callback bracketing/copying and invalid callback rejection. No game was started.
- Source V3, legacy Lua UDP/TCP and encoder checks now pass (five test methods).
  The first V3 integration exposed the receiver's old strict game-time test;
  it was corrected. The final retry also corrected a new test's tuple-unpacking
  mistake. The received samples preserve unknown rates and real-second rates.
- Three focused tests passed for explicit native-binding/legacy-authority refusal;
  four existing receiver regressions passed for snapshots/despawn, recipient
  subsets, reconnect identity and callback mutation.

Independent reviews covered registry append validation, capture ordering and
source/receiver clock handling. No native cadence, Windows or Internet result
is claimed. The full suite was not repeated; its previously recorded one error
and 26 skips remain unresolved and this checkpoint is not whole-project acceptance.

## Client playback implementation checkpoint

BIND3 now carries the unchanged V3 snapshot from the Python participant through
the Lua owner to the native playback factory. The buffer explicitly selects
capture time; legacy game time stays separate. The controller keeps the original
local arrival time, even across delayed binding, and retains version and clock
progression checks across pause/reset. The recovered-client wrapper preserves
both clocks in separate bounded diagnostic rows. Native one-shot apply and
legacy client-authority remain V1-only.

Review also found that callbacks could alter an already validated initial
snapshot before its first setter. Initial alignment now freezes expected values
and checks container, vector and metadata identity after callbacks, refusing
prewrite changes without a setter and retaining uncertainty after a possible
write. This protects both legacy and V3 alignment.

Validation used fake game/native-ABI functions, not X4:

- 24 Python participant/IPC/apply/STOP tests passed.
- Nine Lua owner/buffer/controller wrappers passed. Additional focused capture
  checks passed after review added legacy-estimator isolation and the V3 rate
  bound of 5000 metres per real second.
- Initial-alignment checks passed, with 35 native-adapter cases covering V3
  metadata, shape and callback mutation. The affected wrapper was rerun after
  fixing a false-value rate validation edge.
- Three recovered-client composition methods passed, including six new V3
  scenarios and existing legacy alignment/runtime/pause cases. The V3 method
  passed again after the initial-alignment mutation fence changed.

The composed V3 fixture holds game time at zero, interpolates from 1000 to
1002.5 metres, predicts to 1012.5 metres using the explicit real-second rate,
then expires according to original receipt time. STOP waits for control release.
Invalid capture order, game regression and version switches cause no additional
write. A sparse update still fails the existing 50-metre running correction
bound. These observations establish the simulated composition only.

The previously failing full-suite worker test passed individually with current
socket-count diagnostics. Its original intermittent failure remains unexplained;
the earlier full run and 26 platform/data-dependent skips are not a pass.
No full suite, native X4, Windows or Internet trial was repeated at this stage.

## Source-session and correlated evidence integration

The source installer and Lua runtime now accept an explicit, default-off
`real_time_motion` setting. The native factory uses `net.monotonic` adjacent to
the pose query. The latest collector, source probe and bounded supervisor retain
both clocks and real velocity. The source probe refuses a configuration/version
mismatch before delivery. The supervisor restricts its new flag to the existing
bounded ENH-870 latest-playback diagnostic; legacy local-pair and candidate
selection modes remain outside this experiment.

The V3 paired oracle requires the separate native capture-clock rows. It
correlates both clocks to acknowledged original samples and uses real velocity
for final prediction. A summary may describe a previous write read back after
a newer delivery, so its clock can match an earlier acknowledged sample within
the recorded delivery count. Initial and final clocks must still match their
exact source samples. The reader retains file identity and observed bytes even
while waiting for a trailing clock row; replacement, truncation and rewriting
during that wait are refused. Optional initial-alignment records retain the
3-metre readback bound and original local arrival-age check.

Focused validation, without starting X4:

- Ten source installer/fake-Lua-runtime tests passed.
- Thirteen collector tests passed, including 0/0.5/1/2-times game-clock rates,
  explicit configuration, real-rate preservation and clock/version refusals.
- Three supervisor option/result tests passed.
- Four probe methods passed in 7.215 seconds. The integrated method sends 26
  V3 samples through real loopback UDP/TCP with simulated endpoints, a stalled
  game clock and a slow recipient. Enrollment and final receipt remain
  protected; intermediate positions can coalesce, with both clocks retained.
- Thirty distinct evidence methods passed across the initial batch and focused
  follow-ups, using synthetic log records. Independent review found and fixed
  loss of the observed log prefix during pending-pair retries and during growth
  on a second read. Both legacy and V3 readers now preserve the first observation.

These checks establish protocol and evidence composition, not real X4 cadence,
native movement, Windows compatibility or Internet play. Existing motion limits
were not increased, and no ordinary configuration silently enables V3.

## First native V3 attempt (2026-11-18)

The bounded two-Linux-X4 attempt at `a3296cf1` failed. Private artifacts are in
`.local/private-paired-capture-native-20261118-01/`, launched using
`.local/authority_paired_capture_scope_20261118_01.py` and its fresh 488-file
manifest. The private runner enables the shared V3 source-session flag and
retains the approved initial alignment and replica-control fixtures. It does
not change playback bounds. The source is the same isolated confirmed checkpoint
with SHA-256 `2b07a55d0d5fda0ef08de8a6b9a562100d745ae39076d1a7092f5e3c150f5994`.

Both instances loaded and reported a registry count of 10,082. This is not a
proof of complete ship coverage, exact loaded bytes or ongoing synchronization
of that population. Movement remained limited to registry index 1318, ENH-870.

The source captured and queued three V3 samples; the host retained only ACK 1.
The native client recorded initial alignment with zero readback error, preserving
both clocks in its capture diagnostic. Its next reported source sequence was 3,
with two received samples, 57 observations and zero running readbacks. The
261.570595-metre correction was refused by the unchanged 50-metre bound. No
running write or STOP/release completion was proven. The enclosing observation
and paired-playback acceptance both failed; partial log records are diagnostic
evidence only.

| Interval | Capture seconds | Game seconds | Capture to queue (later sample) |
| --- | ---: | ---: | ---: |
| 1 to 2 | 0.888236 | 0.889897 | 0.600323 s |
| 2 to 3 | 0.777787 | 0.777933 | 0.644893 s |

Sample 1 took 0.610915 seconds from native capture to the collector's queue
timestamp. These are same-host monotonic measurements, not remote clock-offset
estimates. Both capture intervals exceeded the existing 0.75-second continuity
bound; skipping sample 2 left a 1.666022-second span from 1 to 3. Game time ran
close to real time in these two intervals, so clock-rate mismatch does not
explain this particular failure. The V3 clock change does not itself improve
sampling or delivery cadence.

Collection lasted 2.966203 seconds. Three polls used 1.360626 seconds in total;
each completed pull took approximately 0.74-0.79 seconds. Existing batched
checkpoint checks were enabled. Follow up on repeated synchronous ownership and
checkpoint work in that path before another native run; do not repeat this
unchanged attempt or widen the correction/freshness bounds.

Owned process/cgroup and Xauthority cleanup passed. Selected code pins, the
source checkpoint and Steam identity were unchanged, and a separate `/proc`
executable scan found no remaining X4 process. Cleanup is distinct from the
failed motion observation. No Windows, Internet or gameplay acceptance is
claimed.

## Full check and fixture corrections

The strict check at `a3296cf1` ran 5,263 methods in 554.517 seconds and exited 1:
one failure, three errors and 56 skips. Its log is
`.local/check-capture-clock-20261118-01.log`. The four findings were outdated
fixtures: a log test rewrote an observed partial line, a simulated sector adapter
omitted the now-required replica-binding module (two modes), and a setter fixture
omitted its explicit V1 sample version. The fixtures now append without rewriting,
load the real binding module and identify the V1 sample. No production guard was
relaxed. All four selected methods passed afterward, including both sector modes.
An independent review found no further issue in these three test-file changes.

Thirty of the 56 skipped methods had existing local prerequisites that were not
selected in the full-run environment. All 30 passed separately after native
cleanup in 428.238 seconds, without skips. They cover pinned Linux/Windows image
checks, Zig compilation, crypto library/relay behavior, MD schemas and matched
stock UI references. The Windows image checks run on Linux; they do not establish
Windows execution. Exact selected IDs and results are retained in
`.local/check-capture-clock-missing-input-tests-20261118-01.txt` and
`.local/check-capture-clock-missing-input-results-20261118-01.log`.

The crypto library was freshly built from current sources using the existing
pinned Zig toolchain and build flags, without rebuilding or installing a game
gate. Its SHA-256 is
`92fe5bc5255086bd6181d69fff001d6360d59fad8b3397bede3a846a977548e6`;
before/after source and local-header hashes are retained in
`.local/check-capture-crypto-20261118-01/build-result.json`. Prepared MD schemas
match their recorded provenance checksums. The existing stock UI reference uses
the previously documented catalogue match; that match was not repeated here.

The remaining 26 methods depend on Windows execution or missing reference
inputs. The original strict run remains failed; selected follow-ups cannot turn
it into a full-suite pass. No unchanged full-suite rerun was performed.

## Follow-up: avoid duplicate latest-operation entry checks

Read-only review found that explicit batched `begin_latest` and `poll_latest`
each performed an entry check, then immediately repeated it before the first
socket readiness observation. No external callback, I/O or protected mutation
occurred between those checks. The shared context now supplies that entry check
once. Unbatched operation ordering is unchanged. Both full saved-check boundaries
in batch mode, post-select ownership checks, obsolete-reply lifetime checks and
exception restoration remain intact. The generic quiet-socket helper still
performs both its own entry and post-select check.

Forty-five focused methods passed in 39.353 seconds across the latest saved-check,
real helper, running-source binding and recovered-source probe modules. A new
adverse case invalidates ownership during readiness observation and verifies that
both modes refuse the operation without sending a request or delivering a sample.
Independent review found no boundary/order regression. Log:
`.local/check-capture-entry-guards-20261118-01.log`.

This removes one redundant nested guard chain per batched begin/poll operation.
Its native timing benefit is unmeasured and may be insufficient. No second X4
run followed this small change. Investigate the remaining measured overhead
before deciding whether another native attempt is informative.

## Windows executable playback with a stalled game clock

At `07364e54`, one isolated Windows X4 run under Proton passed V3 playback from
a synthetic local UDP source. Source game time remained zero; monotonic capture
time and explicit real-second rates drove 25 movement updates after enrollment.
All 26 packets were acknowledged and correlated with the native log. The ship
moved exactly 20 metres, with zero final error, 1,005 readbacks and confirmed
STOP/pause. Movement-update capture intervals were 0.344-0.404 seconds;
INITIAL-to-STOP elapsed time was 9.904 seconds. This validates the Windows game
code path for the new clock basis, not the nominal schedule or actual server
cadence. No server, TLS connection, native Windows OS or WAN participated.

Seven assembled Windows fixture tests also passed using real TLS/file/TCP/UDP
loopback with simulated Windows/game endpoints. They cover V3 fields and
receipts, a stalled game clock, duplicate/regressed capture time, version changes
and cleanup ordering. Full evidence and limitations are recorded in
[the client report](AUTHORITY-CLIENT-PLAYBACK-20261117.md#windows-v3-capture-clock-playback-under-proton-2026-11-18).
The failed real-source Linux attempt above remains unresolved. No repeated
paired-X4 run or change to the diagnostic guard policy followed this result.

### Composed TLS client path

A subsequent single-game run at `f67aa76e` connected the real TLS/file transport,
`ObservedClientSession` and `ParticipantMotion` to Windows X4 under Proton.
The simulated server offered the pinned checkpoint and sent 26 V3 packets.
All receipts and native clocks correlated; final displacement was 20 metres
with zero error. However, update gaps were 0.784-0.821 seconds (enrollment to
first update: 1.525 seconds), all above the 0.75-second continuity bound.
Native summaries showed only held positions, not interpolation/extrapolation.
The whole-cycle guard instrumentation recorded 979 calls taking 28.247 seconds
of wall time. This locates substantial work in the client diagnostic path; it
does not measure X4 server simulation performance or establish that the proposed
guard policy will meet cadence. No policy or playback bound was changed.
See [the complete evidence](AUTHORITY-CLIENT-PLAYBACK-20261117.md#composed-tls-and-windows-x4-v3-playback-2026-11-18).

## Allocation-only guard investigation (no game run)

A bounded follow-up at `e5d88a49` compared fresh observations without retaining
results between checks. All candidates and benchmarks remain private in the
detached worktree `.local/agent-worktrees/steam-observation-20261118-01/`.
The main checkout, audited native runners and their manifests were not modified.

A first candidate read executable/start-time data only for Steam processes.
Although 80 live pairs returned the same Steam identity, this changed failure
behavior: a short `/proc/<pid>/stat` for a non-Steam process can raise an uncaught
`IndexError` in the original collector. Skipping that read suppresses the error.
This candidate was rejected as a behavior-preserving replacement.

The retained allocation-only candidate uses string child paths for the full
process scan and `os.stat()` directly for metadata snapshots. It preserves the
fresh UID/command/executable/start-time reads, their order and exception handling;
the start-time helper is unchanged. Focused fixtures invoke the actual original
collector and candidate against the same temporary process entries. They agree
on ordinary rows, executable permission failures, the uncaught short-stat error,
and an earlier readlink failure preventing a subsequent start-time read.

Eighty alternating live full-process comparisons returned equal snapshots.
Median collection times were 5.923 ms for the original and 5.279 ms for the
candidate, a 0.644 ms reduction. Eighty paired metadata passes over the 505 pinned
paths also matched: medians were 3.167 ms with `Path(path).stat()` and 1.936 ms
with `os.stat(path)`, a 1.231 ms reduction. Separate checks matched regular-file
and symlink snapshots for the existing string/Path input types.

The sum of these separately measured savings is approximately 1.875 ms, or 6.5%
of the preceding native run's mean 28.9 ms environment-check duration. This is
only an estimate: no combined guard, active-game, TLS-loop or real-source cadence
improvement was measured. It does not establish that either client or source
will meet the continuity bound. The candidates are retained for a future
justified diagnostic revision, not integrated into production or existing pinned
runners. No repeated game run or broad test-suite run followed this investigation.

Private evidence (paths relative to that detached worktree):

| File | SHA-256 |
| --- | --- |
| `.local/authority_guard_allocations_private_20261118.py` | `c7d6d9d1ea0d13b229ba628696f7b7dc7be485b65944949d2983fa7c61ab685e` |
| `.local/bench_guard_allocations_private_20261118.py` | `99393e23f714aaf4d6b5b44f3266e85bbb5f07d83b0e404639b17c5ac84f5ed5` |
| `.local/guard_allocation_benchmark_20261118.txt` | `9deb3eaa3f70a1e26dffa121692c506a8e49f585efa11009e8990b4e057745a3` |

## Diagnostic guard policy (approved for bounded experiment, not implemented)

This heading preserves the approval checkpoint; implementation subsequently
started on 2026-11-20 as recorded below.

On 2026-11-18 the user explicitly approved this bounded experiment. A subsequent
request paused the work before implementation or testing began. The following
scope is authorized for the isolated pair upon resumption; general gameplay
acceptance remains unproven.

The remaining source path repeatedly revalidates process, socket ownership and
the saved baseline around external callbacks and I/O. The native attempt records
216 active-guard calls taking 5.268442 seconds and 21 checkpoint checks taking
2.816292 seconds during the 11.813666-second source diagnostic. These inclusive
timings overlap: they must not be added or treated as isolated CPU costs. Existing
profile evidence and this run justify investigating that path, but do not prove
that a particular relaxation will satisfy the movement bounds.

Approved scope: an explicit diagnostic-only policy for this
isolated source/client pair, with full validation before admission and on
pause/stop or lifecycle change, and expensive process/socket/checkpoint
revalidation at a maximum age of 250 milliseconds during motion. If a refresh
cannot complete within the allowed age, motion must stop rather than reuse an
expired result. The implementation must first establish which local checks can
remain immediate (for example, retained process-handle exit detection), without
pretending a cheap check proves full socket or file ownership.

Session identity, epoch/generation, ordering, source clock progression, protocol
admission, callback reentrancy fences, lifecycle barriers and all playback bounds
remain immediate. The current strict policy remains the default. The proposed
policy would not establish unchanged file/socket ownership at every callback:
an external change could remain undetected within the allowed age and a stale
sample could be processed before detection. Start/end validation cannot undo or
prove the absence of that intermediate effect. Isolated disposable profiles and
owned cleanup remain required.

Approval authorizes developing and measuring this policy, not declaring it
safe for general gameplay or claiming native success. First validate the age,
expiry and lifecycle behavior with simulated changes and representative local
guard costs. Only then consider another bounded X4 attempt. The user has accepted
the changed validation guarantee for this isolated experiment.

## Diagnostic guard implementation (2026-11-20)

The user resumed work from `10ec3f40`. `tools/dev/authority_diagnostic_guard.py`
adds `DiagnosticEnvironmentGuard`: zero cache duration is the default; optional
reuse is capped at 250 ms and measured from the beginning of a successful full
check, including the subsequent immediate check. At expiry, the next guarded
operation must refresh synchronously. A refresh consuming its entire lease is
rejected. Immediate process/local-descriptor checks run on every call and after
each full refresh. Failures and reentry permanently disable the guard.

The `strict()` context requires full checks at both boundaries and at every
existing check inside the block, then invalidates reuse. Callers must use it for
admission, control/STOP and lifecycle changes. It does not alter session,
sequence, clock, protocol or motion validation. There is no background monitor:
an idle or descheduled caller need not detect a change within 250 wall-clock ms,
but cannot reuse an expired observation on its next call. The accepted stale
window remains real; neither immediate liveness nor later full validation proves
unchanged remote ownership or file contents during that window.

`LinuxDiagnosticProcess` retains a pidfd between two existing process-identity
checks. Its hot check detects process exit and compares the caller's retained
socket descriptors, inode identities and local endpoints. Executable/prefix,
remote socket ownership and checkpoint checks remain the full callback's job.
The caller owns game shutdown; closing this helper only closes its pidfd.

Twelve focused tests passed in 0.075 seconds with no skips. Nine use deterministic
clocks/callbacks; three use disposable Python children and local UDP sockets to
check actual exit detection, descriptor replacement and lifetime rejection.
The tests explicitly demonstrate the accepted stale interval, refresh duration,
expiry after a slow immediate check, lifecycle boundaries and permanent failure.
Log: `.local/check-diagnostic-guard-20261120-01.log`. Independent review of the
policy core found no concrete issue; no game/native/full-suite rerun was made.
At this utility checkpoint, runner integration and active-X4 cadence benefit
were unverified; the subsequent bounded native-runner result is recorded below.

## Diagnostic guard refresh cost (NO-GAME, 2026-11-20)

The first short measurement (`.local/guard-cost-20261120-01`) lasted only
153 ms, never reached lease expiry and encountered an obsolete transient Xauth
path. It is insufficient for cost or acceptance conclusions. The replacement
measurement used `.local/guard-cost-20261120-02/measure_guard_refresh.py` and
completed 120 hot-loop calls with 10 ms modeled work per call in 1.3227 s.
The hot loop made 6 full refreshes and 114 reuses; four forced checks at the
entry and exit of two strict blocks bring the total to 10 full checks and 114
reuses across 124 guard calls. Full-refresh callback mean was 17.2315 ms and
maximum 20.0655 ms.
The raw hot-loop statistics include the two preceding strict calls; the
hot-loop-only counts above exclude them.

This exercised a real Python child and two local UDP peers, process/socket
identity checks, the initial witness check, metadata on every full refresh and
Steam identity on every full refresh. All 504 existing pinned paths matched
their exact hashes before and after; metadata remained stable during the run.
Exactly one obsolete transient path was excluded:
`/run/user/1000/xauth_jsBXKr`. Owned child, process guard and receivers all
cleaned up; the result reports no failures. This measures only refresh cost in
a synthetic no-game setup. It does not check the X4 prefix or establish game
performance, cadence benefit, TLS integration, Windows behavior or WAN/pair
operation.

Evidence: `.local/guard-cost-20261120-02/result.json` (SHA-256
`ec455d3fb5940a9d93e00fc2340f8e338836529516d2e8da5a7ccecf1b035916`) and
`.local/guard-cost-20261120-02/measure_guard_refresh.py` (SHA-256
`35d4b1b401042c7bdd5e8614fec6dccf46227d1013564a6dbfcc3ac237b91ea5`).
The result is a bounded cost measurement, not a broad performance pass.

## One audited synthetic-TLS/Windows-X4-under-Proton trial (2026-11-20)

At HEAD `7df3ce432675d7600604f0fa65d5dd22b4b781fb`, the audited private runner
`.local/authority_windows_tls_capture_proton_20261120_01.py` completed one
bounded run with `--guard-cache-ms 250`. The result is
`windows_tls_capture_observed`: the actual Windows X4 executable ran under
Proton, using synthetic motion and a simulated server over real loopback
TLS/file/TCP. All 26 V3 samples were acknowledged, final position error was
0 m, and STOP was drained with uncertainty `0`; 563 readbacks were recorded.
STOP followed INITIAL by 6.9113 s of local elapsed time.

The 24 movement-to-movement capture intervals (excluding enrollment) ranged
from 0.166025221 to 0.233972651 s, with median 0.2000021405 s; none exceeded
the 0.75 s continuity bound. The enrollment exchange took 1.8400 s and its
capture gap was 2.156489385 s. Keep this initial delay visible: it precedes the
24 movement intervals and is excluded from their range. The six phase summaries
reported `held` once, `interpolated` four times and `extrapolated` once. These
are runtime observations, not a visual smoothness assessment.

The optional guard recorded 282 full checks and 926 reused checks. Its wrapper
reported 1,196 calls in 11.275 s, excluding 12 strict-context boundary calls.
The earlier 979-call/28.247 s whole-cycle instrumentation used a different
scope and is not a comparable cost or speedup baseline. This one run validates
the opt-in cache path for this bounded client scenario only; the strict default
and motion bounds remain unchanged. It does not exercise the real source-X4
path, a native Windows OS, WAN or two machines. The audit explicitly excluded
Wine/X4 execution and identified the single synthetic-server scope.

All owned cleanup, protected-input, Steam identity, TLS-thread and pin checks
passed; no errors were recorded. Evidence: `.local/windows-tls-capture-proton-20261120-01/result.json`
(SHA-256 `2f9d31c3bca15fd943fba3480d414b15034ae0f187b2ed035e8a057d4fce7541`),
`motion-cycle.json` (SHA-256
`51955419e55a07e7bc05d238ec98eb4e31593db2892d8932f1800b7e89be3197`), audit
`.local/authority-windows-tls-capture-reviewed-20261120-01.json` (SHA-256
`9aa6caddba08c7c2e42c23bd6f8ef7d165cf12e330b6bd019a143fbeca251e48`) and runner
`.local/authority_windows_tls_capture_proton_20261120_01.py` (SHA-256
`ca4c71bfe3240827b4cdcbf80589f791f0b02c9f5ddd4f7bccc00b2b12b85e83`).

Next: port the same optional policy to the existing real-Linux-source/client
pair harness, audit it, then make one justified trial. Separate hosts are now
available but have not been tested together. No rerun of this Proton attempt is
planned from this evidence alone.

## Real-source diagnostic guard integration (2026-11-20)

Commit `0fa6b9d9` adds the opt-in `--diagnostic-guard-cache-ms 250` to the
bounded ENH-870 real-time/latest saved-playback path. Zero remains the default.
Reuse applies only to the full source environment and saved-checkpoint checks
while collecting motion. Both checks refresh before and after collection;
the reuse flags reset even when collection fails. Binding, STOP, drain and
checkpoint/worker lifecycle operations retain their existing full checks.

Every cached source check still checks the deadline, pinned session, baseline,
participant, player lists and readiness, bracketing fresh process/client
liveness checks. The cached checkpoint path brackets its non-IPC lifetime
check with session/baseline/status checks. Lower-level process/socket/protocol,
sequence and motion validation remains unchanged. This is deliberately narrower
than caching all validation in the test harness: parent and client-worker checks
may still dominate elapsed time.

The focused source-probe module passed 31 tests in 42.088 s. After the final
player-list invariant change, the three cache integration cases passed in
7.615 s and the default lifecycle case passed in 0.004 s. These exercise local
UDP/TCP and simulated source/client behavior, including session loss before a
pull and strict exit checks after a collector error. Syntax and diff checks
passed. Test output was captured in the agent tool session, not a separate log;
the unchanged tests were not repeated merely to create one. This is not native
X4 evidence.

### First real-source trial with bounded guards: rejected before sampling

One audited local Linux source/client run at `0fa6b9d9` used private runner
`.local/authority_paired_capture_trial_20261120_01.py` and manifest
`.local/authority-paired-capture-reviewed-20261120-01.json` (489 pinned files).
Output is `.local/private-paired-capture-native-20261120-01/`.
The overall run failed: `diagnostic refresh exceeded its cache lifetime`.
The active guard's forced entry refresh completed, but the checkpoint guard's
first refresh exceeded the 250 ms budget. Neither guard reused a result;
there were zero pulls, zero captured samples and zero motion receipts.
This provides no new cadence, displacement, interpolation or gameplay evidence.

The source diagnostic reached collection after 10.4847 s in total. Across its
setup and failed collection entry it recorded 61 full environment callbacks
in 3.6249 s and eight saved-checkpoint callbacks in 3.4761 s. These are aggregate
wall times; callbacks may contain each other, so the totals are not additive
and do not isolate CPU cost. The 250 ms ceiling and all motion bounds remain
unchanged. Inspect the checkpoint callback's repeated work before deciding on
another native trial; do not rerun this unchanged attempt.

The server reported the expected marker and register count (10,082), completed
pause/save/checkpoint publication and resumed for the admitted test client.
That register observation does not prove complete universe coverage. The outer
scope explicitly reports `success=false`, `observation_valid=false` and
`display_released_after_runner=false`. Owned-cgroup cleanup and Xauthority
cleanup were confirmed; no owned game processes remained. Steam identity,
pinned dependencies and the original checkpoint were unchanged at their final
checks. The run remains an overall failure despite those cleanup results.

Evidence SHA-256: `trial-result.json`
`6ee0ba103d8e506ae2a8f31042efae2332496fdc16d3114256b416da0ac43924`;
`paired-server/result.json`
`05f563e3836dbfa8f0098f9ed5866bf1e6ce523eba1bd49a8afeb9f695edaddd`;
the reviewed manifest
`fd4edb43afb652a24326a8e1ed0241ed64cbb6b2852a441930d81ba8f93e5693`.

## Checkpoint full-callback scope follow-up (NO-GAME, 2026-11-20)

Commit `a5ddb5d97f7ebbd7b9b34e31894e2b28266d544b` adds an opt-in checkpoint
full callback within the existing `playback_identity_scope`, limited to its
synchronous IPC request. Nested pump iterations keep their fresh targeted checks; full discovery remains at scope
boundaries. Strict default remains zero. The optional 250 ms lifetime includes
scope entry and exit. Independent guard review found no expansion of the
reader-lease or reentry boundary. The initial checks below used no game; the
subsequent native trial is recorded in the next section.

The private IPC probe made three metadata requests per case, with nine helper
pumps per request, across no-delay, modeled 10 ms/pump and modeled 40 ms/pump
cases. Observed request elapsed ranges were 0.000397318-0.000440828 s with no
delay, 0.09067295-0.09072000 s with the 10 ms synthetic delay, and
0.36071266-0.36085656 s with the 40 ms synthetic delay. The delays are modeled,
not native helper costs. Send timings include nested pump time; nested timing
scopes are non-additive. All three cases cleaned up. Evidence is
`.local/checkpoint-ipc-cost-20261120-01/result.json`.

The corrected focused source-cache tests passed: 3 tests in 7.613 s, recorded in
`.local/check-checkpoint-scope-20261120-02.log`. The default lifecycle test
`test_two_samples_stop_then_guard_shutdown` also passed in 0.003 s; log:
`.local/check-checkpoint-scope-default-20261120-01.log`. The first fixture
attempt expected maximum nesting depth 2, although the legal updated path
reaches 3, and asserted scope presence on a strict-cleanup callback. The fixture
was corrected; this failure does not establish a production defect. These results
are synthetic/no-game scope and IPC evidence, not crossplay, native timing or
performance proof. At this checkpoint, versioned native attempt 02 and a
separate laptop menu-only attempt were prepared but not started; subsequent
native attempt 02 results are recorded below.

## Second real-source Linux pair trial: playback failed at sequence 3 (2026-11-20)

The next audited local two-process Linux X4 attempt ran the checkpoint cache
changes at commit `a5ddb5d97f7ebbd7b9b34e31894e2b28266d544b`, with a 489-pin
manifest. The permitted delta was limited to the source-probe change and
versioned private paths. The runner exited 1. The first checkpoint entry
passed and subsequent checkpoint checks reused observations. Four source
samples were captured, prevalidated and queued after five pull attempts; the
client confirmed only receipt sequence 1. Cache statistics were 179 active
guard calls (7 full, 172 reused) and 20 saved-checkpoint calls (7 full, 13
reused).

Client initial alignment succeeded at 0 m error against a 3 m tolerance at
local time 30.092051664. Playback then failed at source sequence 3, local time
30.483157812: the client remained at its initial pose while the target was
79.200777 m away. The existing 50 m distance limit was unchanged. Capture gaps
between the four queued source samples were about 0.311742, 0.231504 and
0.250431 s. These few intervals do not establish full cadence, visual
smoothness, Windows behavior, WAN operation or gameplay.

The source diagnostic ran 10.9733 s including 1.6970 s in collection. It
recorded 67 full callbacks taking 3.6037 s and 14 checkpoint callbacks taking
2.9769 s. These aggregate callback times are nested and non-additive. The
supervisor grouped two sub-exceptions under `latest playback and strict guard
boundary failed`; reported leaf types were `ValueError`, `RuntimeError` and
`RuntimeError`, without more specific messages. The precise cause is
unresolved, and another strict-boundary failure is not excluded. The sequence-1
receipt is not a successful playback result.

The outer observation is invalid and display release was false. The overall
trial failed despite confirmed empty owned-process cleanup, cgroup removal and
Xauthority cleanup. Steam identity, pinned dependencies and the source were
unchanged. No rerun is justified yet; next is read-only analysis of the
initial-alignment-to-sequence-3 transition.

Evidence SHA-256: `trial-result.json`
`1ce260370946416f690045dbeee375716ecfe85c8cec9ba87e036929ee29bd36`;
outer `result.json`
`d6195d2b3319def24bb4334716862b0eec24a0d06ac279309be8d616f7f930e3`;
`paired-server/result.json`
`0c0e7254b0689783cbdc7e43a76cf09825321bd21a7ad754541dbc0d1dc2a5c2`;
client `engine-output.log`
`1e808b31333dcfcc1aaf2b18b397961889ede7384290e19edc00786ba8c43fc0`.

### Recorded-sample mechanism comparison (NO-GAME)

A single private replay used the unchanged production Lua playback and buffer
modules with native samples 1–3. Client arrival times for samples 2 and 3 were
modeled from the observed first arrival plus host queue-time differences;
their actual arrival and playback tick times were not recorded. Omitting
sample 2 produced a 79.225 m correction and a distance failure before any
write. Applying sample 2 at a modeled earlier tick produced two successful
Lua write callbacks, with steps of 46.218 m and 34.987 m. The 50 m step limit,
1 s freshness limit and 0.15 s buffer delay were unchanged.

This demonstrates a possible mechanism, not the actual native event order.
The fake write callback updates an in-memory pose; it provides no X4 write or
readback evidence. A transport rule that retains sample 2 would still need to
establish that playback applies it in time. Native logs do not distinguish
an omitted intermediate sample from delayed client playback. Before selecting
a queue or playback-policy change, add bounded receive/tick evidence and
discuss the resulting proposal with the user. No native rerun or production
policy change followed this comparison. Private artifacts:
`.local/playback-replay-native02-20261120/replay.py` and `result.json`.
