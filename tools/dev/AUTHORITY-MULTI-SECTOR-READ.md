# Opt-in two-sector source read experiment

This experiment reuses the separately verified,
marked two-sector archive and the existing single-X4 private-profile load and
cleanup harness. That archive contains exactly two registry entries: this is
not the 10,054-entry census checkpoint and it cannot show fleet-scale
performance, universe coverage, admission, another client or gameplay.
No save is requested, and no ship, order, position or velocity setter is used.
Only the existing update owner controls resume and final pause. A fault after
resume invalidates the run and the owner terminates the disposable process;
it does not save that state.

The existing marker/load and slot-2 paused read occur first. The new MD probe
then responds to each serialized request with one string carrying a unique
request ID, epoch, saved slot/index, local ship and local sector. MD checks the
stored fixture relationship, forward and reverse registry relationship,
operation and sector. Lua parses both local handles as exact uint64, validates
ship/sector and sector context, binds the first local handles for each slot,
checks that the two ships and their sectors differ, and requires later responses
to match. Slot 2 is also compared to the independently received initial local
read handle. Slot 1's initial handle is not independently established. These
checks are sampled and non-atomic; a runtime-to-saved-actor binding, formatting
of two component values in one MD string, and behavior for all failure paths
remain unverified in native X4. Local handles never enter the output.

The source alternates three samples per slot while running and then confirms
pause with two game-time observations at least 0.1 engine-real-time seconds
apart. Each FFI position is bounded by before/after engine real-time and game
clock readings; `GetCurRealTime` is an engine clock, not an OS monotonic clock.
The offline checker derives optional coordinate-units per engine-real-second
from positions using the recorded *after* times. These are finite differences,
not native velocity; the true position observation lies within each recorded
interval and values can be unknown on excessive intervals or rate. They are
not a smoothness, movement, physics, collision or latency proof. Both per-ship
game time and real time must advance; stationary samples are permitted.

The one archived checkpoint and its exact registry epoch/marker are pinned by
the reused archive verifier. X4 consuming exact loaded bytes is not independently
proved. The larger census archive requires a separately verified marker/origin
and a generalized safe sector-reference/resolve path before this experiment can
address it; increasing these hard-coded slots would not supply those guarantees.

Offline checks: `python3 -m unittest discover -s tests -p test_authority_multi_sector_read.py -v`.
A future native run requires independent review first, a fresh output directory,
a local display and the pinned game; use `python3 tools/dev/authority_multi_sector_read_live.py --help`.

On 2026-11-15, one isolated native Linux run succeeded. Both registered
ships in distinct sectors produced three correlated samples each, and the
positions of both changed over the sampled interval. The source was paused
again and owned-process cleanup reported no remaining members. The native
results support this two-entry read path and its observed response format;
they do not remove the identity, time, scale, client, or gameplay limitations
above. The finite-difference vectors remain estimates per engine-real second,
not native X4 velocity.
