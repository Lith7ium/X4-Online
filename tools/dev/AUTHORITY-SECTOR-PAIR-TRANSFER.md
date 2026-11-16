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
helper. They do not establish any native X4 result. No Windows, public network,
independent-player, simulation-ownership, whole-world, combat, trading,
persistence or playable multiplayer claim follows from this test. The chosen
sector frame, actor/sector identity and FFI positions remain limited to the
saved two-sector fixture. The test seed is a Create input, not an independently
read seed. The candidate-count check is not proof of global ship coverage or
collision-free placement.

This harness must receive independent review and its guarded integration must
be complete before any native run. Failing or missing evidence must abort; do
not convert a failed test into a retry against a possibly mutated profile.
