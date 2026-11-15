# Local job-actor descriptor experiment

These opt-in components inspect one actor that the existing job observer just registered. They start no X4 process and register no events on import. The MD cue is read-only and emits one correlated result containing request ID, epoch, registry index, ship, macro, owner, local sector and sector macro; it checks registry fault/epoch, both mapping directions, operational ship and sector. Its formatted handles are process-local. The Lua component checks the response against a fresh request and the actor from the observer's existing `Front`/`Ack` transaction, reads a finite position in the reported local sector, and rechecks actor/sector validity. It reports macro, owner, sector macro, position and bracketing game times; it does not return actor or sector runtime handles as descriptor fields. A sector macro is not an established unique or portable sector identity.

`authority_job_registry_probe.lua` and its host expose the transient original `Actor` event as a second argument to the **existing** report callback only when `expose_actor=true`; the default callback still receives exactly one argument, and the existing saved event row has no actor field. This does not add an `Enrolled` listener. An enabled observer owner must select one `new_registry_entry`, preserve the original value without rounding, create one descriptor request with a fresh ID, route only its own Result callback and fence all competing consumers. The exact local actor is required: unsupported raw event types and unsafe Lua numbers at or above 2^53 fail, even if a later conversion appears valid. The X4 adapter additionally converts the raw event through `ConvertIDTo64Bit` and requires exact agreement with its original representation. These constraints can refuse representations that X4 may actually use; they must not be relaxed based only on a rounded value.

The observer reports after its local queue acknowledgement. This probe is **not integrated into the observer runner**, and starting it from a report callback without an explicit owner is unsafe. A future dedicated disposable experiment must permit only one outstanding descriptor request; after the selected report it must prevent any next Front/Enroll while checking the observer's fault state, queue overflow, source/process/sector validity and both deadlines. Missing, duplicate, late or inconsistent replies, loss of actor or sector, owner/context change, overflow, timeout or interruption must fence the entire case, with no retry after an uncertain operation. Pausing observer polling does not pause the game or its job event queue: events can accumulate or overflow. The current components do not prove absence of gaps. No production observer, network protocol, persistent row format, or auto-installation is changed by enabling the option alone.

MD fields and FFI coordinates are separately sampled while the universe runs; the time bracket does not make them atomic or prove a stable trajectory. The result only concerns one local observation: `new_registry_entry` means a new register entry, not a newly born ship. Neither a descriptor nor a queue acknowledgement proves complete universe coverage, client delivery, successful reconstruction, cross-process object identity, Windows or Internet operation. Runtime source and sector handles must not be sent to another process or persisted as identity.

Synthetic Lua tests exercise wrong IDs, stale request, deadline, context loss, invalid descriptors, reentrancy, and the default/opt-in callback contracts. A fake-X4 FFI library exercises an exact uint64 actor above 2^53 and rejects an unsafe double. These tests alone do not establish actual MD output, live X4 callback ordering, object identity, or queue behavior.

## Isolated Linux observation

On 2026-11-16, `.local/authority-job-descriptor-01` completed one disposable
Linux X4 run. The log records the load request, expected saved marker, pause,
registry-attach READY and resume in that order. The first acknowledged job
event was sequence 1 / new registry index 10055. Before the next event, the
descriptor callback reported `ship_gen_m_tugboat_01_a_macro`, owner
`pioneers`, sector macro `cluster_115_sector001_macro`, and sector-relative
position `(-132217.203125, 6004.3818359375, 169081.265625)` metres. Its game
times were 13.122914898 before the request and 13.130593159 before and after
the position read. These are separately sampled attributes and coordinates,
not an atomic state or a measured velocity.

The log then reports sequences 2–23 / indices 10056–10077, followed by
`observed=23 acknowledged=23` and the final pause. The result reports no
owned processes remaining. The archived source save and staged copy both
currently hash to `64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
that does not independently establish the bytes X4 consumed. The monitored
conversion/arithmetic and probe/MD/Lua error patterns do not appear in the
engine log, although startup logs contain read-only config, graphics-queue and
missing-signature errors. The filter is not a complete engine-error detector.

This records a single local descriptor for a newly allocated *registry entry*;
it does not establish ship birth, a complete event stream, durable delivery,
unique sector identity or another client's object. Activations may also occur
between the last queue status and final pause. No client, reconstruction,
cross-sector replication, Windows, Internet or gameplay was tested.

## Isolated attach diagnostic

`authority_job_descriptor_live.py` and `authority_job_descriptor_attach.lua` prepare one opt-in Linux-only experiment on the existing pinned census checkpoint. The existing private archived-save loader, provenance checks, read-only save mount, script protections, process guards, exec gate and owned-process cleanup are reused. No game save or client is requested. The original observer remains the sole registry/queue consumer, and the existing load callback is the sole update owner.

After paused registry attach and resume, the first `new_registry_entry` is acknowledged by the existing queue. Its original local Actor is then used for exactly one descriptor request. Until its response, the same update owner stops further observer ticks, checks the descriptor timeout and source guard, and leaves the observer's already registered queue-fault callback active. A fault or timeout fences the case; the test does not attempt to recover an acknowledged event. The observer then resumes draining and finishes by pausing the private instance. No new entry, an unsupported Actor representation, an unavailable descriptor or overflow is an unsuccessful or inconclusive experiment, not evidence of absence. A successful parser requires exactly one sample, bound to the first new registry entry, before the next observer event or final summary; it validates finite values and the game-time bracket.

The result is one non-atomic local activation sample, not proof of object birth, exact loaded bytes, sector identity in another process, complete or lossless event coverage, delivery, reconstruction, or gameplay. An asynchronous queue may fill while the descriptor is pending. The returned macro, owner, sector macro and pose reflect separately timed local reads; no local Actor or sector runtime handle is written into the result. Synthetic state-machine, overlay and log checks do not establish native X4 event ordering. No native run for this wrapper is recorded here.
