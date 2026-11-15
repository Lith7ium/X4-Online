# Job-activation to registry diagnostic

`authority_job_registry_probe.lua` is a disabled-by-default, transport-free
driver for the experimental local `authority_job_ship_events.xml` queue and
`authority_ship_registry.xml` registry. No X4 game or callback starts on
import. It does not discover every ship, create a client ship, deliver an
event, or prove that an activation is a birth. The X4 event and queue have not
been demonstrated natively by this diagnostic.

Use only in a disposable server experiment. The caller must initialize the
registry and queue with the same fresh epoch, capture the registry's highest
allocated index, and start consuming a freshly initialized queue at sequence
1. A baseline maps only independently observed local actor keys to the matching
registry indices. It may be partial; it is not a universe census. Local actor
keys must be unique throughout this diagnostic and must never be sent as
network identities. The driver must ensure exclusive serialized queue and
registry access and independently fence process, loading and checkpoints.
Do not run the existing census probe alongside this driver: its persistent
registry response handlers expect their own pending operation and can fault on
this driver's `Enrolled` response. A future combined test needs one shared,
serialized registry consumer, not two independent event listeners. An empty
observation window is inconclusive.

`new({enabled=true, epoch=..., last=..., baseline=..., issue=..., key=...,
to_md_actor=..., valid=..., report=...})` requires explicit callbacks. `issue(screen, operation,
args)` submits a local MD request and must return `true`; it is not an
acknowledgment. `key(actor)` returns a nonempty local identity string;
`valid(actor)` returns exactly `true` only for the intended live object.
`to_md_actor(actor, key)` must convert the event value through X4's
`ConvertIDTo64Bit`, a validated nonzero decimal string and
`ConvertStringToLuaID`, before any registry enrollment. `key` must return the
same identity for both the event value and converted MD Lua ID. Conversion,
round-trip identity and actor validity failures permanently fault the probe.
Avoiding the raw Actor event value as `Enroll.ship` remains the adapter's
responsibility: the generic probe cannot prove that the injected callback
produced an MD Lua ID. Actual conversion semantics require a native host adapter.
`report(row)` must return exactly `true` after accepting the diagnostic record.
The caller invokes `front()` only when the prior operation completed and
dispatches each MD response in order through `event(name, value)`. It must
independently call `timeout()` for a missing response, monitor asynchronous
queue faults and discard the diagnostic after any failure. An `Abort` is
best-effort; it is not proof that the queue stopped. Never retry after an
uncertain operation or reuse the case as a checkpoint.

An `Empty` ends a poll. An item flows through `Sequence`, `Actor`, registry
`Enroll`, and queue `Ack`; only the exact `Acked` sequence allows a report.
Missing/changed actor references, a duplicate or gapped queue sequence, an
index collision, inconsistent prior binding, a new-index gap, unexpected
events, a rejected request, callback failure, remote refusal, overflow or
timeout permanently fault the driver. Repeated legitimate activation of the
same actor is reported as `previously_observed`; it does not allocate another
identity. An unknown actor with an existing index is
`previously_unobserved_existing_index`, and a newly allocated index is
`new_registry_entry`. Neither establishes when the ship was created.
Every record explicitly reports `birth_confirmed=false` and
`delivery_confirmed=false`. Local `Acked` has no durable or client-delivery
meaning, and a crash can lose an acknowledged event.

`tests/authority_job_registry_probe.lua` uses callback doubles only. Before any
native observation, a separate local driver must establish the X4 event names,
reference conversion, initialized state and bounded event handling. The local
schema describes `event_job_ship_activated` for job ships activated after a
space spawn or shipyard completion; it does not prove universal creation-event
coverage. Additional independent evidence would be required to identify an
actual birth or establish how complete this observation is.
