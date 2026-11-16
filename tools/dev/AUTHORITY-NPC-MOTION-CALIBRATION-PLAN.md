# Proposed non-player motion and velocity calibration

This is a plan for a bounded, opt-in diagnostic, not a production movement
policy. It has not been implemented or run. Use an isolated disposable Linux
profile and copied save, never the normal player profile. The first target is a
single **unpiloted** non-player test ship; the experiment does not establish
that autonomous NPCs can safely be controlled this way.

## Existing evidence and unresolved questions

* The default-off [`motion_buffer.lua`](../../src/authority/lua/motion_buffer.lua)
  reconstructs position and orientation and can return `linear_velocity`. That
  vector is the derivative of its rendered translation per **observer-clock
  second**, not a native velocity readback. At a first render, clock snap,
  missing rate and other ambiguous points it can be absent. A known frozen
  prediction can instead yield a real zero. The buffer makes no X4 calls and
  does not transform coordinate frames; see
  [its contract](../../docs/AUTHORITY-MOTION-BUFFER.md).
* The old LAN NPC path transmitted rates for reconstruction and wrote rendered
  positions. Its separate ghost-ship velocity path guarded identity, expiry,
  undocked state and nearly aligned zone/sector/cluster orientations before
  requesting MD `set_object_velocity`. This is not evidence that an arbitrary
  rotated or moving parent accepts a sector-frame vector. The old path's reset
  is not proof of safe release for AI-controlled ships.
* A [single fixture observation](../../docs/AUTHORITY-FIXTURE-VELOCITY-EXPERIMENT.md)
  recorded approximately 10 m displacement per real second between samples,
  then near-stationarity between the final samples; the first final sample had
  returned to the original baseline position. The engine also logged conversion
  and arithmetic-type errors for the requested expressions, so setter effects,
  units and release are inconclusive despite the historical success flag. There
  was no native velocity-vector readback, proven axis, restoration of the
  original mode, or independent collision-clearance proof. The earlier
  [NPC flight experiment](AUTHORITY-NPC-FLIGHT.md) used position writes and
  readbacks, not a native velocity setter.
* In the corrected [NPC signal comparison](authority_npc_signal_ab.md), one
  piloted Patrol ship remained stationary for 50.120 game seconds after a
  zero-velocity intervention and release. A separate treatment associated one
  `patch_reset_moveto` signal with later motion. One control and one treatment
  do not prove causality, an unchanged order instance, or lossless restoration.
  Earlier unit-bearing zero expressions logged conversion errors; use validated
  plain numeric event values and reject relevant native conversion errors.

Whether the native setter expects the same frame and time units as the buffer
remains unproven. In particular, a derivative per real observer second must not
be assumed to equal the engine's velocity per game second. Zone/sector/cluster
orientation checks also do not establish correct treatment of moving parents.
The pose setter's orientation convention requires separate native calibration;
the buffer's Euler-coordinate angular rates are not a native angular-velocity
vector.

## Smallest useful native calibration

Prepare a single disposable case using the existing fixture-velocity and motion
test infrastructure. Before any setter, require a live, operational, undocked
ship with a stable direct zone parent and known sector, excluded from player
control and storage. Check the same local actor and parent immediately before
each operation and observation. The caller must independently establish an
appropriate clear test volume; a `safepos` request alone is not a collision-free
guarantee. Establish that the fixture is unpiloted and has no autonomous order
using valid getters and a known positive pilot control; an unavailable getter
or ambiguous null is inconclusive, not a free-seat proof. If these conditions
cannot be established, stop before mutation.

First constrain the case to stable zone/sector/cluster frames whose relative
bases pass an explicit alignment check. Record both real and game timestamps,
and require a measured normal, uninterrupted game-time progression. Calibrate
without time acceleration or pause transitions. This restriction is a test
condition, not an implementation for general frames or time scales.

Feed a few deterministic, bounded, timestamped samples into one buffer track,
retaining the sample sequence, frame token and rendered pose and optional rate.
On that same guarded actor, distinguish a small, independently clearance-checked
position write from a velocity-only interval, then exercise a bounded combined
pose/velocity interval. Use low, known positive X, positive Y and negative
components so the recorded sector-position changes can test sign and axis as
well as displacement. Preserve orientation unless a separately validated
orientation setter is available. Record every request, its matched receipt, the
buffer output and sector-position readbacks with real/game times. Check errors,
identity and lifecycle throughout. The intervals must permit displacement to be
distinguished from an idle baseline; an action receipt alone is not physics
evidence. Do not send an absent `linear_velocity`, reuse a stale vector, or turn
an unknown into zero. A known zero and an unknown value are different cases.

The native test needs an explicit bounded failure/expiry procedure and owned
process cleanup. Because the original velocity and constant-velocity state are
not read back, a requested reset is not a proven restoration. If a guard,
receipt, deadline, conversion or process check fails, stop and discard the
copied world; do not silently retry or use `patch_reset_moveto` on an NPC.
Termination and disposal contain this test, but do not undo an external effect.

A passing result would only show that these particular buffer outputs were
requested on this fixture and that the observed position changes were
consistent with the recorded inputs under the tested conditions. Finite
differences are not a native velocity-vector readback, and pose writes can
affect subsequent measurements. It would not prove visual smoothness,
collision-free movement, arbitrary coordinate transforms, preservation of NPC
AI, multiplayer delivery, Windows compatibility or combat/trade behavior.
The pilot-controlled NPC takeover/release problem remains a separate open
design and experiment.
