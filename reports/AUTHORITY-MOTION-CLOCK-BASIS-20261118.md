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
