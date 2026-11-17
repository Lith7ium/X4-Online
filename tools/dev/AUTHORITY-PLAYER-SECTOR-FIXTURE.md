# Two-sector player-ship fixture (preparation only)

These files prepare an opt-in diagnostic for two explicitly created Company ships in the two sectors already held by `X4AuthoritySectorReferenceFixture.State`. The fixture alone does not install itself or assign seats; the separate runner below can request a disposable test save. The one-shot `Create` event requires `player.module == 'custom_creative'`, the matching saved epoch and two distinct sector references. This game-start guard does not establish an isolated profile; the caller must provide one. It creates two small Argon fighter hulls with owner `faction.player`, omits pilot creation, and requests `create_ship/safepos` with plot-box avoidance. The cue checks owner, macro, sector, operational state, empty pilot reference, and that neither object is the active player ship, docked or internally stored. The two ship and sector references and the fault/pending state are saved in the cue. If any step fails, creation is not retried: a partial object can remain, so discard the isolated test world.

`authority_player_sector_evidence.verify` checks a saved marker, exact cue fields and saved epoch, unique saved component references, small-ship macro and player owner, and sector ancestry with a zone parent and `connection="space"`. It relies on the caller to supply a confirmed, exclusively fenced checkpoint and expected epoch/marker. The marker parser checks the compressed bytes against checkpoint SHA and size; neither this verification nor an MD reference proves which bytes X4 loaded. The cue serialization was subsequently observed in the native fixture-save run described below. Unknown formats fail closed.

`authority_player_fixture_marker.xml` is a separate test script named `X4AuthorityPlayerFixtureMarker`; the archived one-shot `X4AuthorityCheckpointMarker.Store` must remain intact. The fixture evidence checker requires the new script's `MarkerState`, not the archived marker. `PlayerFixtureBridge` prepares the normal published-checkpoint identity and native receipt checks with the new marker and saved-fixture verification before confirmation. Its ordinary `save()` deliberately refuses: no validated live fixture-readback gate exists yet. The distinct, explicitly enabled `save_fixture_experiment()` can request one save for serialization research in a disposable world; a native receipt is not a verified checkpoint. If dispatch is uncertain, the bridge is fenced and the save cannot be retried. `checkpoint_published()` still requires the saved marker, identity, two fixture references, ownership and sector ancestry to pass before native confirmation; it does not prove seat availability or collision safety.

`authority_player_fixture_save_live.py` is an opt-in Linux research runner that combines the archived, verified two-sector source with the fixture, its distinct marker and the existing local control bridge. It stages a private copy in `save_008` and saves the paused test world into a separate `save_009` in the disposable profile. The loader owns the only update callback. After ordered preflight and creation receipts, the supervisor checks the bridge's UDP peer against the owned X4 process, dispatches one save, publishes the file, checks its marker and fixture references, and only then confirms the checkpoint. Input, configuration and process guards are sampled around operations; an unsuccessful or interrupted attempt does not establish whether X4 wrote a save. An already visible checkpoint or confirmation pointer after an error is not a successful experiment.

The runner has synthetic coverage and one native Linux result described below. `checkpoint_requested` and `save_attempted` mean the bridge save call began; they do not prove delivery to X4. `confirmation_attempted` records a call to the checkpoint store, and `checkpoint_confirmation_uncertain` records an exception that may have occurred after a visible pointer replacement. Later experiments must require this runner's successful final `result.json` as well as independent checkpoint revalidation; the pointer alone is insufficient. Fixture creation reports two returned references, not a complete universe census. The two new ships are **not enrolled in the server ship registry** by this experiment. A confirmed fixture checkpoint demonstrates only the checks on saved bytes and the native confirmation protocol; it does not prove seat availability, collision safety, loaded-byte identity, player control or multiplayer. Never load or save a normal X4 profile.

## Native fixture-save result

One isolated Linux X4 run in `.local/private-fixture-scope-real-20261117-03/`
reported the ordered preflight and creation of two player-owned test ships,
followed by one save attempt and confirmed checkpoint. The retained game log
records both fixture-creation entries and the `CREATED` receipt. The runner
reports that the saved marker, two component references, ownership, class and
distinct sector ancestry were verified, and its final result reports no owned
processes remaining. The private display and user scope reported successful
cleanup; the Steam process identity remained unchanged. The archived source
fingerprints were checked by the runner.

A separate read-only verification of the confirmed checkpoint reported the
same two saved slots, ownership, class and sector ancestry. The checkpoint ID
is `checkpoint-a3cf97a14b394b408d34513e3658c9ab`, with SHA-256
`86795a48053de8f05a4467ba1286479eef116a1e4ba170f227ea98d8b6f72556`.
This is one serialisation test, not a registry enrollment, seat assignment,
flight or multiplayer test. The retained logs do not prove exact file
consumption or uninterrupted pause.

The cue emits its local parent, local position, hull and pilot values for later inspection. They are not yet parsed into finite sector-relative coordinates or a verified hull/collision baseline. `safepos` is the engine's position search, not a proof of complete collision clearance, absence of later collisions or safe operation. No assumption is made about zone-to-sector transformations or the completeness of collision detection. The schema accepts the XML but does not execute its expressions or establish the meaning of an empty pilot in a running X4 instance. Before any use as a control-test checkpoint, an isolated native harness must check those facts, preserve the actual parent/frame, verify positions and hull and abort on missing, ambiguous, damaged or visibly unsafe observations. This preparation makes no claim about runtime behavior, autonomous movement, a seat being usable, server authority, networking or gameplay.

Research in the installed game's scripts identified `GetComponentData(ship, 'assignedpilot')` as an assignment observation and the MD properties `ship.controlpostslot.{controlpost.aipilot}` and `slot.component.slotactor.{slot}` as a control-post reservation observation. See [the local research](AUTHORITY-PLAYER-PILOT-RESEARCH.md). A future probe must verify that the slot and component exist and independently calibrate both readings against a known piloted NPC and the unpiloted test ships. An absent assigned pilot and an unreserved slot do not by themselves establish physical seat availability or successful player control. Suppressed MD errors cannot be treated as an empty seat.

The repository development check after adding this runner, before selecting the
historical registry for the archive, ran 4,694 tests with no test failures and
56 skips. It remains incomplete under the repository's check policy. The private
log is `.local/check-player-fixture-save-final-20261117.log`.

## Native saved-seat reloads

Two separate, isolated Linux X4 runs loaded a private copy of the confirmed
fixture checkpoint above. In the first run the recovery owner selected saved
slot 1; in the second it selected slot 2. Each game log recorded the fixture
marker after load, a paused recovery, the saved-target request, the local
teleport action, two guarded player-control observations, and the final
`FENCED` receipt. The runner reports successful local control for the requested
slot and no owned X4 processes remaining. The outer scope reports cleanup,
private display release, and unchanged Steam identity in both runs. Results:
`.local/private-seat-scope-real-20261117-01/` and
`.local/private-seat-scope-real-20261117-02/`.

The two runs used the same checkpoint in separate processes and did not run
simultaneously. They do not prove exact bytes consumed by X4, uninterrupted
pause, free-seat calibration, flight, input, registry enrollment, networking,
or multiplayer. Both new MD cues (`authority_saved_player_control.xml` and
`authority_player_registry_read.xml`) separately passed the stock MD schema in
one local schema compilation; schema validation does not execute expressions.
