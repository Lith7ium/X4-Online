# Experimental two-client census delivery

`authority_census_replica_live.py --defer-source-ack --two-clients` is a
separate opt-in three-process Linux/loopback diagnostic. It is not a playable
server. One bounded native observation is recorded below. The unchanged default is one client.
The same pinned historical save is staged into three distinct disposable
profiles using one source read; each staged inode and digest is verified.
Before preparation and each process launch, a point-in-time gate requires
available RAM (including any visible cgroup limits) of at least 4 GiB plus
2 GiB for each X4 process still to launch, and at least 2 GiB free disk.
These are conservative heuristics, not measured X4 peak requirements or a
guarantee against memory exhaustion. GPU/VRAM capacity is not measured.

The coordinator binds a separate private UDP socket and lease for each X4
owner, and assigns two distinct generated client incarnations. The existing
client owner receives the local role `client` for both copies; the coordinator
keeps their sockets, leases and Python-side roles distinct. Two separately
owned TCP helpers each transmit the descriptor to a supervisor callback. That
callback requests the corresponding paused X4 client to create and inspect its
replica over the separate private UDP control path before returning a TCP ACK.
Only after the first helper confirms its actual TCP ACK does the coordinator
notify the source, and it requires a correlated `PARTIAL_ACKED`; only after
another independent client replica and TCP ACK does it send the second
notification and require `SOURCE_ACKED`. Any missing, wrong or premature
receipt fences the case. A send or source ACK with an uncertain outcome is
not retried. Listener/helper cleanup must succeed before stopping owned X4
processes or releasing the lock; errors retain the lock.

This is still one descriptor and one bounded source event. Actor birth, global
coverage, authoritative world agreement, autonomous duplicate prevention,
complete ship state, shared sector frames, client disconnection/rejoin, real
Windows clients, Internet reachability and gameplay remain unproven. The TCP
ACK includes attempt/epoch/sequence/index, not a descriptor hash; the binding
uses a unique attempt, one validated descriptor, one separate socket exchange
per client, and the coordinator's exact receive comparison. Client incarnation
is bound by the private supervisor to its own UDP/TCP exchange, not by remote
client authentication. Distinct observed X4 PIDs and UDP endpoints are required;
the UDP endpoint is not independently bound to an X4 PID. All process, pause and file observations are sampled.
No original profile or save is used for mutation.

`tests/test_authority_census_replica_multi_coordinator.py` uses three fake UDP
owners with real private loopback TCP helpers. It covers the two ordered
successes, premature or wrong source receipts, a lost second TCP outcome and
missing final receipt. `tests/test_authority_census_pair_inputs.py` checks three
independent staged inodes, and the runner test uses fake processes. These are
not native X4 tests.

## Recorded native observation

`.local/authority-census-multi-01` reports success for one job activation and
two approximate replicas in three isolated Linux X4 processes. The source X4
engine log records `READY`, `DESCRIPTOR`, `WITNESS_OK`, `PARTIAL_ACKED` and
`SOURCE_ACKED` in that order. Each client X4 engine log records `READY`,
`WITNESS_READY`, `REPLICA DONE` and `WITNESS_OK` in that order.

The coordinator result reports job sequence 1, registry index 10055, witness
index 1318, both client confirmations, TCP acknowledgements after their
respective replica callbacks and a source queue acknowledgement. Ordering
between X4 processes and TCP is supported by the coordinator code and result,
corroborated by those log labels; there is no independent packet trace. The
TCP receivers are local supervisor callbacks, not X4 clients' own network
connections. Each client uses artificial seed 7183 and an approximate loadout.

The reported descriptor was `ship_gen_m_tugboat_01_a_macro`, faction
`pioneers`, sector `cluster_115_sector001_macro`, at approximately
`(-132217.25, 6004.3818359375, 169081.453125)`. Registry allocation following
activation does not prove that a ship was newly built. The result reports no
requested checkpoint, confirmed owned-process cleanup and no remaining owned
processes. Sampled guards do not prove uninterrupted pause, exact X4 file
consumption, common coordinate frames, full universe coverage, autonomous
deduplication or complete ship state. This was not a Windows, Internet or
gameplay test; combat, trading and boarding were not exercised.
