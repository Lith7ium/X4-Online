# Experimental MD ship-reference registry

`authority_ship_registry.xml` is a default-off MD script for an isolated X4
experiment, not an installed extension or a production protocol. The local X4
instance designated server supplies real, currently operational ship objects;
the script stores their MD references. A server-chosen, unique nonempty epoch
and a monotonically allocated integer together name a registry entry. The epoch
must be created and checked by the caller; the MD script does not authenticate
it or a client. Never use a local runtime object ID as a network identity.

Install the XML only in a disposable experiment overlay. Send events to screen
`X4AuthorityShipRegistry` using `AddUITriggeredEvent` and register handlers for
the event names below. Wait for each response before issuing the next request:
concurrent request correlation and delivery ordering are not established.

* `Initialize({epoch=...})` returns `Initialized(epoch)`. Send this exactly
  once for a fresh test world, with a validated unique string. The non-instanced
  state cue persists, and it cannot reset itself to a new epoch.
* `Status({})` emits `Epoch(epoch)` followed by `Count(last)`, or
  `Uninitialized` or `Faulted`. Count is the highest issued integer, including entries that
  cannot currently be resolved; it is not an operational-ship count.
* `Enroll({epoch=..., ship=...})` accepts an X4-local object reference and emits
  `Enrolled(index)` or `Refused`. The reverse table keys are object references,
  not names, macros or process-local IDs. Each request must supply the exact
  saved epoch. An existing mapping is checked
  against the forward mapping before it is returned.
* `Resolve({epoch=..., index=...})` emits `Actor(object)` or `Unavailable` for a missing,
  non-operational, non-ship, wrong epoch, or out-of-range reference. Unavailable does not
  establish destruction; no deletion or reuse operation is implemented. A valid
  reference must also pass the reverse check.

An inventory source can pass each candidate local object to `Enroll`, await the
answer, and retain the returned epoch/index with its subsequent observations.
The diagnostic fleet scanner is a candidate source, not a proved complete,
atomic inventory. Additional discovery and reconciliation are needed as ships
appear, disappear or change context. A remote instance can resolve a registered
entry only after loading the checkpoint containing the register. This does not
bind independently created ships after a checkpoint or synchronize their state.

The implementation uses object-keyed tables instead of a full scan for each
registration; no complexity or performance guarantee follows. One isolated
Linux/Linux run enrolled and re-enrolled 10,054 operational candidates, saved
them, then resolved and re-enrolled all of them in a second X4 instance. The
checkpoint's forward and reverse tables were independently checked against
10,054 distinct saved ship components, and their per-index macros matched both
processes' observations. The inventory saw 140 sectors and rejected 49 other
distinct objects as unconfirmed. This is evidence for this checkpoint and the
observed candidates, not complete universe coverage or an independent binding
of each client runtime object to its saved component. Destruction, creation
after checkpoint, and index invalidation remain unverified. No clients were
admitted and no gameplay was tested.

An inconsistent reverse entry or write readback latches a fault. Allocation
uses a separate saved counter rather than the number of currently present
entries, so intended no-reuse does not rely on table compaction; destructive
lifecycle behavior requires native verification. This experimental code must
not be used as a production gameplay adapter.
