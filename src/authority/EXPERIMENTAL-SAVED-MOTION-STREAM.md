# Bounded saved-motion stream: offline orchestration only

`lua/experimental_saved_motion_stream.lua` is a default-off state-machine
prototype. It neither registers X4 callbacks nor opens a socket, starts a
process, sends traffic, or calls a game API. A caller must provide a real
saved-registry binder and one-shot writer with their existing local X4
environment, actor, parent, sector, docking, player and checkpoint guards;
passing callbacks is not proof that those guards actually exist. There is no
production session or server-X4 integration in this module.

At most eight samples for a single explicit epoch, generation, index and
sector are accepted. Sequence and source game time must increase strictly;
the first velocity is unknown. Arrival age is measured by the local monotonic
clock, not by comparing unrelated process clocks. The caller must separately
validate transport peer, grant, session, digest and actual sample provenance.
The digest and request token are correlation values here, not authentication
or proof of a cross-process coordinate frame.

For each accepted sample, the owner waits for the local asynchronous binding
to return successfully, pins the same local actor/sector/zone across samples,
and only then creates one writer. The existing writer's guarded pre-read,
distance fence, single write and delayed readback remain authoritative. The
next sample is accepted only after that writer has completed; overlapping,
replayed, stale or invalid work permanently faults the owner. A callback
after which a write might have occurred is conservatively marked uncertain;
failure never retries that write or rolls back earlier completed samples.
Completion callbacks are provisional until `tick()` returns true, and must not
alter the supplied sample.

Velocity, if present, is retained only as an observed input value. This module
does not extrapolate with it, request native velocity, use constant-velocity
mode or send NPC signals. It does not establish authority, HA handover,
collision clearance, correct cross-process frames, persistent gameplay or
visual smoothness. The existing writer's 5–50 distance and delayed <=3
readback gates make it unsuitable as a general continuous-play solution. Its
time and MD/FFI observations are non-atomic.

The reused writer still requires a delayed position within three units of its
target after at least one real second. In the separate native one-shot
`authority-client-to-server-apply-pair-03` attempt, a moving NPC's first write
had an immediate point read at the target, but the later observation was about
192.7 units away and the unchanged late check failed. That run did not use
this stream prototype. It shows why this writer can stop at the first sample;
the offline stream test does not establish practical continuous updates.

`tests/authority_saved_motion_stream.lua` composes the existing binding and
one-shot writer state machines with fake MD, fake positions and fake clocks;
it exercises three sequential samples, failure after a possible write,
identity changes, stale input and reentrancy. These are offline tests, not
native evidence.
