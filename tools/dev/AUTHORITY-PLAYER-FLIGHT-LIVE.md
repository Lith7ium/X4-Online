# Private passive player-flight observation

This opt-in Linux diagnostic extends the disposable player-control experiment
in the same private X4 process. It makes no keyboard, mouse or other input;
it does not save, modify a ship's pose or velocity, or provide multiplayer.
Importing the runner has no effect. Its source archive, copied checkpoint,
read-only save directory, protected scripts and profile, process identities,
Steam identity, deadlines, signal handling, final log and owned-process cleanup
use the existing sector-read supervisor. The original control runner is not
changed, and the staging hooks are restricted to this private test overlay.

After two successful guarded player-control readbacks, the control owner
performs a single guarded in-process handoff of the exact local ship and sector.
Its paused NPC/player context is a completed precondition; it is not used as a
running-world guard. Its existing event handlers remain installed and their
errors still invalidate the whole run. A direct zone parent is read and checked
locally. The flight observer verifies the player container, occupied ship,
controlled ship, sector, zone and owner before and after each read. The direct
container/zone assumptions may cause an inconclusive native failure if X4 uses
another representation. No local identifiers are written to results.

The owner arms while paused, records a guarded transition, calls `Unpause()`
once, and requires observed game-time advancement. It collects three ordered
pose/time samples under the same update owner. The labels identify sequence only;
no control input is sent or inferred. The observer and external process/log
fences remain active until the process is stopped. No retry occurs after an
uncertain dispatch. A timeout or error does not establish the final game state.
The in-process external-guard callback is deliberately a no-op: the Lua observer
checks its own profile and player/ship identities, while the supervisor checks
process identity and protected files independently at polling points. They are
not one atomic check. The supervisor waits for `FENCED`, emitted only after the
guard immediately following `DONE` has returned. Later fault logs are rejected
if captured, but `FENCED` is a point observation, not continuous monitoring.
The existing initial sector-read guard retains its separate 30-second deadline;
this continuation also has its own deadline capped at 120 seconds. Timeouts and
identity checks around external calls are point observations, not preemption or
continuous monitoring.

`success=true` means that this particular diagnostic and its cleanup checks
completed; when the control test is inconclusive the output explicitly says no
flight observation was completed. Three samples and advancing game time do not
establish movement, successful steering, a cause of movement, seat freedom,
Windows/Internet behavior or shared gameplay. Numeric pose and rotation units
and axis/frame semantics are not established by this experiment. Changes in
the environment remain possible when the private simulation runs. Offline
tests alone do not establish native behavior.

## Native passive observation

In `.local/authority-player-flight-01`, one disposable Linux X4 process loaded
the recorded marked checkpoint, created a temporary player-owned fixture, and
reported two matching guarded local player-control readbacks while paused. After
the controlled handoff and resume, the recorded game time advanced from 3.014
while paused to 3.022316832 at the running observation. Three subsequent samples
at game times 3.044578554, 3.084173631 and 3.119517522 all reported the same
position `(145.78358459472656, 99490.2265625, 1155.231201171875)` and rotation
`(0, 0, -0)`. The first and last samples span about 0.075 seconds of game time.
The ordered log includes `DONE` followed by `FENCED`, and the result reports
successful diagnostic completion with no owned processes remaining. The staged
save and source hash matched the expected checkpoint under the runner's checks.

This was a passive, short, local observation with no injected input and no
requested save. The three equal samples do not prove continuous stillness or
steering. The checkpoint marker and staging checks do not prove exact bytes
consumed by the engine, and the guarded reads do not prove continuous control
or an atomic world snapshot. Movement, multiplayer, Windows and Internet
operation remain untested by this run.
