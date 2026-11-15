# Experimental TCP participant client

`ExperimentalTCPParticipantClient` is an opt-in, loopback-only, single-owner
adapter for the existing experimental host participant protocol. The caller
must already own a live TCP connection and consume/validate its load-accepted
frame without reading beyond its newline. The host can send the first command
immediately after that frame; this adapter cannot accept bytes already consumed
by another reader. The caller supplies the expected world epoch and session handle from
that current connection's offer, an already enrolled local controller, and
continues to pump `poll`. The adapter owns the socket until closed; it must not
share reads, writes or control state with a second owner.

The injected controller must implement `pause((handle,))` and
`resume((handle,))` and return exactly `True` only after confirming that local
operation. A correctly enrolled `LocalParticipantControl` offers this shape,
but this composition has not been run against X4. Reentrant calls fail the
adapter. Commands must match the connection's epoch and handle and have a
strictly increasing request ID; stale, duplicate, malformed and pipelined
commands fault the connection. A receipt is emitted only after controller
confirmation and point-in-time socket/deadline checks. The ID is consumed before
the controller runs, so an uncertain operation is never retried by this object.

The controller call is synchronous and must enforce its own bounded timeout;
this adapter cannot interrupt it. The adapter's absolute deadline starts when
the first command bytes are read and is rechecked after the call and through
receipt output. It cannot know the host's separate deadline; the host may
already have faulted while the client operation was in progress. On timeout,
disconnect or uncertain controller result, fence or settle the local X4
process and discard this session; never reconstruct this adapter on the same
connection to bypass its request history. A socket send does not prove the host
received the receipt, and no point-in-time liveness check prevents later EOF.

Tests use real loopback TCP sockets with fake controllers, including a paired
exchange with the experimental host adapter. There is no actual X4 process,
Windows execution, Internet listener, peer authentication, load operation or
gameplay in these tests. Loopback and the synchronous exchange are experimental
limits, not final architecture decisions.
