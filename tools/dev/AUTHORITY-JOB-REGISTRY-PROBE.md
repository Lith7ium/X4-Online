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


At the largest exactly representable Lua integer (`2^53 - 1`) the driver
refuses **before every `Enroll` dispatch**, including known reactivations. The
MD `Enroll` action can allocate before returning an index, so waiting to reject
an out-of-range response would be too late. This conservative capacity fence
also means no further existing actors can be processed by this driver once the
boundary is reached. It does not establish native exhaustion behavior or a
recovery path.
# Deferred source queue acknowledgement (experimental)

The existing source probe and host retain their original diagnostic behavior
unless `defer_ack=true` is explicitly set. In the deferred mode, enrollment
produces one provisional `report` before the MD queue `Ack`: the source
remains at `await_delivery`, with that original queue head still retained.
After a separate owner has verified receipts from all required clients, it may
call `host:confirm_delivery(epoch, sequence, index)` exactly once. Wrong,
late, duplicate or reentrant confirmation faults the diagnostic instead of
advancing it. The mandatory `delivery_timeout` bounds the wait. The host
requires its existing running-source guard throughout this wait: the paused
one-shot census coordinator cannot use this path without further integration.

After the corresponding MD `Acked` event, the host calls the mandatory
`queue_acked(epoch, sequence, index)` callback. It must return exactly true and
must not reenter the host. A callback failure faults the host but cannot undo
an already applied MD `Ack`. `report` remains provisional, and actor handles
are process-local. The external owner must bind client/session incarnations,
event identity, descriptor and each client receipt before confirmation. This
module itself neither collects nor authenticates client ACKs, survives a
restart, creates replicas, or proves that all clients received a ship.
Queue overflow and unavailable queued objects still fault; no event is silently
dropped. A running NPC activation is not necessarily a newly built ship.
