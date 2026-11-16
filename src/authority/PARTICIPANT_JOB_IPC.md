# Experimental participant job IPC

`ExperimentalParticipantJobIPC` connects the existing admitted TCP participant's
`apply_job` callback to one local X4 update owner through UDP. It installs no X4
extension and does not start, authenticate or manage a game process. The owner
must bind an exclusive IPv4 loopback UDP socket before starting X4, provision
fresh independent 128-bit lease and attempt values and configure the same world
epoch and queue generation at both ends. A newly started X4 owner sends one
`READY` after its own initialization and running-state checks. `wait_ready()`
accepts this only from loopback and only after the supplied `validate_peer`
checks that the UDP endpoint belongs to the intended live X4 process. It pins
that address with UDP `connect` and rechecks the peer and the supplied process,
profile and session `guard` throughout each operation. Token/digest echoes are
correlation aids, not authentication against another local user/process. The
supervisor must actually implement these guards; a callback returning true
without checks is not evidence of process ownership. Raw duplicated socket file
descriptors and external readers remain outside the module's control.

Use the ready bridge as `apply_job=bridge` in
`ExperimentalTCPParticipantClient`. Each application sends one ASCII datagram
with a fresh request identity, event lineage, index, digest and descriptor. The
only accepted response repeats the identity and digest and reports `APPLIED`.
The Lua owner is responsible for resolving a validated local baseline witness,
calling the separately correlated MD receiver, and returning `APPLIED` only
after its running FFI readback completes and the MD callback returns. The digest
is an opaque echo in Lua; it is not an independent recomputation. Actor IDs do
not cross this IPC boundary. The seed/loadout is explicitly test-only, so this
is not a complete ship replica.

Both sides fail permanently on stale/foreign packets, process-guard failure,
timeout, or uncertain result. There are no retries: X4 may have created a ship
before a response is lost, and neither UDP nor TCP timeout can undo it. The
supervisor must fence and reconcile the X4 process and session before restarting.
The synchronous callback blocks the TCP client's sole reader; its IPC deadline
must be strictly shorter than the remaining TCP delivery deadline, with time
reserved for processing. Guard/validator callbacks must be bounded: they cannot
be interrupted. A late reply, a disconnect during local application or an X4
failure after partial effects cannot be rolled back.

Focused tests use real loopback TCP and UDP sockets. One connects the actual
TCP participant, Python bridge, native UDP library, Lua owner and Lua
multi-create client; its MD responses and FFI inspector are simulated and the
inspect response deliberately delayed. Another uses a simulated X4 owner to
check two consecutive events and exercises mismatched responses, peer
validation and timeout. The tests do not start X4 or prove native execution,
Windows, Internet, complete world synchronization or gameplay. This is an
internal experiment only.
