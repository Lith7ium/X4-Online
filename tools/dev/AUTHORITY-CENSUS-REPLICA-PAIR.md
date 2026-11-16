# Private census descriptor to approximate client replica

This default-off Linux diagnostic builds upon `authority_census_pair_live.py`.
It is an internal two-process experiment, not multiplayer. It requires a fresh
output directory, two owned disposable X4 profiles, the pinned census save and
witness artifact, and installs the extra replica scripts only in the client.
The original archived registry and identity fixture remain byte-identical. The
source-only job observer, source queue handling, marker/load/pause gates,
protected-file and source checks, exec-gated/pidfd-owned TCP helper, signal
fence, lock retention on uncertain cleanup and final logs are inherited from
the original pair diagnostic. No game save is requested. During the bounded
source observation the source simulation runs in memory; the client remains
paused. File, process and pause checks are sampled, not atomic or continuous.

After both saved 10054-entry registries are ready, the source observes a new
index 10055 and captures a descriptor. Source and client each validate a local
saved-sector witness. The actual descriptor travels through one TCP loopback
connection with a distinct transport sequence and actual job sequence. Within
its receiving callback the coordinator waits for `WITNESS_READY`, sends exactly
one `REPLICA` command, and waits for the correlated completion after the client
has initialized its separate receiver, created the ship, inspected it with MD
and local FFI, replayed the identical Create, and inspected it again. A further
successful local update and both-owner process/pause guard precede the TCP ACK.
The final logs and late UDP queue are checked after stopping the owned X4
processes. No local actor or sector handle enters the TCP or UDP envelope.

The receiver uses the actual descriptor's macro, faction, sector and bounded
sector-space position. Seed **7183** is a deliberately artificial local test
parameter, not a source attribute; loadout is also approximate. The client
checks a faction/macro candidate count before and after, but that count's
coverage is limited and it does not prove the absence of autonomous or other
similar ships. The witness maps the target to a local sector but does not prove
identical coordinate frames, collision clearance or global sector identity.
This test has no adoption or removal policy, and does not reconstruct the
source ship's pilot, orders, AI, velocity, orientation, health or cargo.

Any failed or ambiguous dispatch permanently discards that private case. The
result's `ship_creation_requested` is set once even the one replica UDP send
is attempted; on failure it does not imply that the MD Create was actually
received or completed. The result remains unsuccessful if the client receipt,
FFI checks, ACK, final logs, source integrity or cleanup is unconfirmed. If the
bounded source window produces no new index, a validated final `NO_EVENT` is
`inconclusive_no_new_registry_entry`, never success. The experiment has not
established persistent-world behavior, NPC synchronization, Windows or
Internet connectivity, or gameplay. A successful native run would still only
show a single approximate counterpart in this particular Linux fixture.

Offline tests use fake X4/process owners and real local UDP/TCP and a gated
helper. They do not prove native MD/FFI semantics or actual multiplayer. Normal
profiles and saves must never be used. Before a native run independently review
the complete overlay, UDP/ACK order, process and cleanup fences; no existing
successful test results should be overwritten.

## Recorded native run

`.local/authority-census-replica-01` completed successfully in two isolated
Linux X4 processes. Both logs contain the requested `save_009` load, the same
saved marker, a pause observation and `READY`. The source log then reports
`DESCRIPTOR` and `WITNESS_OK`; the client log reports `WITNESS_READY`,
`REPLICA DONE`, and `WITNESS_OK` in that order. These log labels do not contain
the descriptor or an independent packet trace. The coordinator result reports
one job activation allocated index 10055, sequence 1, the saved witness at
index 1318, and TCP ACK after the guarded replica callback. The inspected code
requires the source and client local witness checks and the client's
Create/Inspect/Replay/Inspect and local FFI checks before that ACK. Thus the
cross-process order and descriptor values are coordinator/result evidence,
corroborated by the separate process logs; they are not a packet capture.

The reported descriptor was `ship_gen_m_tugboat_01_a_macro`, faction
`pioneers`, sector `cluster_115_sector001_macro`, at approximately
`(-132217.1875, 6004.3818359375, 169081.203125)` in the sampled local sector
frame. Seed 7183 and the loadout were artificial. A new registry entry following
job activation does not establish that the original ship was newly built.

