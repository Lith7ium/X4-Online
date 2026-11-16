# Disposable one-ship control probe

This default-off MD/Lua component is a bounded experiment, not an installed
feature or a multiplayer client. Importing it installs no callback or update
loop. It must be invoked by a single existing private X4 load/update owner after
that owner has observed a verified marked checkpoint and pause. The entire
private save directory must remain read-only; the normal profile is untouched.
No Save or saved-fixture bridge is used.

A fresh epoch/attempt binds the one-shot MD state. In a custom-creative test
world, Create first verifies the saved healthy sector/registry references, then
creates one player-owned ship in saved sector 1 with `safepos`. It does not ask
whether a pilot or slot is empty. The cue records pending before creation; a
partial failure is never retried and the private world must be discarded.
The fixture does not prove collision clearance. A correlated Read 0 compares
`player.ship`, `player.occupiedship`, `player.controlled` and `player.sector`
to that local fixture before the next single-use action. Exactly one Teleport
then requests `control=true instant=true force=true`, after validating the same
fixture and registry references and setting attempted/pending. `force` skips
research restrictions; it does not force control of an occupied position.
The Dispatched event only says the cue reached the request.

The caller invokes one tick at a time and routes exactly one Created,
Dispatched, ReadResult or Refused event to the module. Request ID, epoch,
fixture and sector are checked on each response; the MD cue itself enforces
Read 0, Teleport, Read 1, Read 2. On both post-transition reads, MD must report
the fixture as player ship, occupied ship and controlled object in its target
sector, and owned by `faction.player`. Lua independently validates the same
local uint64 fixture, sector, player container/ship contexts, occupied- and
controlled-ship getters, docking state and UI owner against the MD owner ID.
Two fully matching readings on separate ticks are required for `controlled`.
The local callback contains process-specific actor IDs only internally; they
must not be logged, sent to other processes, or reused as portable identities.
No conclusion about seat freedom or ability to fly is drawn.

Before the teleport request, the supplied `pre_guard` must enforce the original
saved-fixture/player context. Immediately before dispatch the component crosses
an explicit phase boundary and establishes a new paused game-time baseline;
`post_guard` must fence the permitted transition from the old player context to
the target, with no arbitrary third player/ship/sector admitted. Do not assume
the original NPC remains operational after the attention/sector transition.
The module itself checks profile path, player validity, pause, clock,
fixture/sector validity, getter results and stable observed owner on both sides.
An owning supervisor must separately fence Steam identity, exact process,
protected files and source checkpoint, overall deadline, live callbacks, signal
handling, and cleanup through the final observation and process stop. These
are point-in-time checks, not atomic locks. FFI player-container-to-ship mapping,
owner getter and whether instant teleport finishes while paused are not yet
validated for this case.

A tick at deadline returns `inconclusive`; a result already being inspected
that crosses the deadline is also inconclusive, never controlled. A newly
arriving late or duplicate event faults; there is no automatic retry of Create
or Teleport. An incomplete but valid post-read is inconclusive, not proof that
control is impossible. A getter/guard error, a late event, state mismatch, lost
pause or player/fixture identity change faults and requires discarding the
world. The caller must continue watching callbacks through cleanup. The current
component is not a native harness; it has synthetic and fake-FFI evidence only.
It cannot establish network propagation, movement/input, two players, Windows,
Internet, shared economy, combat or a persistent multiplayer session.
