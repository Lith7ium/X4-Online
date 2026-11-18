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

## Decision pending

Two compatible directions need the user's decision before implementation:

1. Retain the existing game-time fields and add an explicitly versioned source
   monotonic capture time plus a clearly defined real-second rate or adapter.
   This supplies an additional timing anchor without requiring equal absolute
   clock origins, but changes the protocol and requires lifecycle handling.
2. Keep the wire fields unchanged and estimate source-game-time progression
   from their values and local arrival times. This avoids a wire change, but
   queueing, jitter, and source stalls are not reliably distinguishable without
   another timing anchor; uncertain prediction would need conservative bounds.

Neither direction has been implemented or chosen. This observation does not
by itself establish the best network clock or prediction policy.
