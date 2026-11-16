# Experimental local ship registry client

`lua/ship_registry_client.lua` is an opt-in local integration primitive for
`tools/dev/authority_ship_registry.xml`. It installs nothing, performs no X4
calls on import, and does not provide networking or sector identity. The MD
registry itself remains experimental. This adapter has not been tested in X4.

Construct with `new({enabled=true, epoch=..., timeout=..., issue=..., key=...,
to_md_actor=..., valid=..., clock=..., complete=...})`. The epoch is 32 lowercase
hex characters. The injected clock is monotonic seconds and timeout is between
zero and 300 seconds. The caller owns X4 event registration and calls
`client:on_event(name, value)` with the short MD event name. It must call
`client:tick()` to enforce the deadline, stop using a faulted client, and fence
events across process/load transitions. Route only fully qualified
`X4AuthorityShipRegistry.*` events to this adapter, strip that exact prefix,
and ensure it is the exclusive consumer issuing requests to the MD registry.
Normalize MD index and count values to Lua numbers only after verifying exact,
finite, integral representation within the safe integer range. Never convert
an actor ID through a rounded Lua number. `issue(screen, control, params)` must
return exactly true only when dispatch is confirmed; a wrapper must treat a
nil return from an underlying API as unconfirmed, not as proof of success.
Event delivery must be asynchronous.
The caller provides local actor validity, a stable process-local key and a
conversion to an MD-compatible actor. Both original and converted actor keys
must match. A resolved actor is local and must never be used as a wire ID.

The one-request methods are `initialize()`, `status()`, `enroll(actor)`, and
`resolve(index)`, called with Lua's colon syntax. Completion is delivered through
`complete(operation, value)`, which must return true: `Initialize` returns the
epoch, `Status` returns `{epoch=..., count=...}`, `Enroll` returns an index, and
`Resolve` returns a local actor. The methods return true when dispatched, or
false and a reason when refused. `state()` reports `idle`, `pending`, `failed`,
or `closed`; `close()` discards pending state. An error, unexpected event,
overlap, timeout, invalid or changed actor, bad clock, failed callback or
uncertain dispatch stops the adapter. There are no automatic retries.
`Initialize` is for a fresh, uninitialized MD cue only; the cue is one-shot and
cannot be assumed to initialize again after a refusal or reload. Initialization
timing, persisted registry readiness, and any required fencing belong to the
caller. Injected callbacks must not re-enter the client; a change to client
state during a callback invalidates the operation.

The deadline is checked after dispatch, before completion, and after the
completion callback returns. Callbacks cannot be interrupted: the timeout
detects an overrun only when control returns. A completion callback is therefore
provisional and must not commit external effects; its caller may use the result
only after `on_event` returns true. If the callback exceeds the deadline, the
adapter returns false and faults, but cannot undo effects already performed by
that callback. Actor conversion before a request is dispatched is outside the
request deadline and likewise cannot be preempted.

**Legacy correlation limit:** without the optional correlation mode, MD responses do not include a request ID.
An unexpected event while idle, a late event after timeout, and wrong response
types are rejected. However, a delayed duplicate of the expected event from an
earlier request is indistinguishable from the response to a new request of the
same type. Serialization and a new adapter do not remove that ambiguity. The
caller must not use legacy mode as a reliably correlated production protocol.

For an isolated experiment, specify `correlation_nonce` and `from_md_actor` in
the constructor. The nonce must be a fresh 32-character lowercase hexadecimal
value for every adapter instance, including across game/process reloads; its
uniqueness and event fencing are the caller's responsibility. The adapter
adds this nonce and a monotonically increasing local request number to each
MD request, and accepts only the matching `Correlated` response event. A stale
or malformed response faults the adapter; it is not retried. The caller must
register and route the full `X4AuthorityShipRegistry.Correlated` event before
dispatch and exclusively own registry requests and events. Legacy responses
and their original payloads remain in place when no request ID is supplied.

In this mode the MD actor is expected in hexadecimal text (`0x` plus one to
sixteen hexadecimal digits). `from_md_actor(text)` must convert it directly to
an exact local actor without passing through a Lua number, and `key(actor)`
must return its canonical decimal ID. The adapter independently converts the
hexadecimal text using digit arithmetic and checks this key before the existing
local actor checks. A previous separate native experiment observed a matching
hexadecimal reference for one local ship; this new path has not been run in X4. Counts and indices must be
exact safe Lua integers. Both MD formatting and callback behaviour need native
X4 validation; schema and synthetic tests alone do not establish that these
events are emitted or that actor text can be converted in X4. A unique request
ID does not authenticate or fence arbitrary senders, undo MD side effects,
establish global identity, or make this a production protocol.
None of the API establishes cross-instance binding, creation/destruction
coverage, multiplayer admission, or gameplay.
