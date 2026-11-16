# Isolated census replica MD experiment

These default-off scripts are only components for a disposable, paused client
experiment. They do not install themselves, own an update loop, open sockets,
read a save, or supply pause, process, deadline, transport, FFI, or cleanup
fences. The archived registry and identity fixture must remain byte-identical;
no existing scripts are modified. The pair harness must not install other
consumers for the same events. A failed or ambiguous mutation requires the
entire disposable profile to be discarded, never an automatic retry.

The one-shot State cue handles `X4AuthorityCensusReplica/Initialize` with an
`epoch` argument. It requires a healthy existing registry of that epoch with
last index 10054, empty 10055 and no receiver state. It creates private receipt
state but does not reset or initialize the registry. `Initialized` returns the
epoch. A duplicate Initialize can be ignored by X4's one-shot cue; absence of
the expected correlated event is a failure/timeout, not evidence of success.

`Create` takes `epoch,index,macro,faction,sector_macro,seed,x,y,z,witness_index`.
The caller must have already validated a real source descriptor and a matching
client witness, and provide exactly index 10055 and the **artificial** local
seed 7183. The existing transport has no seed field. All values are checked by
the caller before dispatch; X4 MD may reject invalid expressions before its
Refused action runs, so timeout also fails closed. The script checks bounded
coordinates, resolves the faction uniquely and finds exactly one local sector
matching the live, undocked saved registry witness and its reverse mapping. It
sets pending before `create_ship`, uses level 1 and variation 0, checks the
created ship, and stores the receipt and all request fields together with the
forward/reverse registry entry and last index. It never adopts or deletes an
existing ship. On refusal it marks available registry/receiver fault state and
emits `X4AuthorityCensusReplica.Refused`. Partial mutation is indeterminate.

After `Created` (10055), the sole owner invokes `Inspect` with the same fields
plus a unique `request_id`. The separate inspector repeats the sector-witness,
registry, receipt, actor, macro, faction, and complete stored-field checks and
returns `Inspection` containing
`request_id|epoch|10055|local_actor|local_sector|sector_macro`. Both handles are
strictly local and must never cross the network. The MD phase is advanced when
this event is raised, before external FFI checks. The owner must validate the
correlation, local FFI actor/sector relationship and finite sector-space
position, guarded pause/game time and bounded position tolerance before it
issues the identical Create as a replay. After that `Created`, a second
correlated inspection and FFI check is mandatory. The phases are 0→1→2→3→4;
foreign, premature, extra or late events fault the experiment. The owner must
permanently discard on missing, invalid, late, or failed FFI checks, even though
MD has advanced its phase. Completion and TCP ACK require a subsequent guarded
update and final process/log/callback fencing; MD results alone are provisional.

This tests creation of an approximate individual counterpart. The seed,
loadout, orientation, velocity, pilot, orders, equipment, cargo and health are
not recovered from the source. Client AI and autonomous spawns are not
reconciled, a similarly described client ship is neither proof of a duplicate
nor eligible for automatic adoption, and the witness does not prove equivalent
coordinate frames or collision clearance. Background source simulation and
queue coverage remain bounded by the census experiment. No shared gameplay,
Windows or Internet support, persistent world, or complete synchronization is
shown. Native X4 execution of these new scripts remains necessary; synthetic
structural tests and schema validation cannot establish expression semantics.
