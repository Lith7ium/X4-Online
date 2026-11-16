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
an explicit phase boundary and establishes a new paused game-time baseline, which must equal the previously observed paused time;
`post_guard` must fence the permitted transition from the old player context to
the target, with no arbitrary third player/ship/sector admitted. Do not assume
the original NPC remains operational after the attention/sector transition.
The module itself checks profile path, player validity, pause, clock,
fixture/sector validity, getter results and stable observed owner on both sides.
An owning supervisor must separately fence Steam identity, exact process,
protected files and source checkpoint, overall deadline, live callbacks, signal
handling, and cleanup through the final observation and process stop. These
are point-in-time checks, not atomic locks. Native evidence for the
player-container-to-ship mapping, owner getter and instant teleport while paused
is limited to the single recorded case below.

A tick at deadline returns `inconclusive`; a result already being inspected
that crosses the deadline is also inconclusive, never controlled. A newly
arriving late or duplicate event faults; there is no automatic retry of Create
or Teleport. An incomplete but valid post-read is inconclusive, not proof that
control is impossible. A getter/guard error, a late event, state mismatch, lost
pause or player/fixture identity change faults and requires discarding the
world. The caller must continue watching callbacks through cleanup. The component
itself is not a native harness; the separate supervisor and bounded native
observation are described below.
It cannot establish network propagation, movement/input, two players, Windows,
Internet, shared economy, combat or a persistent multiplayer session.

## Private native supervisor

`authority_player_control_live.py` is the separate opt-in single-process runner.
It reuses the guarded marked-load path, pins the source checkpoint, installs the
one-shot MD and Lua files in the private protected overlay, and mounts the whole
private save directory read-only. Its existing load callback is the sole update
owner. The original NPC/sector and player context are checked live through the
pre-teleport phase; at dispatch the owner crosses an explicit phase boundary.
The target stays live and in its original sector, the player context may only
move between the captured old context and the target (with temporarily absent
controlled/occupied IDs), and after the first positive read the target context
is locked. A post-transition paused game-time observation must equal the
pre-transition value; this does not establish continuous pause.

The final result distinguishes `controlled` from `inconclusive`. A completed
controlled result requires the ordered markers and two MD/UI readbacks after
the single dispatch, followed by final process, log, protected-file and source
checks. `success` means only that this bounded diagnostic completed; an
inconclusive result is not control. A fault, late event or cleanup failure
suppresses the control claim. For safety the owner requires
`GetPlayerContainerID()` itself to equal the target after the first positive
read; a different valid native container representation would cause a
conservative failure. Correspondence in other contexts and real gameplay remain
unproven.

## First native attempt and diagnostic fences

The isolated Linux run `.local/authority-player-control-01` observed the
expected marked load, pause, fixture creation and before-control read, then
failed before any `DISPATCH` marker. The X4 engine log reported
`Error while parsing expression: Maximum operator nesting level reached` for
the Teleport guard while loading. Its effect on the later generic fault is not
established, and the absence of `DISPATCH` does not establish whether the local
UI request or MD action was attempted. `success=false`, no checkpoint was
requested, and the supervisor reported no remaining owned processes.

The MD conditions are now decomposed into shorter nested guards while retaining
the same checks; XML schema validity alone does not validate X4 expression
execution. The Lua owner logs fixed `INTENT_TELEPORT` before calling the local
UI dispatch function and `LOCAL_CALL_RETURNED` when that function returns. The
MD cue logs fixed `ACTION_BEGIN` and `ACTION_RETURNED` around its action.
These markers identify execution points only: none is proof of delivery,
completion, a seat change or player control. Engine expression-parsing/nesting
errors and malformed, duplicate, late or missing required markers fail the
live and final-log validation.

The supervisor's external log polling is asynchronous with the X4 update owner:
it cannot guarantee detecting an engine parsing error before that owner issues
Create or Teleport. A separate explicit arm handshake would be required for a
pre-mutation log check, with additional analysis of log visibility and process
fencing; this harness does not implement such a handshake. The copied private
world remains disposable if any error is detected.

## Second native attempt

The isolated Linux run `.local/authority-player-control-02` completed the
bounded diagnostic with `outcome=controlled` and `local_control_proven=true`.
The engine log records the expected marker and paused slot-2 read, followed by
`START`, `CREATED`, `BEFORE`, `INTENT_TELEPORT`, `LOCAL_CALL_RETURNED`, MD
`ACTION_BEGIN`, MD `ACTION_RETURNED`, `DISPATCH`, `FIRST`, `CONTROLLED` and
`DONE` in that order. The reviewed state machine emits `FIRST` only after the
first post-teleport MD/UI context comparison and `CONTROLLED` after a second
matching comparison on a subsequent tick. This establishes those guarded,
paused local readbacks for this one disposable player-owned fixture; it does
not establish movement, player input, an independently free seat, another
client, or multiplayer. The action markers alone are not control proof.

The log does not contain the earlier expression parsing/nesting error. It does
contain startup errors including failed writes to a read-only `config.xml`, so
it is not an error-free engine log. Source and private staged save each hash to
`2c6494308424fffe8bd114bd017802e2b6dc1f227a64998aea8a787672846748`;
the private control MD and two Lua files match their reviewed source bytes.
The result reports no checkpoint request and no remaining owned processes.
These file, pause and process observations are sampled checks, not proof of
byte-exact engine loading or uninterrupted pause. The copied world was not
retained as a confirmed multiplayer state.
