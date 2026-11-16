# Experimental admitted TCP job delivery

This opt-in adapter exchanges one bounded NPC descriptor with the actual sockets
already admitted to `ExperimentalLocalHost`. It supplies no X4 adapter, listener,
authentication, encryption or recovery. The existing host and client are
loopback-restricted, and the client application callback is a trusted assertion,
not proof of a native replica or a Windows/Internet connection. The caller owns
all components on the existing owner thread and must fence the source, gate,
connections and local clients on an indeterminate operation.

The source queue/gate owner passes `delivery.membership()` to the Lua gate as
its membership callback and `delivery.enqueue(peer,event)` as its send callback.
Enqueue only stores one event in a bounded local queue. Once `gate:begin` has
returned and every participant has been queued, the owner invokes
`delivery.flush(on_ack)` outside the gate callback. `on_ack(peer,event)` must
feed the exact pair and event back into that gate, returning true only if the
gate accepted it. This avoids a synchronous ACK re-entering the gate's dispatch.
The gate's own release callback and subsequent source `Acked` receipt must still
be wired by the source owner. Neither is implemented by this transport.

The adapter snapshots the fully admitted, running set; handles come from the
actual tracked sockets and each session handle gets a random incarnation. It
exchanges each request serially under the host's exclusive busy guard, blocking
that host's network pump for at most the configured timeout plus uninterruptible
caller callbacks. A socket-reader lease blocks control polling, admission,
participant control and closing while the exchange is active; only one delivery
owner can bind to that control instance. External code retaining raw socket
references must not read or duplicate them. It fails closed on socket errors, an unexpected or pipelined
frame, membership change, callback error or timeout. Only a fully validated
receipt invokes `on_ack`; previously applied client changes cannot be rolled
back. The caller must not replace a failed instance or retry an uncertain source
release without separately reconciling source and clients. New connections must
be admitted through the existing load protocol before forming a later complete
membership; an in-flight membership change is not recovered.

The deadline is checked immediately before and after each receipt callback, but
cannot interrupt a callback. A callback may trigger the gate's source release
and then return after the deadline; the transport faults but cannot undo that
release. The owner must give the gate a deadline on the same clock no later than
the transport deadline, keep callbacks bounded, and fence/reconcile the source
and all participants after such an uncertainty.

A client opts into job commands by passing `apply_job(event)` to the existing
`ExperimentalTCPParticipantClient`, the sole reader of its admitted socket. It
must return exactly true only after its own application is confirmed. Commands
carry session handle/epoch, connection incarnation, registry epoch, queue
generation, event sequence/index and the descriptor. The client responds with
those connection fields and a SHA-256 of the canonical event; the source checks
all response fields. The digest binds the exact descriptor for this exchange but
does not authenticate a sender. A fresh queue generation is required after a
source queue reset, and this adapter accepts consecutive event sequences only.

The focused tests use two real admitted loopback TCP connections, the existing
participant client, a real Lua delivery gate and synthetic application/source
callbacks. They do not test X4, a Lua/Python live bridge, replication correctness,
WAN, Windows, combat, trade or multiplayer gameplay.
