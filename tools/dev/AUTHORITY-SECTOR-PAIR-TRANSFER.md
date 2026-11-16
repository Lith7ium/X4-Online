# Experimental two-X4 sector transfer

This opt-in harness is a development experiment, not multiplayer. It stages
separate disposable read-only copies of the pinned two-sector checkpoint,
starts two owned Linux X4 processes, and requires their markers, pause, saved
registry baseline 2 and local FFI readiness before sending either START. Its
private readiness overlay requires the receiver to be fresh and fixture sector
1 to differ from the local player sector. The private receiver checks that
sector relationship again before creating index 3. Both local owners remain on
the existing update handler. The original registry scripts remain unchanged.

The source makes one bounded synthetic ship and replays its request, inspects
both results locally, and emits its FFI position and portable descriptor. A
pidfd-owned, exec-gated helper sends that descriptor once through real IPv4
loopback TCP. The client may ACK only after its own Create, replay, MD/FFI
inspection and subsequent guard checks. Only then is ACK sent to the source.
Actor and sector handles stay local. UDP is private localhost process IPC, not
an Internet multiplayer protocol. A mutating request or uncertain send is
never retried. Per-role leases and correlation fields are experimental local
fences, not security or Internet authentication.

Each release is preceded by correlated CHECK/CHECKED replies from both guarded
X4 update loops and process, marker/log, profile and deadline checks. These
are observations, not continuous or atomic pause/process proof. The guard and
local inspect cannot preempt a stalled native callback. During cleanup, the
helper must be stopped and reaped before either X4 process or its lock is
released; if this is not confirmed, the processes and lock are retained and
the result explicitly reports unknown remaining processes. Success is
published only after owned X4 cleanup, final log continuity/receipt checks,
protected input checks, archive check and an empty final UDP queue. Late or
unexpected evidence fails the run. A callback or Create interrupted at an
uncertain point requires discarding the entire disposable experiment.

The native UDP module is built before starting X4 in a bounded compiler
process group. If the group kill or leader reap cannot be confirmed, the
result reports `CompilerCleanupUnconfirmed`; compiler descendants may still
exist, no X4 is started, and the tool does not claim that cleanup succeeded.

Offline tests use fake X4 processes, actual localhost UDP/TCP, and a real gated
helper. The bounded native attempt is documented below. No Windows, public network,
independent-player, simulation-ownership, whole-world, combat, trading,
persistence or playable multiplayer claim follows from this test. The chosen
sector frame, actor/sector identity and FFI positions remain limited to the
saved two-sector fixture. The test seed is a Create input, not an independently
read seed. The candidate-count check is not proof of global ship coverage or
collision-free placement.

The guarded integration received independent review before the bounded native
run below. Failing or missing evidence must abort; do not convert a failed test
into a retry against a possibly mutated profile.

## Bounded native Linux/Linux attempt

The disposable `.local/authority-sector-pair-transfer-01` run reports
`success: true`, a TCP ACK after client inspection, local replay checks, and
confirmed owned cleanup with no remaining owned processes. The result is the
harness's report: the TCP bytes, helper exit and intermediate Create/Inspect
events are not separately recorded in a durable packet trace. The source X4
log records `READY`, `DESCRIPTOR`, then `FINISHED`; the client log records
`READY`, `AWAIT`, then `INSPECTED`, with repeated guarded `CHECKED` receipts.
Both logs first record their load request, marker inspection, slot-2 read,
pause receipt and local pair readiness. The logs alone do not establish a
cross-process ordering; that follows from the reviewed coordinator and its
reported successful completion.

The source, client and pinned archived staged-save files have SHA-256
`2c6494308424fffe8bd114bd017802e2b6dc1f227a64998aea8a787672846748`.
Each private overlay's Create driver, FFI adapter, UDP owner, session,
inspector and engine match their reviewed source or expected module-export
transformation; the receiver and readiness scripts match their intended
private guard transformations, and the saved-state scripts match the archive.
The observed sector fixture is `cluster_33_sector001_macro`, remote from each
local player by the readiness/inspection guards. The experiment requests one
artificial index-3 ship per process, repeats the request locally, and checks
the same local actor, sector, candidate count and position within two metres
per axis before completion. The source request uses seed 7183; this is a
synthetic input, not a seed readback. The logs do not record the actual
transferred coordinates or expose the locally compared actor IDs.

This is one paused Linux localhost fixture, not a Windows or Internet test,
independent-sector player session, full ship-state replication, resumed NPC
simulation, combat, trade, boarding or gameplay. The common save hash does not
prove which bytes X4 actually consumed, and sampled pause/process checks do not
prove uninterrupted pause. No checkpoint was requested by this run.
