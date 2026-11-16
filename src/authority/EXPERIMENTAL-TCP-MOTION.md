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
A source sector change must carry null velocity. A selected peer that already
received this track in a different sector faults before any send, even with
null velocity; no per-peer frame reset is implemented. Macro equality does not
establish cross-process coordinate-frame identity.

Updates must increase sequence and source time. Per-index sends are rate limited
by source process monotonic time, configurable from 1/240 second to 10 seconds;
rate rejection does not transmit or alter a sample. Invalid, stale, unknown,
closed or inconsistent frames fault the motion and shared delivery/host;
delivery, membership, receipt, socket-lease and consumer errors do the same.
A `motion_despawn` message carries only the version and identity fields and a
new sequence, bypasses the pose rate limit, and fences this lifetime. It is a
transport tombstone: no X4 removal is performed or inferred. This path does not
observe or automatically generate destruction events.

The caller may pass `recipients` to `send` as a nonempty list/tuple of exact
`{'id': ..., 'incarnation': ...}` pairs from the current admitted membership.
This is an explicit, per-sample selection; omitting it retains the original
all-admitted behavior and is not an interest decision. Duplicate, malformed,
foreign or stale-incarnation selections fault before any send. The full
admitted socket set remains fenced and quiet-checked while only the selected
peers receive the sample. Every selected peer must return its correlated
receipt; a partial success cannot be rolled back. Empty selection is refused.
This option does not alter the job/create delivery's all-participant ACK rule.

The source bridge can use an optional caller-supplied selector; neither module
computes sectors viewed in the map or manages subscriptions. First delivery
may begin at a later increasing sequence, but the owner must establish each
client's local actor binding. Leaving interest sends no removal, hiding or
expiry command; an old held sample can remain indefinitely. On re-entry an
older client frame may differ from the sender's current frame even if the last
two source samples match. The sender fences this per peer incarnation and
track, and the current local X4 binding also faults sector changes;
there is no general unsubscribe/reset/rejoin or cross-frame reconciliation.
Callers must fence or separately resolve these cases and cannot infer a safe
rejoin from a successful targeted send. No choice of recipients proves shared
checkpoint identity, actor/frame equality or interest correctness.

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
