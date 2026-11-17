# Experimental client-authority motion pull

`ExperimentalTCPClientAuthorityMotion` is a default-off, read-only diagnostic
for one explicitly admitted TCP participant and one immutable test grant. The
grant contains the session epoch, registry epoch, generation, index, sector
macro, fresh token and actual participant incarnation. Caller-owned guards must
bind this assertion to the owned game process, the private checkpoint context
and the same test grant installed on that client. It is not a network authority
assignment or a security credential, and it proves no HA ownership or handover.
Use fresh generation/token and fence old processes and buffered messages.

One request at a time uses the existing participant connection and the same
exclusive control-reader lease as job/motion delivery. The participant adapter
requires its separate opt-in grant, guard and pull callback. The server sends a
strictly numbered request; a bounded response is either NO_SAMPLE or one
actor-free validated motion sample and digest. NO_SAMPLE does not advance the
sample sequence. Samples must start at sequence 1 and advance by one, use the
granted context and a fixed frame label, and carry strictly increasing source
game time; the first velocity is unknown. Invalid framing, duplicate keys,
foreign context, replay, guard failure, changed membership or timeout fences
the connection; the lifecycle supervisor must fence both game processes too.
The dynamic response validator runs while the existing socket-reader lease is
held. Callbacks are synchronous and their timeout checks are sampled: a stuck
callback itself cannot be preempted by this adapter.

The participant callback must bind its UDP peer to the owned client X4 PID,
start time and socket inode. `tools/dev/authority_client_authority_bind.py`
offers a separately enabled running-client HELLO/BOUND/ATTACHED binder with
explicit external running and test-grant guards. These are sampled assertions;
the old paused-source binder retains its separate contract. No GO or resume is
sent by this client binder. Its local X4 owner must only expose a staged sample
once its correlated reader event and follow-up guard have completed. The
participant-side callback is an assertion, not independently authenticated X4
execution. Source and server clocks are not equated; sector macro equality does
not prove cross-process frame equivalence. No job acknowledgement, server-X4
setter, interest assignment or persistent shared-world operation occurs here.
The coupled offline test additionally drives the real Lua authority session,
reader, bootstrap and sampler through native loopback UDP and a real local TCP
participant. Its `/proc` checks bind the spawned Lua test process, not X4; MD,
FFI-dependent game state, time and the authority grant are simulated. The outer
participant onUpdate and `new_x4()` wiring are not exercised. TCP admission is
a synthetic test fixture; its fresh test incarnation is bound once to the
admitted handle by the explicit opt-in binder. Neither actual assignment nor
handover is demonstrated. These tests do not
establish native X4, Internet, Windows or shared-world behavior.

## Ordered participant transitions

For explicitly selected participant owners, `suspend_client_authority()`
stops new pulls and checks the existing reader lease, admitted sockets and
queued input. The caller must separately drain the X4 source and any server
sink: this transport operation is not a freeze or pause acknowledgment.
An owner whose connection leaves during this suspension is revoked. After the
world is running and the new admitted set is complete,
`resume_client_authority()` checks socket and grant bindings under the same
reader lease. A surviving participant retains its original owner and sample
sequence; a new participant needs a new owner and grant. Unexpected departure
without suspension, or an uncertain exchange, fences the host.

When all authority participants have departed, `release_client_authority()`
can detach an idle delivery owner if it has no other delivery or motion work.
Retired grant tokens and incarnations remain rejected by a replacement delivery
for the lifetime of the same control object. They are not a persisted replay
ledger across process restarts. These methods do not synchronize an X4 pause,
apply poses, establish frame identity or implement general multiplayer.
