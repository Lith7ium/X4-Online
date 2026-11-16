# Opt-in census replica UDP wrapper

`authority_census_replica_udp.lua` is a client-only experimental adapter. It
changes neither the existing Census owner nor the source process. It installs no
update handler and opens no socket on import. `new_x4(c)` explicitly wraps the
existing Census X4 adapter and its single connected nonblocking UDP socket; the
same sole X4 update owner must continue calling `tick`. The surrounding harness
still owns both processes, protected profiles, registry baseline, lease/peer,
paused state, queue, TCP, helper and cleanup fences.

After the existing client locally validates its witness, the wrapper intercepts
the original WITNESS_OK and its value-free log and forwards WITNESS_READY
instead. It preserves the local validated witness (epoch, index and macro) for
one subsequent command:

```
CENSUS|lease|client|attempt|epoch|WITNESS_READY|jobseq|saved_index|sector_macro
CMD|lease|client|attempt|epoch|REPLICA|jobseq|10055|macro|faction|sector_macro|x|y|z
```

The caller must send this one REPLICA only after receiving the actual validated
source descriptor over the separate TCP test connection and checking that the
sequence and sector match the accepted saved witness. The wrapper rejects wrong
attempt, epoch, role, sequence, index, sector, nonfinite/out-of-range position,
invalid names, duplicates and unexpected states. There is no automatic retry.
Actor/sector runtime handles never appear in UDP messages.

The replica owner initializes its local registry extension, performs Create,
MD/FFI Inspect, identical Replay and second Inspect, then reports a local intent
after a further guarded tick. Only after another successful wrapper/base/replica
guard tick does the wrapper log `AUTH_CENSUS_REPLICA DONE`, send the original
correlated `CENSUS|...|WITNESS_OK|jobseq|saved_index|sector_macro`, and log
`AUTH_CENSUS_JOB WITNESS_OK`. On error it emits/logs FAULT best effort; a sent
UDP datagram followed by a failed guard remains an indeterminate outcome. The
wrapper does not send a TCP ACK. The harness must independently validate both
processes, pause/witness, source queue, helper and TCP state after WITNESS_OK and
before allowing that ACK. Pause and process guards remain point observations,
not atomic or continuous guarantees. Late callbacks and duplicate commands
fault; packet loss requires timeout and discarding the private experiment.

Explicit `new_x4(c)` expects the Census X4 config plus `base_adapter` (the
original Census X4 module), `base_owner` (its underlying owner module),
`replica_adapter` and `replica_driver` (the separate replica client modules).
It is client-only. Existing Census READY, CHECK and FAULT framing remains in
place; WITNESS_READY is an intermediate notification, never completion. A fresh
attempt must be consumed once by the supervising harness across sockets.

Offline tests exercise fake state machines, actual native UDP on loopback, and
the full Lua owner/adapter chain against a fake X4 FFI library:

```
python3 -m unittest discover -s tests -p test_authority_census_replica_udp.py -v
```

They do not execute X4, prove frame identity, collision freedom, complete ship
state, Windows operation or multiplayer gameplay.
