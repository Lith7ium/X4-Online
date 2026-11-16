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
