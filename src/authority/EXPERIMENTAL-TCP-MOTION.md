# Experimental admitted-socket motion delivery

`experimental_tcp_motion.py` is default-off. It uses the existing
`ExperimentalTCPJobDelivery` owner and its admitted `ExperimentalTCPControl`
sockets, reader lease and serialized writer; it opens no socket or listener.
The sender's caller must call `track(epoch, generation, index)` only after
establishing the real source lifetime and any necessary client creation. This
module does not authenticate the source or establish those claims. Track state
and tombstones are bounded, process-local and not persisted. A new lifetime for
an index is accepted only after the previous tracked lifetime has been closed;
old generation tokens cannot be reused in the same owner.

Snapshot v1 is the source-sampler contract: exactly `version`, `epoch`,
`generation`, `index`, `sequence`, `sector_macro`, `source_time`, `x`, `y`,
`z`, `velocity`. The tokens are 32 lowercase hexadecimal characters; index and
per-lifetime sequence are positive exact integers through 2^53-1. Source time
is finite X4 source game time in seconds (0..1e12); coordinates are bounded
finite values (±1e7). Velocity is explicitly null when unknown, or a complete
finite x/y/z vector (±5000), interpreted as a derivative per source game
second, not a proven native velocity. No actor or sector handle is transported.
A sector change must carry null velocity; downstream interpolation must reset at
that boundary. Macro equality does not establish cross-process coordinate-frame
identity.

Updates must increase sequence and source time. Per-index sends are rate limited
by source process monotonic time, configurable from 1/240 second to 10 seconds;
rate rejection does not transmit or alter a sample. Invalid, stale, unknown,
closed or inconsistent frames fault the motion and shared delivery/host;
delivery, membership, receipt, socket-lease and consumer errors do the same.
A `motion_despawn` message carries only the version and identity fields and a
new sequence, bypasses the pose rate limit, and fences this lifetime. It is a
transport tombstone: no X4 removal is performed or inferred. This path does not
observe or automatically generate destruction events.

`ExperimentalTCPParticipantClient` accepts motion only with an explicit
`apply_motion(sample, despawn)` callback. The callback must verify its actual
local object binding and return exactly true only once the sample is accepted;
it receives a copy, and mutation, false, exception, timeout or reentrancy
faults the connection. An `accepted` TCP receipt is a callback assertion, not a
position application or game-side readback. Earlier recipient effects cannot be
rolled back. This synchronous test interface is not yet connected to the
asynchronous MD/FFI binding module or to a motion buffer/setter. The surrounding
supervisor must fence every involved process on indeterminate failure and retain
profile locks through confirmed cleanup.

The tests use admitted loopback TCP sockets and synthetic consumers, including
two clients and interleaving with existing job delivery. They do not establish
an X4 binding, authentication, smoothness, Windows, Internet, complete universe
coverage or multiplayer gameplay.
