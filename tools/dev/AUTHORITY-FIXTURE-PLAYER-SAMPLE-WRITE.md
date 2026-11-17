# Experimental fixture player sample write

The opt-in `--fixture-player-sample-write-slot` (1 or 2) requires the existing
private two-client fixture source diagnostic and cannot be combined with its
rejoin mode. The chosen source remains pinned to its original fixture sector.
Defaults do not install or activate the writer. This is a disposable Linux
loopback experiment, not an internet, Windows or gameplay implementation.

The separate `--fixture-player-sample-write-after-throttle` option records a
baseline, requests and acknowledges a bounded client throttle pulse, and waits
for a sample timestamped after the client's STOP callback. That first sample is
only a fence: a later sample with a higher sequence and game time is the write
candidate, and must differ from the original baseline by at least one unit.
This ordering relies on the source sampler allowing only one outstanding read
and on serialized client Lua/MD callbacks; it is not an atomic measurement.
The samples prove a difference across that interval, not that the impulse caused
it or that the ship was stationary beforehand. The post-pulse collection has a
300-second limit, also bounded by the overall session deadline.

After a validated TCP SAMPLE2 pull and its post-pull guard, the supervisor sends
one correlated request over a separate owned, loopback UDP socket to the
existing server world-bridge update owner. The request carries portable values
and the original full SAMPLE2 digest; local X4 actor/sector handles never leave
the server process. The Lua/MD path checks the four-entry registry in both
directions against the saved fixture slot, epoch, slot-specific sector, player
ownership and local player exclusion. It uses the server's own FFI actor and
sector, checks docking and parent context, and allows one setter attempt.
The supervisor checks the owned X4 PID/start/executable and UDP peer, guards the
session and grant before and after I/O, and never retries after dispatch.

This writes **XYZ only** and preserves the server's locally read rotation. The
full SAMPLE2 digest binds the recorded source but source orientation, velocity
and angular rate are not applied. The writer requires 1–50 units between its
local starting position and the target; a target already matching the server
is rejected without a write. Its immediate local readback must be within 0.5
units of the target. The result includes starting, target and readback values;
it proves no persistent, smooth or physically valid motion and no collision
clearance. The writer runs while the server is unpaused; the previous successful
local-offset X4 experiment used a paused server and does not establish that this
variant will work in native X4. MD and Lua checks sample live state and are not
atomic with the write. On timeout, lost response or failure after entering the
setter, the write is uncertain and the owner is fenced; never retry it.

For this one experiment **source/server sector-frame equality is assumed**,
based on earlier sequential Linux reload measurements. Those measurements did
not establish equality for the actual concurrently running server and client,
Windows, different checkpoints, moving objects or arbitrary sectors. A
successful one-shot write does not upgrade that assumption to proof. Checkpoint
marker and saved registry identity remain separately guarded assertions and do
not prove exact loaded bytes. A changing join/lease/sector or failed guard must
end the experiment; this is not a reusable authority or replay protocol.

`tests/authority_fixture_player_sample_writer.lua` tests the real writer with a
synthetic X4 ABI. `tests/test_authority_fixture_sample_write_chain.py` exercises
the Python IPC and the real Lua writer over the native UDP module with fake
X4/MD functions. `tests/test_authority_fixture_player_sample_integration.py`
checks private installation, source selection and evidence validation. None
starts X4 or proves native setter behavior for a client sample.
