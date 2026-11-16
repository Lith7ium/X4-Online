# Private nonblocking pair-create UDP owner

`authority_sector_pair_create_udp.lua` is a default-off test adapter. Importing
it starts no X4, opens no socket and registers no event or update handler.
`new_x4` must be called explicitly after the local pair-readiness probe reports
success, in a disposable protected overlay; it opens one connected,
nonblocking `x4lan_net.so` socket to `127.0.0.1` and the specified local port.
The existing sole X4 update owner must call `tick` after continuing the
pair-readiness check. No TCP operation or socket wait belongs in this update.
The surrounding harness owns peer-address binding, unique per-role lease,
process identity, archive, file, pause, liveness and cleanup checks. A connected
UDP peer and lease are not an Internet authentication or security scheme.

Call `new_x4` with `enabled=true`, `role` (`server` or `client`), 32-character
lowercase hex `lease`, `attempt`, `epoch` and per-process `nonce`, sector macro
`sector`, positive local `timeout` in seconds, the UDP `port`, the private
`expected_save_path`, `driver` from `authority_sector_pair_create.lua`,
`adapter` from `authority_sector_pair_create_x4.lua`, and `pair_guard`. The driver timeout is the lesser of this timeout and 120 seconds. The
caller supplies a `pair_guard` that validates the same current local paused
pair-readiness state, including both sector references; it must be safe to call
multiple times per tick. Client and server use separate profile overlays, socket
objects, leases and local owners. Each has the same approved attempt, saved
registry epoch and sector macro. A fresh attempt must be consumed only once by
the supervising harness across all connections.

All messages are ASCII `|`-separated and at most 768 bytes, the existing native
module's datagram limit. X4 sends exactly one READY after guarded setup:

```
PAIR|lease|role|attempt|epoch|READY
CMD|lease|role|attempt|epoch|START
PAIR|lease|client|attempt|epoch|AWAIT
PAIR|lease|server|attempt|epoch|DESCRIPTOR|1|3|macro|sector|owner|seed|x|y|z
CMD|lease|client|attempt|epoch|DESCRIPTOR|1|3|macro|sector|owner|seed|x|y|z
PAIR|lease|client|attempt|epoch|INSPECTED|1|3
CMD|lease|server|attempt|epoch|ACK|1|3
PAIR|lease|server|attempt|epoch|FINISHED|1|3
```

`CHECK|counter` and `CHECKED|counter` use the same respective `CMD` and
`PAIR` prefixes. Counters must be positive, strictly increasing decimal values
at most 2147483647; one CHECK may be pending in a tick. CHECKED is sent only
after the same tick has completed pair guarding and, once started, guarded
owner update. START, DESCRIPTOR and ACK are consumed only in their expected
state. Duplicate, late, foreign, malformed or unexpected packets observed by
this owner fault it. UDP itself can lose packets, and the native receiver can
silently discard oversized datagrams or socket errors: a missing event must
therefore time out and fence the case, never trigger a mutation retry.

The descriptor comes from the Lua driver's real source-side FFI snapshot. The
client's INSPECTED means that its two local MD inspections, per-axis position
checks and local replay binding checks reached the callback and a later
owner/guard tick succeeded. No handle is transmitted. These outcomes are only
process-local assertions, not native evidence until an isolated X4 run.
`DESCRIPTOR` and `INSPECTED` are buffered as local intentions in the callback:
the adapter sends them only after the callback returns and the next successful
owner/guard tick. Sending an INSPECTED datagram is **not** the TCP ACK. The
supervisor may acknowledge only after validating that datagram, inspecting both
process/guard fences, and following the separate TCP receiver contract. ACK is
forwarded to the source only after TCP confirmation. Failed or ambiguous steps
must discard the disposable test case.

Ordered, value-free `AUTH_PAIR_CREATE` log markers record READY, AWAIT,
DESCRIPTOR, INSPECTED, FINISHED and CHECKED. A fault, including an unexpected
late event, logs `ERROR FAULT`; fault datagram delivery is best effort. The
owner continues guarded updates in the finished state until the surrounding
harness stops it. These guards are sampled, not continuous or atomic. Call
`close()` during fenced cleanup and ensure every helper is reaped before ending
owned X4 processes or releasing their lock. A process whose owned stop cannot be
confirmed must retain the lock.

Offline validation:

```
python3 -m unittest discover -s tests -p test_authority_sector_pair_create_udp.py -v
```

The tests use fake X4 owners and the actual native UDP module on local sockets;
they do not run X4 or prove native update/event behavior, complete coverage,
Windows, Internet access or multiplayer play.
