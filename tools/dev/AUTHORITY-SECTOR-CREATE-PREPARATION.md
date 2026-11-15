# Two-sector receiver experiment: preparation only

This default-off preparation is **not a runnable or native-start-ready
experiment**. No harness currently installs it, owns the single X4 update/event
dispatcher, implements or tests its native FFI readback adapter, fences a
process, or validates a final log. Do not load these scripts into X4 until
those missing pieces are implemented and independently reviewed.

`authority_sector_create_receiver.xml` is a test-only copy of the existing
receiver. The only behavioural change is sector resolution: the requested
sector macro must resolve via an unrestricted `find_sector multiple=true` to
exactly one local sector and that object must equal either stored
`X4AuthoritySectorReferenceFixture` sector with the same epoch. All original
registry, descriptor, pending, mutation, readback and fault guards are retained.
The copy has the same MD script name and screens as the original and must never
be installed alongside it. It is not production code.

`authority_sector_create_inspect.xml` defines a read-only preflight for a
healthy saved registry with last index 2, bidirectionally bound fixture indices
1 and 2, two distinct sectors, at least one outside `player.sector`, and an
uninitialized receiver. It also defines correlated readbacks for indices 3/4:
registered ship, reverse mapping, receiver receipt, all stored descriptor
fields, owner, macro, sector, healthy registry/receiver and cleared pending.
`authority_sector_create_driver.lua` is a dependency-injected serial state
machine that imports without registering X4 events. It requires a same-epoch
receiver initialization, creates and replays index 3 then 4, reinspects both,
checks returned local reference keys stay stable and distinct, requires a
remote target and matching candidate counts, and accepts a guarded finite
sector-position sample only within 2 m of the fixed test coordinates. A
refusal, unexpected event, mismatch, timeout, reentrancy, lost pause/context or
uncertain result fences the case; it does not retry or save. The driver checks
its deadline after the context guard and again after dispatch and reporting. A
dispatch that already sent a Create before a timeout or pause loss remains
indeterminate; the owner must discard the process and never retry it.

The future owner must implement the driver dependencies with one update owner
and one serialized consumer: confirm the pinned checkpoint/marker and pause,
securely identify the disposable profile and owned process, route each event
exactly once, enforce bounded stable argon fighter candidate enumeration, and
check actor and sector validity/class/relationship before and after a real
`GetObjectPositionInSector` read while paused. It must independently inspect
and test all X4 FFI signatures and handle conversions, fence timeouts and
cleanup, reject stock MD/Lua errors, protect overlay files and archive bytes,
and use a fresh output/profile with no save. It must also recheck save-derived
fixture macros and initial registry baseline. Pending or ambiguous mutation
requires discarding the process; there is no rollback or crash consistency.

The installed X4 `08.cat` `libraries/common.xsd:25075–25086` describes the
`sector` create attribute as using sector-space position. The fixed coordinates
here are only requested inputs; the old create experiment did not independently
read the source position. No collision-free location, native receiver behaviour,
exact duplicate avoidance, arbitrary-sector identity, NPC equivalence, real
network delivery, client reconciliation or playable multiplayer is established.
Candidate counts observe only the bounded selection, not a complete world.
The tests are synthetic and XML structural checks; no game was started.
