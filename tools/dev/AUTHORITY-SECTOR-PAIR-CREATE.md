# Two-process index-3 creation probe components

These opt-in components are not installed by the normal extension or by the
pair-readiness harness. They do not start X4, install an `onUpdate`, open a
socket, create an ACK or choose a multiplayer protocol. Each X4 process must
have one exclusive update/event owner. The caller must first establish both
private profiles, the pinned common save and marker, pause, registry epoch and
baseline entries 1 and 2, and that neither receiver was already initialized.
The test uses the saved first sector and requires it to differ from each local
player sector. A process-identity, protected-file, deadline, archive and cleanup
fence must remain active throughout. No normal save or profile is appropriate.

The source and client state machines each perform Initialize, index 3 Create,
correlated local Inspect, the same Create request again, and a second local
Inspect. Each Inspect checks registry/receiver bindings and stored requested
fields in MD. Lua compares the same **local** actor and sector across the two
inspections, queries a sector-space FFI position, checks pause and stable game
time, and accepts at most two metres difference per coordinate from the Create
request. It also compares a guarded, faction/macro-filtered candidate count
against its baseline and baseline plus one. This count has unknown coverage and
is not proof of global uniqueness, identity or collision clearance. The MD and
FFI checks are not atomic, and no native X4 execution of these new components
is claimed.

After its second inspection, the source calls the injected nonblocking
`emit_descriptor` callback with exactly `attempt`, `epoch`, `sequence=1`,
`index=3`, `macro`, `sector`, `owner`, `seed`, `x`, `y`, `z`. The coordinates
are the actual source-side FFI readback, not its original create request. The
seed is the test's Create parameter, not an independent readback. Actor and
sector handles and local comparison keys stay inside the local process. The
`emit_descriptor` callback may only record a local intent. Forward it only
after the driver event has returned successfully in `await_ack`, a subsequent
guarded update succeeds and the external process/pause fence is checked; discard
the intent if any of these checks fails. The source remains in `await_ack` until
`confirm_ack` receives the matching four
fields `attempt`, `epoch`, `sequence`, `index`. The loopback transport names this field `seq`; the integration must map it
exactly to/from `sequence` and validate all correlation fields. The caller must
only confirm once the transport has verified a client ACK.

The client accepts one descriptor via `accept_descriptor`, validates the exact
field set and test-specific bounds/identities, then passes its values to its
own receiver. Only after the second MD and FFI Inspect and count check does it
call injected nonblocking `inspect_complete` with those four correlation fields.
This callback may only record a local completion intent; it must not send an
ACK or expose a completion to a concurrent sender. The caller may send the
transport ACK only after the driver event has returned successfully with state
`done`, a subsequent guarded update succeeds and all external process/pause
fences are checked. A callback that overruns the deadline or loses pause can
record an intent even though the driver subsequently fails; that intent must be
discarded. Callback success
is a dispatch/queue assertion, not proof of delivery; a callback that sends and
then fails has an indeterminate outcome. Do not retry a failed/uncertain Create.
The attempted descriptor, MD argument bridge and replay behavior need native
validation before use.

The X4 adapter requires a `fault` callback and invokes it on failures, including
late events. Continue polling and monitoring faults through terminal cleanup;
`done` is not proof that a late event or later process loss cannot occur. All
callbacks invoked on the game update thread must return promptly and must not
run blocking TCP or wait for other X4 events. Reentrancy fails closed. The
synchronous checks are point observations and cannot preempt a stalled native
callback. On timeout, lost pause, process failure or uncertain delivery, fence
and discard the disposable case. Test transport and supervised helper lifetime
remain separate integration tasks; source/client runtime handles never cross
that boundary.

Offline checks:

```
python3 -m unittest discover -s tests -p test_authority_sector_pair_create.py -v
```

The LuaJIT fake exports verify adapter wiring and float conversion with tiny
synthetic IDs. They do not prove actual X4 FFI, large-ID behavior, saved-sector
identity, actor equality across processes, native placement, TCP/UDP behavior,
Windows or multiplayer gameplay.
