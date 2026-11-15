# Internal plan: local player control in two sectors

This is a proposed diagnostic, not an architecture decision or an implemented
multiplayer feature. Its immediate question is whether two isolated Linux X4
instances can each take and operate a different player-owned ship in a different
sector, starting from the same saved world. It does not require the instances'
worlds to remain synchronized.

## Evidence and prerequisites

The existing Linux lockstep work observed bounded synthetic keyboard and mouse
input, player-body motion and replay between two isolated processes. It is not
a standalone authoritative client; its 1,800-frame run failed overall world
agreement, and a longer independent-input run also failed. See
`docs/LINUX-VALIDATION.md`. Historical Windows lockstep tests established one
cooperative player-faction ship setup across three instances but did not fly
slots 2 and 3 in that test (`reports/LOCKSTEP-PLAYER-IDENTITY-20261029.txt`).
These observations do not establish this proposed experiment.

The local X4 schema documents `teleport_player` with `control=true` as taking
control **if free**. `force=true` bypasses research restrictions; it does not
establish that a pilot position is free or control was obtained. The existing
`tools/dev/native_gate_pilot_respawn.xml` uses this action for a newly created
slot-1 ship without an AI pilot in a respawn scenario. Neither its use on this
checkpoint nor cross-sector seat selection is proven by that example.

## Spawn-position evidence and limits

The local X4 9.00 `preparation/game-schemas/libraries/common.xsd` documents
`create_ship` with a `safepos` child (around line 25029). Its position search
radius defaults to the created object's radius when omitted (around line 7488);
`includeplotbox` can request avoidance of station plot boxes, and dangerous
regions are not ignored by default. `tools/dev/native_gate_session_start.py`
already constructs an optional `safepos` for a disposable saved start. These are
schema and existing-code evidence, not a native result for this test.

The same schema documents `get_safe_pos` for sector- or zone-relative output
and optional space reservations (around line 29096). A zone takes precedence
over a sector when both are supplied. The local base-game archive `08.cat` /
`08.dat` contains `aiscripts/move.seekenemies.xml`, where an existing ship uses
`get_safe_pos` and a reservation, and `aiscripts/move.buildership.xml`, where a
build-location check follows a safe-position search. These are vanilla usage
examples, not proof of our proposed spawn's complete geometry clearance.
Reservations must be cancelled and coordinate frames checked; they are
respected by participating position searches, not an atomic exclusion of all
other movement or physics.

The separately documented `check_is_area_obstructed` is ship-specific and
explicitly excludes certain mass traffic and ships with collision avoidance
disabled. `check_is_build_location_free` accounts for objects including
stations, gates and highways but explicitly ignores ships and asteroids. A
radius-based object search, either check alone, or their combination has not
been shown to cover every moving, streamed or collidable object. An observed
successful spawn, unchanged hull and absence of visible collision are bounded
observations; hidden geometry, concurrent movement and later collisions remain
unproven. Unknown or visibly unsafe results stop the experiment rather than
being labeled safe.

## Bounded sequence

1. Create a fresh disposable marked checkpoint containing two explicitly
   identified operational ships owned by `faction.player`, with free pilot
   positions and saved MD references, in two distinct saved sectors. Use the
   game's `<create_ship><safepos .../></create_ship>` search rather than
   asserting that an arbitrary fixed coordinate is clear. Record the actual
   resulting position and space, finite pose, hull and relevant collision or
   damage observations before the save. Persist the references and use a
   structured checkpoint parser to verify marker, ship classes and owners,
   distinct slots and sector ancestry. Missing, ambiguous, docked or stored
   fixtures, invalid positions, visible collisions, damage, or unexpected
   movement abort the test; none of these checks proves complete clearance.
2. Stage the verified checkpoint read-only into two separate disposable
   profiles and launch owned X4 processes using the pinned executable and
   bounded, gated lifecycle. Observe each load request, expected marker and
   pause. While paused, issue one serialized, correlated seat request per
   profile for its assigned saved ship. After the action, independently confirm
   the MD saved reference, owner, `player.ship`, `player.occupiedship`, local
   `GetPlayerOccupiedShipID` / `GetPlayerControlledShipID`, and the matching
   local `GetContextByClass(..., 'sector', false)` result. A cue receipt is not
   proof of a successful seat change. Treat every local handle as process-local.
3. Run both instances concurrently. Record a neutral interval, send a short
   controlled direction input only to the verified first window, release it,
   observe another neutral interval, then stimulate only the second window with
   a distinguishable input. Capture ordered per-process input observations,
   game times, positions and orientations before, during and after. Record
   baseline drift and inertia; an injector success code or a changed pose alone
   does not prove that the intended input reached the intended player. Recheck
   seat, ship, sector, process and focus identity at each boundary. Refuse on
   missing input evidence, lost focus, unexpected transition, timeout, malformed
   values or unconfirmed cleanup.

The minimum harness needs a narrowly scoped fixture and seat cue, a separate
saved-reference/ancestry verifier, a correlated local player readback probe,
and a supervisor based on `authority_two_x4_live.py`,
`authority_sector_read_live.py`, and `linux_snapshot_capture.py`. Their checks
must be retained, including source/output separation, read-only protected files,
process identity, Steam identity, deadlines, signal fencing and owned-process
cleanup. `authority_fixture_warp_probe.lua` contains relevant local getters,
but intentionally excludes player ships and cannot be reused unchanged as a
player writer or guard. The old Linux keyboard evidence tools are gate-bound;
a standalone, bounded input/window observer is still needed. Past input tests
encountered focus loss, layout differences and a temporary device closing too
soon. Keep the test input device alive until its helper and both owned game
processes are safely stopped; retain the lock if cleanup is uncertain.

A passing result would cover local seat assignment and bounded, measured input
for these two fixtures only. It would not prove server ownership or propagation
of player movement, a shared evolving universe, high-attention arbitration,
velocity smoothing, sector transitions, collision safety after movement,
reconnection, Windows, Internet, real player controls, combat, trade, boarding,
or gameplay. A separate test is needed for each of those boundaries.
