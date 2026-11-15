# Prepared natural NPC flight experiment

The fixture and evidence checker are wired to an opt-in runner. One native run
observed a moving, NPC-piloted fixture after a `MoveWait` order while game time
advanced. No file starts X4 or changes a save merely by being read.

One isolated Linux/Linux attempt was deliberately interrupted after several
minutes of stalled progress. Its server log recorded the pilot/MoveWait `ORDER`
receipt, but no source `SAMPLE`. The file service was still active when the
stall was investigated, and the result reported the server as paused with no
admitted client. There is no evidence in that attempt that the terminal fence
completed, that the bridge resumed the server, or that the fixture flew. The
log did not record whether the `ARMED` datagram reached the supervisor, so the
exact cause of the stall is undetermined. A synthetic UDP test subsequently
found that losing the single `ARMED` datagram stranded the previous handshake;
this is a possible failure mode, not proof that it caused this attempt. The
source now repeats `ARMED` while paused, and the supervisor records stage names
without leases and uses bounded per-receipt waits for future diagnostics.

A subsequent isolated Linux/Linux run passed this diagnostic. Its recorded
pilot and `MoveWait` order preceded 1,290 source samples; during those samples
game time advanced by about 32 seconds and the source moved about 3 km. The
checker recorded 201 guest position writes and 201 matching readbacks, using a
maximum 5 m target error and a 0.75 s guest-local readback window. The source
used a finite-difference rate from measured positions, not native velocity.
The progress log records the terminal offer fence, bridge resume, source stop,
and confirmed bridge pause. The coordinator was then stale; no checkpoint was
created after this flight and no client was admitted.

This is evidence for one controlled fixture and the recorded readbacks in two
isolated same-sector Linux instances. It does not independently prove every
cause of the observed movement, exact loaded bytes, collision clearance,
atomicity, visually smooth motion, universe-wide synchronization, admission,
shared gameplay, Windows operation or an internet connection.

The existing post-checkpoint `authority_create_test_fixture.xml` creates a ship
without an explicitly assigned pilot. The runner adds a pilot selection only to
its disposable source overlay and requires a pilot receipt; the unmodified
spawn is not pilot evidence. The MD
fixture expects an already enrolled operational ship and checks its registry
mapping, frame, direct parent, player exclusion, docking state and pilot before
creating a `MoveWait` order. A separate guard compares the current pilot to the
stored pilot reference before each source sample. In the successful run, the
fixture emitted the pilot/order receipts and the source guard allowed sampling;
the source observations showed movement. This is one positive runtime
observation of those cue paths, not independent proof of the object's complete
pilot or order state, of order completion, or of why the ship moved. Behavior
when the pilot changes, an order is missing, an object becomes unavailable, or
the sector/parent changes has not been verified in native X4.

Run `python tools/dev/authority_npc_flight_md_check.py` for an XML syntax
precheck. An independently available local X4 `md.xsd` may be supplied with
`--xsd /path/to/md.xsd` for optional, potentially expensive schema validation.
Neither precheck runs MD or verifies its expressions in X4. The successful
native run exercised the positive cue path described above; it did not exercise
the negative conditions or verify all MD expression semantics independently.
The stock MD schema has not been validated against these files.

`authority_npc_flight_evidence.validate` checks the runner's instrumented
format. It has synthetic coverage and was exercised in the successful native
run above; its behavior under the negative native conditions remains unverified.
For every source sample it requires the source
position, finite-difference rate, monotonic sample time, and the actual
reference position and monotonic time used to derive that rate. It recomputes
the rate; the data must come from instrumentation that logs the very same
values used to send the sample. Source samples must follow the pilot/order
receipt on the source process's monotonic clock and show advancing game time
and position. Guest writes and readbacks carry the registry identity, frame,
and a stable guest-local actor token. The guest monotonic timestamps are
compared only with other guest timestamps; each readback must follow its write
within 0.75 seconds. The checker cannot authenticate these caller-supplied
values, establish how the source moved, or prove NPC flight by itself.

The runner invalidates offers and closes the transfer service before using the
bridge exclusively for server resume, treats the coordinator as stale, stops
source sampling before requesting a confirmed bridge pause, and never returns
to the session. The source samples without a native setter; the guest uses the
existing pause-guarded diagnostic setter. The native behavior, including guest
pause enforcement and missing identity, parent, pilot or clock failures, still
requires independent verification. The source refuses STOP if X4 is already
paused at that update; sampled pause checks do not establish continuous engine
state between UI updates.
A moving fixture in disposable profiles does not establish persistent-world
synchronization, network play, combat or a smooth player experience.
