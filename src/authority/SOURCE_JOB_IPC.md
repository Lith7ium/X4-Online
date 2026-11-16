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