The pinned source save and both staged saves independently hash to
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
the witness JSON hashes to
`006b07a39be4cff6a3fac7555b26d40ffe834594304c231dd659b23bfdc85349`.
The client replica scripts in the saved overlay match the reviewed inputs and
the installer's expected module export transformation. The runner reports
confirmed owned cleanup and no remaining owned processes. Its sampled
protection checks do not independently prove which exact bytes X4 consumed or
continuous pause, nor do they establish shared coordinate frames, full state
replication, Windows/Internet behavior or gameplay.

## Deferred source queue experiment

The pinned census checkpoint predates correlated registry responses. Its
private overlays therefore use the save-era byte-identical registry script in
`tools/dev/fixtures/census-20261115/authority_ship_registry.xml`, while the
current correlated registry script remains separate. Provenance still compares
the archived saved-state scripts and the staged overlays byte for byte; this
fixture does not change the archived save or bypass those checks.

The separate `--defer-source-ack` opt-in prepares an additional experimental
source path. It holds one source queue head while the existing client replica
and TCP exchange run, then sends a source release only after the exchange and
another context guard succeed. The experiment reports success only after the
source reports its matching MD `Acked` event. The fresh run attempt is also the
queue generation; the private UDP envelope binds attempt, epoch, role and lease,
and the release and receipt carry the sequence and index. The supervisor is the
one simulated delivery participant, not a real Windows player.

The TCP ACK contains the attempt, epoch and sequence/index identities, not a
descriptor hash. Its association with the descriptor relies on the fresh
attempt, a single validated descriptor/exchange and exact received-descriptor
comparison. An uncertain release is not retried; a missing source receipt does
not establish whether MD removed the item. Synthetic fake-owner tests exercise
success, missing/foreign/premature source receipts and uncertain TCP outcomes.
The earlier recorded run above used the non-deferred path. The deferred path's
bounded native observation is recorded below; it is not proof of gameplay,
complete replica state or general creation coverage.

While the source waits, the owner requires its isolated profile, confirmed
pause and unchanged sampled game time; the host is ticked with a dedicated
bounded pause guard. These observations are not an atomic or continuous pause
guarantee. Known or previously unobserved existing registry entries cause the
deferred case to fail instead of being silently acknowledged. A source ACK
already dispatched before a later guard or communication failure cannot be
rolled back. The offline tests use fake MD and client communication.

### Native deferred observation

`.local/authority-census-deferred-01` refused before launching X4 because the
current registry script differed byte-for-byte from the saved checkpoint's
script. The save-era fixture described above restores the exact comparison;
the original failure record remains unchanged.

`.local/authority-census-deferred-02` reports success for one activation and
one approximate replica in two isolated Linux X4 processes. The server engine
log records `READY`, `DESCRIPTOR`, `WITNESS_OK`, then `SOURCE_ACKED`; the client
engine log records `READY`, `WITNESS_READY`, `REPLICA DONE`, then `WITNESS_OK`.
The coordinator result reports index 10055, job sequence 1, the TCP ACK after
the replica callback, and `source_queue_acked=true`. The code accepts the latter
only after the matching MD `Acked` event. There is no independent TCP packet
trace: the ordering across processes and descriptor values are coordinator
evidence corroborated by the separate X4 log labels.

The reported descriptor was `ship_gen_m_tugboat_01_a_macro`, faction
`pioneers`, sector `cluster_115_sector001_macro`, position approximately
`(-132217.234375, 6004.3818359375, 169081.375)` and witness index 1318. The
replica uses artificial seed 7183 and an approximate loadout. An allocated
registry entry after an activation does not establish a ship's birth. The TCP
receiver is the local supervisor's callback; this was not a second independent
network participant. The result reports no requested checkpoint, confirmed
owned cleanup and no remaining owned processes. Its sampled guards do not prove
continuous pause, exact X4 file consumption or a shared coordinate frame.
There was no multi-client, Windows, Internet, combat, trading or gameplay test.
