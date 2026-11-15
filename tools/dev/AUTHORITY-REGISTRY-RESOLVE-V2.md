# Isolated correlated registry resolve experiment

**The proposed table response is outside the documented `raise_lua_event`
contract and must not be used as a production protocol.** The local X4 9.00
schema `preparation/game-schemas/libraries/common.xsd`, in the
`raise_lua_event` element, documents `param` as a string, number or component.
The attribute is typed as an expression in the schema, so ordinary XML schema
validation alone does not enforce that documented runtime restriction.

This default-off experiment does not alter or replace the existing registry
screen. `authority_registry_resolve_v2.xml` exposes a separate read-only screen
for an existing registry; `authority_registry_resolve_v2.lua` is a standalone
synthetic client and does not register or install any callback. A separate
native diagnostic runner is described below; there is no production integration.

The MD cue tests the registry's epoch, fault flag, index, forward reference,
ship class, operational status and reverse reference. It proposes one event
containing a table with `request_id`, `epoch`, `index`, `actor` and `status`;
refusals return the same fields and a null actor. There is no split-event
fallback. A table-valued parameter is not supported by the documented event
contract; field names, null representation and the embedded X4 actor were not
demonstrated in native X4. A malformed input
may fail before any event can be emitted; timeout is not a correlated refusal.

The client requires explicit opt-in, a 32-lowercase-hex registry epoch, fresh
32-lowercase-hex request IDs supplied by its owner, a bounded deadline and at
most one outstanding request. It rejects wrong or duplicate IDs, mismatched
epochs/indices, bad actor keys, timeouts and reentrant state changes. Failure
poisons this instance; no retry or automatic recovery is attempted. The owner
must ensure request IDs are never reused across instances, fence old callbacks,
serialize every reader and writer sharing the registry, and use an isolated
disposable profile. The bounded seen-set rejects reuse within one instance.

An `ok` result is returned synchronously from `response` only after local actor
validity/key checks and a second deadline check. Those injected functions must
be read-only; no validation can guarantee actor validity at a later time. A
correlated refusal says no usable actor was returned, not that it was destroyed.
The payload contract and event ordering require native verification; structural
XML tests and Lua synthetic callbacks do not establish MD execution or save,
cross-process, multiplayer or production correctness.

`authority_registry_resolve_v2_live.py` and
`authority_registry_resolve_v2_native.lua` prepare one separate opt-in native
experiment in a private profile. The source must be paused, and the probe
selects and registers one existing operational ship. It then expects one
table response resolving registry index 1 to the same local actor, followed by
one correlated unavailable/null response for absent index 2. The same existing
world-bridge update callback owns the probe; no second `SetScript`, fixture
ship creation, movement setter, checkpoint request, client or multiplayer is
involved. The supervisor checks native pause and owned-process cleanup. The
private snapshot harness disables autosave, but this is not an independent
assertion that no private file could be written by the game.

One native attempt was made in X4, described below. If the table contract
differs or no response arrives, the runner fails; the
private engine log records response field names and value types without actor
values to help diagnose the actual conversion. Sampled pause checks are not a
proof of uninterrupted pause. A successful diagnostic would establish only
the observed local MD/Lua conversion, not durable identity or gameplay.

On 15 November 2026, `.local/authority-resolve-v2-01/result.json` recorded
`success=false` and confirmed owned-process cleanup. Its private engine log
shows `SHAPE stage=ok type=nil` followed by `ERROR ok_response`: the
ResolveV2 event handler was reached, but its second Lua callback argument was
nil instead of the expected table. Reaching this stage required the earlier
scalar registry initialization and enrollment responses. The result does not
identify which MD response branch ran or precisely how the value was handled.
The nil observation is consistent with the documented restriction; it is not
an independent proof about every possible MD-to-Lua interface. The
unavailable/null request was not reached. No save or client was involved.

An earlier `work/x4-attachment-integration/dev/cargo_probe.xml` contains a
similar `raise_lua_event` table expression and its Lua probe logs the value
type, but no native output from that probe was found in the inspected checkout.
Its existence is a hypothesis and not evidence of successful conversion.

Avoid repeating this table experiment as though the API supported it. A next
design would need one documented scalar/component payload and an independently
justified way to correlate an actor, or another established interface. No such
solution has been demonstrated here. A bounded diagnostic could first check a
scalar control and log callback argument count and types, without actor values,
while keeping the private profile, pause, deadline and cleanup safeguards. Do
not treat multiple separate events as an atomic correlated response.
