# Experimental multi-client job delivery gate

`lua/job_delivery.lua` is a default-off, in-memory offline building block. It
starts no game, registers no handlers and provides no transport or persistence.
It does not establish that an activation is a birth, that a replica is correct,
or that all creations in X4 are observed. It has not been used in a native run.

`new` requires `enabled=true`, a monotonic `clock`, a timeout in (0, 300]
seconds, a `generation` token and `membership`, `send` and `release` callbacks.
The supervisor must create a fresh unpredictable 32-character lowercase hex
generation for each source-queue incarnation, bind it to that queue and fence
all old gates and callbacks before replacing the source. The gate checks the
token's form and freezes its value; it cannot prove freshness or fence an old
gate on behalf of the supervisor. It permits exactly one active event and
1–16 participant connections. `membership()` must return the
complete current admitted set as a dense array of `{id, incarnation}` pairs.
The transport owner supplies identities from its actual connection, never from
a client assertion. Each incarnation is a fresh 32-character lowercase hex
connection token; IDs are bounded ASCII names. The owner must serialize all
operations, fence transport and source on failures, and call `tick()` while
waiting. The sampled membership checks do not prove atomicity with a send,
acknowledgment, disconnect or source mutation. Empty/uncertain membership,
any membership or incarnation change, timeout, ambiguous send, unexpected
callback/reentrancy or invalid input permanently fences this gate. Rejoin and
recovery are deliberately unspecified.

Call `begin` with `{epoch, generation, sequence, index, descriptor}`, where descriptor
has exactly `{macro, faction, sector_macro, x, y, z}`. Epoch is 32 lowercase
hex characters and generation must equal the gate's token; sequence and index are positive exactly representable Lua
integers; identifiers are bounded ASCII and coordinates finite. This explicit
allowlist excludes actor handles and arbitrary extra fields. The owner must
independently construct and verify the descriptor for the specific held source
event; exact value comparison here cannot prove its provenance, complete ship
state, coordinate frame or actual client-side creation. Subsequent events on the
same gate must use the same epoch and the next sequence; the first sequence is
caller-provided. The gate freezes copies and sends copies. `send(peer,event)`
must return exactly true when its own bounded dispatch is accepted; this is not
a delivery acknowledgment. Synchronous/reentrant acknowledgments are refused.

After the transport and client have independently validated successful
application, the owner calls `ack(actual_peer, event)` using the actual
connection binding and the complete original event. Every field and connection
incarnation and generation must match. A buffered ACK from an earlier queue
generation cannot match the new event if the supervisor supplies a fresh token.
Duplicate exact ACKs during the active event are
idempotent and do not add a participant; changed or stale ACKs fence. When all
participants have ACKed and membership still matches, the gate invokes
`release(epoch,sequence,index)` exactly once. For the experimental deferred
source driver this callback may call `host:confirm_delivery(epoch,sequence,
index)`; successful dispatch is not the subsequent MD `Acked` receipt.

After `release`, the gate remains closed to another event until the host's
correlated actual MD `Acked` callback calls `source_acked(epoch,sequence,index)`.
A source-ACK failure or membership change must fence both components. If the
source already removed the queue item before a subsequent failure, this gate
cannot roll it back or establish recoverability. The owner must not interpret a
failed release or lost callback as proof that the item remained in the queue.

`tests/authority_job_delivery.lua` and its Python wrapper exercise three
simulated participants, out-of-order and duplicate ACKs, changed event and
connection identities, stale queue-generation ACKs after restart, membership changes, timeouts, callback failures and
source-ACK correlation. They run no real network, MD, X4, save, Windows client
or Internet test and prove no transport authenticity or live multiplayer.
