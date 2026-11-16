# Experimental source job IPC bridge

`experimental_source_job_bridge.py` and `lua/source_job_ipc.lua` are a
default-off integration seam between a held source job and admitted TCP clients.
Neither installs an extension, starts a listener or X4, owns a game process or
supplies an X4 client application. No native X4, Windows, Internet or gameplay
has been tested with this seam. Source and TCP callbacks are injected and their
observations are assertions by the owner, not independent process proofs.

The owner must serialize the Python host, control channel and source UDP socket
on one thread, keep a separate exclusively owned UI update handler for X4, and
supply a connected IPv4 loopback UDP socket pinned to the intended source. Its
fresh lease, attempt, registry epoch and queue generation are distinct 32-hex
values, independently generated and bound by the supervisor. The socket-object
binding prevents two bridges sharing the same Python socket object; duplicated
file descriptors, raw socket reads, same-user interference and actual X4 PID
binding remain the supervisor's responsibility. This is not transport security.

The source creates the Lua IPC adapter with a real `job_delivery` gate, guard,
clock, send callback and `release(epoch,sequence,index)` callback that delegates
only to the held job host's `confirm_delivery`. The caller passes the validated
actor-free event to `candidate`; the IPC adapter freezes it before any callback.
Its ASCII local protocol uses `S|lease|attempt|CANDIDATE|epoch|generation|seq|
index|macro|faction|sector|x|y|z`. Python obtains actual admitted TCP connection
handles and incarnations, checks socket liveness, and sends `BIND` with that
identity and the complete frozen membership. Lua begins the actual gate and
returns `READY` only after successful gate dispatch. The injected send callback
there confirms local queueing, not network delivery.

Python synchronously sends the descriptor over each actual admitted TCP socket.
It collects and correlates the validated client receipts without calling the
source during `deliver`, avoiding TCP-owner reentrancy. Only after all receipts,
release of the TCP reader lease, and a membership/liveness check does Python
forward per-peer `RECEIPT` messages to the source. Lua gate accepts the ordered
membership and responds `PARTIAL` for intermediate receipts. The last receipt
may dispatch the source host's local Ack. The source caller must call
`source_acked` only after the separately correlated actual MD `Acked`; only then
does Lua send `SOURCE_ACKED`. TCP client `apply_job`
is still an injected synchronous assertion, not actual X4 client creation.

After `SOURCE_ACKED`, Lua remains in `await_rearm`. Python first verifies that
no unexpected source datagram is queued, then sends `REARM`; Lua responds
`REARMED` before accepting a new candidate. A new candidate may arrive
immediately after `REARMED` and is retained in the UDP socket for the next
`run_one`. The source owner must not poll/consume the next queue head before
rearm; an early `candidate` faults rather than dropping that event. This pacing
does not remove the underlying finite queue limit: an overflow still faults and
requires the supervisor to fence the case, not silently discard events.

All operations have bounded deadlines and strict sequencing. A failed source
packet, unexpected queued UDP datagram, lost client, changed membership, uncertain
send or missing source acknowledgment fences the bridge and host. Python checks
for queued unexpected source packets before and after forwarding receipts;
these are sampled checks, not atomic against subsequent packets or disconnects.
Guard callbacks execute under host busy and control reader leases so they cannot
consume participant sockets or run host ticks. The synchronous TCP callback and
other caller-provided callbacks must be independently bounded: the adapter checks
the deadline before and after but cannot interrupt a blocked callback.

`host._failed=True` is only a software state flag. It does not stop X4, fence a
remote client, retain a profile/process lock or undo a source Ack already
submitted. The real supervisor must stop/fence every affected owned process and
client and retain its lock until cleanup is confirmed; no recovery/rejoin policy
is implied. A failed result cannot establish whether an already dispatched MD
Ack removed the source event. No source Actor or local X4 handle is sent.

`tests/test_authority_experimental_source_job_bridge.py` uses a fake X4 source,
the actual Lua IPC and delivery gate, real localhost UDP and two admitted TCP
client sockets with fake client apply functions. It covers ordered success,
client failure, stale generation, mutation, duplicate messages, socket reuse,
reentrant guards and missing source receipt. It does not exercise an X4 MD
callback or actual gameplay.

