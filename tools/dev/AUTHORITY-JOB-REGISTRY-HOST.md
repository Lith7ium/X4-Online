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
