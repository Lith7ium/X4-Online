# Source clock and playback: bounded offline observation

The paired source currently sends **source X4 game time**, while the playback
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
separate this support from native playback, which still refuses V3. The source
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
