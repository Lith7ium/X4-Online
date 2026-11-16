# Two-sector receiver experiment: preparation only

This default-off experiment has an isolated process harness, but is **not yet
native-start-ready** pending independent review of its process, callback and
log fences. The FFI adapter and orchestration are tested only with fake X4
APIs; no native create run is recorded.

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

`authority_sector_create_owner.lua` is an opt-in event owner and FFI adapter. It
registers no events on import and installs no `onUpdate`: an external owner
must call `start()` once and `update()` from the sole update hook. It checks
profile/pause/game time, local sector and ship handles and position before and
after the read. It bounds the argon faction list, checks truncation, list/count
stability, valid unique local handles, exact ID round trips and macro lookup.
Fake-X4 tests exercise these checks, but the adapter has not run against real
X4. The enumeration is faction-wide for one macro; it is not a sector census,
complete universe coverage or proof against every autonomous duplicate.

Driver completion is `pending_fence`, never a final success: a late event
permanently fails it. `authority_sector_create_live.py` prepares the pinned
checkpoint in a private profile and uses the existing gated owned-process,
archive, marker, pause, protected-file and final-log checks. It binds the whole
private save directory read-only and never issues a save. The only load update
owner calls `authority_sector_create_run.lua`; it checks profile, player,
pause, game time and a deadline on each sampled frame, waits for a half-second
settle after `pending_fence`, then emits a completion receipt. The private
owner copy logs an error immediately on later callback faults; final validation
rechecks the log after owned-process shutdown and refuses any such error. The
source archive and output paths must be disjoint, and source fingerprints are
checked again after a successful run. If process cleanup is unconfirmed, the
underlying harness retains its lock. These are sampled checks, not an atomic
proof of uninterrupted pause or an absolute guarantee against log ABA.

The caller must still establish exclusive event routing, and X4 FFI signatures,
handle conversions, MD cue semantics and the final callback/process boundary
need independent review and native validation. A fault or late ambiguous
mutation requires discarding the private process; no retry or save is safe. It must also recheck save-derived
fixture macros and initial registry baseline. Pending or ambiguous mutation
requires discarding the process; there is no rollback or crash consistency.

The installed X4 `08.cat` `libraries/common.xsd:25075–25086` describes the
`sector` create attribute as using sector-space position. The fixed coordinates
here are only requested inputs; the old create experiment did not independently
read the source position. No collision-free location, native receiver behaviour,
exact duplicate avoidance, arbitrary-sector identity, NPC equivalence, real
network delivery, client reconciliation or playable multiplayer is established.
Candidate counts observe only the bounded selection, not a complete world.
The preparation tests were synthetic and XML structural checks; the later
isolated native attempts are described below.

## First native attempt and diagnostic hardening

The isolated `authority-sector-create-01` attempt requested the checkpoint,
observed its marker, completed the slot-2 read and reported pause. It then
logged a generic owner error before any create-readback ROW. The result is
failure, with no owned processes reported remaining. The old log did not
identify the failing owner/driver/FFI phase or whether a Create request had
already been dispatched. Do not interpret the absence of ROW as evidence that
no in-memory ship was created; the disposable case remains indeterminate and
must not be reused. Its artifacts and failure result are unchanged.

The current probe emits fixed, non-sensitive diagnostic categories for owner,
driver and FFI phases, including candidate conversion, plus ordered before/after
dispatch receipts for Preflight, Initialize, Create and Inspect. They contain
no actor IDs, descriptors, leases or exception text. A `before` receipt means
only that dispatch was about to be attempted: the deadline and pause are checked
again before the API call. An `after ... accepted` receipt means the local API
returned without refusal, not that MD completed or a ship was created. An
exception or missing after-receipt leaves delivery indeterminate. Diagnostics
are written inside the existing deadline fencing, and logging failure, late
callback or slow dispatch still faults the whole disposable case. For a
successful result the log validator requires the complete ordered before/after
sequence, the six readbacks, pending fence and final receipt; the post-cleanup
log check still rejects late faults. Missing logs do not establish that an
action did not occur.

The diagnostic update is covered by fake-X4 tests for failure before and after
a Create dispatch, a slow logger on either side, candidate ID conversion,
pause loss, late callbacks, invalid receipt order and final-log faults. These
are synthetic checks; no native follow-up is claimed here.

## Second native attempt and LuaID conversion

The isolated `authority-sector-create-02` attempt also failed. Its marker,
slot-2 read and paused-load receipts preceded `ADAPTER_FAIL count_conversion`,
`DRIVER_FAIL new callback_failed` and `OWNER_FAIL driver_start`. The installed
driver reaches that initial faction count before issuing Preflight, and the log
contains no dispatch receipts; its code therefore did not send Preflight,
Initialize or Create on that path. The result reports no owned processes
remaining. The artifacts and failure result remain unchanged.

The diagnostic at that revision did not distinguish the LuaID creation call,
returned value type, direct check or reverse conversion, so it does not prove
which substep failed. An X4 LuaID represented as `userdata` is a plausible
explanation: the old check tried to treat the opaque value as a numeric handle.
The revised adapter permits `userdata` only as an opaque argument to
`ConvertIDTo64Bit`, and compares that result against the independently captured
exact fleet uint64. Numeric or cdata references must also independently pass
the exact direct check; unsafe numbers and other types fail closed. Value-free
failure categories distinguish creation, null/unsupported type, direct check,
and reverse-conversion call or comparison, without logging IDs or exceptions.
Fake LuaJIT tests cover real userdata, exact uint64 above 2^53, failed and
rounded reverse conversions, unsupported types and direct checks. They do not
establish the actual native return type or the cause of the second failure.

## Third native attempt: two remote sectors in one paused process

The isolated Linux run `.local/authority-sector-create-03` reports success and
no owned processes remaining. Its log records the checkpoint load request,
saved marker, slot-2 read and pause receipt, followed by ordered Preflight and
Initialize dispatches. Each Create and Inspect dispatch has its before/after
receipt, followed by six readback rows, `PENDING` and `DONE`. The after receipt
is only local dispatch acceptance; the subsequent readbacks are the evidence
for this bounded case. The archived receiver, inspector, engine and run-script
bytes match the reviewed sources; the owner and driver overlays match apart
from their expected module exports.

Registry index 3 was created and replayed in
`cluster_33_sector001_macro`, and index 4 likewise in
`cluster_45_sector001_macro`; both sectors were reported remote from the
player's sector. Each position readback was (-400, 100000, 500) in that
sector's coordinate space. The argon faction-wide count for the selected ship
macro started at 156, was 157 after index 3 and its replay, and 158 after
index 4 and its replay; final reads of both indices retained 158. The log
reports game time 3.014 throughout these readbacks. These are artificial test
ships and requested fixture positions in one paused process, not transferred
positions or observations of naturally generated NPCs. The count is neither a
sector-wide nor a universe-wide census, and the fixture does not establish
collision-free placement or exclusion of all duplicate objects.

This run does not establish two-process replication, network delivery, client
identity or reconciliation, continued simulation, or gameplay. Pause and
process checks are sampled, not proof of continuous pause or exact X4-loaded
bytes. No checkpoint was requested by this experiment.