## Opt-in source peer binding preparation

`experimental_source_job_binding.py` prepares one already-bound loopback UDP
socket for handoff to `ExperimentalSourceJobBridge`. A paused source owner must
send one `S|lease|attempt|HELLO|epoch|generation`; the binder checks exact
context and invokes its caller-supplied peer validator. Only then does it
connect the socket and send `P|lease|attempt|BOUND|epoch|generation`. It waits
for the exact `S|lease|attempt|ATTACHED|epoch|generation`, checks peer ownership
again, and permits a single socket handoff. The supervisor must keep the source
paused until the handoff and separately controlled resume; those pre-bridge
messages must not be passed to the source IPC packet handler. Lost, duplicated,
foreign or uncertain packets, a failed validator or timeout fence the binding;
there is no retry. A callback or raw descriptor retained by outside code can
still interfere, and the sampled checks are not atomic.

The binder's `validate_peer(peer)` is an injected assertion, not a PID/inode
inspection by this component. A real supervisor must independently verify that
the UDP flow belongs to the owned X4 process and stable start identity, and
maintain the process, profile, pause and cleanup guards. Local tokens are not
authentication against another process of the same user. Successful binding is
not evidence of a job event, source acknowledgment, NPC birth, client delivery,
Windows or Internet operation. `tests/test_authority_experimental_source_job_binding.py`
uses local UDP and a simulated source; it does not start X4.

For a Linux diagnostic, `tools/dev/authority_source_job_bind.py` supplies the
concrete peer validator using the existing `/proc` UDP-flow/socket-inode and
PID/start-time/executable-identity checks. The supervisor supplies the process
identity it has independently associated with its owned X4 and the external
pause/lifetime guard. `tests/test_authority_source_job_bind.py` exercises that
path against sockets in the test process, including a changed start identity;
it does not establish X4 ownership or continuous process liveness.
The handoff returns only the connected socket; it does not install the peer
validator in `ExperimentalSourceJobBridge`. The supervisor must keep the same
captured peer/process identity and recheck the UDP flow and socket inode in
the bridge's guard throughout use. After its deliberate resume, that guard
must check the expected running context rather than continue requiring pause.
The existing binding tests cover sampled handshake checks, not later bridge
lifetime checks.

After socket handoff, the Linux helper `authorize_source` sends one
`P|lease|attempt|GO|epoch|generation` and waits for the matching
`S|lease|attempt|GO_READY|epoch|generation` while repeatedly checking the
owned process and UDP flow. Only after that confirmation may the supervisor
request resume. Neither helper resumes X4 or decides when admitted clients are
ready. A changed peer, process, guard, timeout or unexpected datagram closes the
socket and requires external fencing. The supervisor must then pass the same
connected socket to the source bridge and keep checking its process/peer guard.

Binding, GO authorization and `ExperimentalSourceJobBridge` reserve the same
Python socket object exclusively in turn. Reentrant GO or a second GO for that
socket is refused; a reentrant attempt during GO also fences that attempt.
Reservations do not detect duplicated file descriptors or direct raw socket
reads retained outside these components. The supervisor must prohibit both.

The Python bridge can optionally accept the source owner's correlated
`FINISHED` after the host samples an empty queue following the observation
window: call `run_one(allow_finished=True)`
and a `None` result means the reported count equals the number of this bridge's
completed ACK/REARM cycles. The bridge then enters `finished` and cannot read
another event. It samples TCP quietness, a nonempty admitted set, continuity
with the last event's membership, and source-socket quietness before accepting
the completion. The producer can add events during or after that sample; it is
not a lossless drain or a session-shutdown proof. These are point-in-time checks,
not proof of future liveness;
count zero does not establish complete world coverage. Without explicit opt-in,
`FINISHED` is a protocol failure. Source owner and bridge continuous operation
remain offline-tested; no native continuous-run result is asserted.

For an externally supervised continuous session, `run_one(allow_finished=True,
wait_without_deadline=True)` permits an idle interval without a bridge-wide
deadline. The supervisor guard is still sampled throughout that wait. On the
first received datagram, the normal bounded operation deadline starts afresh;
this option does not permit a stalled delivery or source ACK. The supervisor
must itself stop the session and fence processes and sockets when required.
