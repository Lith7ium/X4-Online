# Experimental motion local IPC bridges

These default-off bridges connect an already admitted TCP motion owner to
separate process-local X4 source and participant endpoints. No process,
listener, X4 hook, socket or profile is created by import. The outer supervisor
must own each X4 process and its profile lock, ensure the selected game state,
and fence all sides after an uncertain operation until cleanup is confirmed.

`ExperimentalSourceMotionIPC` receives one connected loopback UDP socket after
`ExperimentalSourceJobBinding`'s HELLO/BOUND/ATTACHED exchange. A caller must
invoke `bind_confirmed(index)` only after the corresponding source job event
has genuinely completed its client delivery, MD acknowledgement and REARM.
The bridge cannot establish that assertion itself. A monotonically numbered
PULL yields one matching SAMPLE or NO_SAMPLE; a later pull is forbidden until
TCP delivery completes. Each sample must use the configured epoch/generation,
a confirmed index and the v1 motion limits. Velocity uses `-|-|-` to mean
unknown. Local actor handles are never transmitted. Unexpected packets, stale
identity, PID/peer guard loss, timeout or uncertain send permanently fault the
bridge and the shared TCP host. No UDP retries or fabricated receipts occur.

Separately, `saved_baseline` and `saved_guard(epoch, baseline)` opt in to
`register_saved(index)`, optionally through the scheduler's exclusive owner.
It sends a correlated `REGISTER_SAVED` and requires the exact
`SAVED_REGISTERED` reply before creating the local transport track. Both
operations share the monotonically increasing PULL request counter. The
guard is sampled throughout and is an external assertion, not proof of a
checkpoint, loaded save, actor identity across processes, or interest. A
failure after request dispatch leaves the X4-side effect uncertain and the
entire owner must be fenced. There is no retry or job-queue ACK. This path
alone does not bootstrap the client or establish a running session.

Optionally the session owner supplies `select_recipients(sample, members)`.
It receives detached copies of the validated sample and currently admitted
`{'id', 'incarnation'}` members and must return a list or tuple of distinct
current members. The callback runs under the shared exclusive TCP reader
fence; sample or membership mutation, foreign/stale recipients, reentrancy,
timeout or changed connection state fail closed. The selected peers must
confirm through the existing TCP motion sender. Without a selector the old
all-admitted behavior remains; that behavior does not establish interest.

An explicit empty selection consumes and discards that source sample with no
TCP send or receipt; `pull()` returns `None`, just as for `NO_SAMPLE`. In both
cases this does not report a delivery. Sequence, source time and frame checks
include discarded samples, so an old/replayed sample cannot become valid by
skipping delivery. A later selected sample may have a sequence gap. No empty
selection removes, expires or hides an earlier client sample. The caller must
provide actual, current sector/map interest and fence subscription changes;
re-entry, client-local object bootstrap, cross-frame reconciliation, sector
transition and despawn remain unresolved. The selector does not change the
all-client job/create ACK rules and does not itself implement interest.

`ExperimentalParticipantMotionIPC` pins one READY peer using an explicit
process/socket validator. A TCP participant callback sends one BIND request,
then blocks until the same request, epoch, generation, index, sequence, sector
and SHA256 digest return in BOUND. The BIND request also carries source game
time, position and either a complete velocity or `-|-|-` for unknown. The X4
update owner must send BOUND only *after* its asynchronous, request-correlated
local MD/FFI binding and the hold-only buffer push succeed.
The SHA256 is an opaque correlation echo, not game-side recomputation. The
bridge verifies PID/peer guards and deadlines before/after I/O. Despawn is
currently refused fail-closed: no checked X4 despawn implementation exists.

A BOUND response is an assertion of local identity and buffer ingestion; it
does not independently prove X4 execution, position or velocity application,
visual smoothness or frame equivalence. The buffer stores 3D samples in
`hold_only` mode: source game time and client real-time arrival are not assumed
to run at the same rate, and no interpolation or extrapolation is attempted.
An independently opt-in `allow_apply=True` enables `apply_once(sample)` on
this bridge. It accepts only the last successfully BOUND sample, matching its
epoch, generation, index, sequence and full-sample digest; it sends a fresh
request and requires the matching APPLIED after the X4 owner reports its later
local readback. A bridge allows only one attempt, with no automatic retry. A
missing or invalid reply permanently fences the bridge: the game-side write
may already have happened and cannot be rolled back. The result is the local
owner's assertion, not an independent visual, shared-frame or gameplay proof.
All timeouts must be nested so the X4 IPC deadline is below the enclosing TCP
operation, and that operation fits in the source bridge deadline. A failed
callback cannot undo any earlier peer or game-side effect.

`tools/dev/authority_motion_ipc_supervisor.py` supplies Linux PID/start/exe and
UDP inode validators using the existing private diagnostic helpers, but does
not own an X4 lifecycle by itself. The source process guard is also sampled
while the serialized TCP operation waits for the client. These checks are not
atomic authentication or a guarantee of future liveness. Fresh 32-hex leases,
attempts and generations, plus a fresh request-prefix per owner/process
incarnation, remain the caller's responsibility.

`ExperimentalJobMotionScheduler` gives an already queued source job priority
at each step, then registers its motion index only after the actual job ACK
and REARM. Otherwise it issues one motion PULL. This is serialized and cannot
preempt an in-flight PULL or TCP client readback: a job arriving during that
operation may exceed its own timeout. Such a failure fences the adapters; it
is not a liveness guarantee. A real session requires a verified end-to-end
deadline budget or a separately designed nonblocking multiplexer. The class
does not manage X4 lifecycles and is not installed as a production owner.

Focused tests use real local TCP and UDP sockets with simulated X4 endpoints,
including a delayed BOUND and wrong digest. They do not establish native X4,
Internet or Windows operation, successful gameplay or persistent replication.
