# Isolated X4 job-activation host adapter

`authority_job_registry_host.lua` is a default-off local host for the queue and
driver. Import does not register handlers, start X4, open sockets, load or save
games. `new_x4` uses `ConvertIDTo64Bit`, a nonzero decimal string and
`ConvertStringToLuaID`, then checks the round-trip before passing a ship to MD.
Those bindings are covered by fake X4 exports, not by an actual host run.

A future single-X4 supervisor must supply an isolated empty 45841 profile,
exact expected save path, a fresh unique epoch, a newly initialized game with
neither experimental registry nor queue previously initialized, an explicitly
limited baseline of at most 64 live local ship references, and exclusive
ownership of UI/MD request and response handling. It must not run the existing
census probe concurrently: both register permanent response handlers. The
baseline entries must be real X4 Lua component IDs accepted by
`ConvertIDTo64Bit`, not raw FFI `UniverseID` handles or rounded Lua numbers.
Fake FFI exports do not establish the native conversion convention. The
supervisor starts the source game separately, provides `probe`, `report`,
`done`, and `fault` callbacks, calls `new_x4`, then `start`, and calls `tick`
from the already-owned UI update callback; it must not install a competing
`SetScript` handler. `report` and `done` must return exactly true. `fault`
must notify the supervisor, which fences the case and stops its owned process.
The Lua adapter does not prove process ownership or that other extensions are
absent. Its test-profile check alone does not establish isolation.

The adapter registers one callback per expected response, initializes the
registry, serially enrolls the supplied baseline, initializes the queue, and
checks ordered status fields before polling `Front`. It applies the generic
driver's local `Enroll` and `Ack` contract to each event, and checks status
again after each polling turn. Its source must remain unpaused with a valid
player and the expected path from queue initialization onward. Unexpected or
late replies, changed actors, invalid queue counts, fault/refusal, bad
conversion, callback failure, missed per-request deadlines or failure to drain
within `window + timeout` fence the adapter. `Abort` is best-effort; the
supervisor must not resume or save a failed or uncertain case.
An explicit `false` from `AddUITriggeredEvent` is treated as dispatch failure;
`nil` is accepted only as an unconfirmed dispatch and requires the expected
response before the timeout. Existing calls do not establish a native return
value contract.

The bounded `done` record reports queue activations, not ship births. An
`observed=0` result is `inconclusive_no_events`. Event time and sector are not
yet independently recorded. Events before queue initialization or after the
final status snapshot can be missed. The baseline is partial and non-atomic;
After the nominal window ends, the adapter continues draining the queue until
an empty status or the hard deadline. Without per-event timestamps, individual
events cannot be assigned to the original window or used to calculate a rate.
`new_registry_entry` does not imply a new ship. MD status is not an atomic
proof of engine-wide event coverage. The server's local acknowledgment proves
neither durable delivery nor any client-side creation. No checkpoint or client
is produced by this host.

`tests/authority_job_registry_host.lua` uses synthetic asynchronous MD
responses, including queue fault and timeout. The companion fake-X4 FFI test
checks the actor conversion at baseline enrollment. Neither is a native X4 run.

## Experimental attach to a saved register

The host now has a separate, default-off attach mode for a saved register; its
existing fresh-register mode remains unchanged. This is an offline-tested
adapter only, not a live recovery, delivery, or client-creation protocol. A
caller supplies `attach_saved_registry=true`, `expected_last` from a separately
verified checkpoint, `exclusive_registry_consumer=true`, and an empty local
`baseline`. It must fence all other registry request/response consumers,
including permanent census/resolve listeners, and own the single UI update
handler. The boolean is a caller assertion, not an enforced process lock.

Attach starts only in a verified paused local context. It sends the existing
registry `Status` request and requires the ordered epoch and exact last index;
it never sends registry `Initialize` or enrolls baseline ships. The existing
`Status` cue is a limited state check, not an independent full-table or saved
object bijection validation. Checkpoint marker, bytes, save provenance,
registry mappings, process/profile identity and absence of competing writers
must be established independently by the caller. A changed epoch/count,
missing/uninitialized/faulted registry, unexpected event, timeout or lost pause
fails the attempt.

It next checks that the job event queue reports `Uninitialized` and only then
attempts its one-shot `Initialize` while still paused. An already initialized
or faulted queue is refused; it is not reinitialized or aborted during this
preflight. Lost/uncertain initialization permanently fences the case. Once
initialization is acknowledged, the host waits for a confirmed running context
before the bounded observation window; resume is the external supervisor's
responsibility and a pause-to-resume timeout fails. Queue activations before
initialization are missed; activations after initialization but before the
nominal window can be drained and have no timestamps. The queue is not durable.

The job driver receives the checkpoint's actual last index, not the number of
locally known actors. The attach baseline is deliberately empty, so an actor
mapped to any existing index is `previously_unobserved_existing_index`, not a
newly created ship. A newly allocated next index means only
`new_registry_entry`; neither classification establishes birth, complete
coverage, client delivery or duplicate freedom. After a local queue
initialization attempt, an error may send best-effort `Abort`; the caller must
discard the disposable case after any uncertain response and must not save it.
Do not attach to or recover a previously active queue under this contract.

`tests/authority_job_registry_attach.lua` exercises status ordering, a large
saved last index, old/new/repeated actors, queue preflight, pause transitions,
refusals and timeouts using synthetic event callbacks. The fake-X4 adapter test
checks the paused/running guard with a fake FFI library. These do not establish
X4 callback timing, queue serialization after a real save, complete identity,
network delivery or a client counterpart.
