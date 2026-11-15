# Experimental job-activation queue

`authority_job_ship_events.xml` is a default-off, uninstalled server-side MD
experiment. Its sole source is X4's `event_job_ship_activated`; its event
parameter is the actual local job ship reference. The local MD schema describes
job ships activated in the galaxy, including those spawned in space or finished
at a shipyard. This is not documented as covering every ship-creation path, nor
does activation prove that a ship did not already exist. Event delivery,
reference lifetime and all script semantics below need native verification.

Install only in a disposable server overlay with the experimental ship registry.
Use a trusted local driver and strictly serialize all requests and replies.
Initialization must follow successful registry initialization and precede the
observation window. Events before it or after a fault are not counted. This
script cannot detect unreported engine events. All events are local, and object
references and sequence numbers must not be treated as network identities.

Send UI events to screen `X4AuthorityJobShipEvents`:

* `Initialize({epoch, capacity})` accepts the initialized, healthy registry's
  epoch and a capacity from 1 to 1024, then emits `Initialized(epoch)`. An
  invalid initialization emits `Refused`; the one-shot state cue cannot be
  reinitialized, so discard that isolated experiment. Validate the table and
  its types in the driver. Initialization is not an authentication mechanism.
* `Status({})` emits `Epoch`, `Observed`, `Acknowledged`, `Depth`, `Inflight`, `Reason`,
  then either `Healthy` or `Faulted`; before initialization it emits
  `Uninitialized`. `Observed` counts handler invocations until the first fault,
  including the invocation which faulted. It does not count missed events.
  `Healthy` also requires the registry to have the same epoch and be unfaulted
  at the instant of this check. The first fault reason is retained for diagnosis.
* `Front({epoch})` returns `Empty` or emits `Sequence(number)` then
  `Actor(local reference)`. It keeps the head in flight until acknowledged;
  repeated reads refer to that same head if the object still exists. Lost,
  reordered or ambiguous replies are failures, not evidence of delivery.
* After obtaining an operational ship, the driver must use the existing
  `X4AuthorityShipRegistry.Enroll` and await its unique index. Only then may it
  send `Ack({epoch, sequence, index})`. `Acked(sequence)` is emitted only if
  the sequence is the in-flight head and both registry tables map the exact
  queued object to the supplied index. If it is already registered, enrollment
  may return an existing index: job activation alone is not a create command.
  `Acked` removes the event and confirms **only local enrollment**: it does not
  acknowledge durable delivery, client receipt, client creation or replication.
  If delivery or process state is lost afterwards, this queue has no replay.
* `Abort({epoch})` latches `Faulted`. A driver must abort on unexpected,
  ambiguous or missing results, inability to process an object, or uncertain
  state, and discard the disposable experiment. Once initialized, a wrong-epoch
  front request, invalid acknowledgement, or loss of the queued reference
  faults the queue. `Status` retains a reason such as `ack_refused` or
  `queued_object_unavailable`; do not retry blindly.

Queue overflow, invalid event objects, lost queued references, a mismatched or
faulted register during activation, and sequence exhaustion latch a fault.
`Faulted` can arrive asynchronously when an activation is handled; the driver
must watch for it independently of the serialized request/reply exchange.
There is no persistence transaction for delivery, no safe recovery protocol,
no timeout, and no automatic checkpoint or lifecycle coordination. `Ack` only
proves the MD tables agreed at that instant; the driver remains responsible for
the actual registry response and any later network delivery. Never infer that
the client has received, created or reconciled the object from an `Acked`.

The existing client creation fixture demands consecutive server register indices
and only accepts the client's current player sector. Therefore selectively
forwarding events for one sector can leave an unfillable index gap. Existing
ships activated again, concurrent enrollment, and autonomous client spawns add
further ambiguity. A connected experiment must address these constraints
explicitly and stop on gaps; it cannot claim full-universe synchronization,
complete ship state or absence of duplicate ships.
