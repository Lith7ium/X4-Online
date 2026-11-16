# Private running local Multi-Create experiment

This separate default-off diagnostic reuses the isolated single-X4 supervisor,
pinned census checkpoint, saved witness inventory, correlated receiver/client,
and owned-process, protected-file, marker and cleanup guards of
[the paused experiment](AUTHORITY-MULTI-CREATE-LIVE.md). After the normal load
and an observed pause it requests `Unpause()` once, waits until the game reports
unpaused and game time has advanced, and dispatches one synthetic Create. The
running inspector is armed before dispatch; it requires further game-time
advance before its separately correlated MD Inspect response is accepted. The
owner checks for a later game-time advance after the create result before
reporting completion. Pause, time regression, foreign/late events, missing
progress or timeout fence the experiment. Checks are sampled, not proof of
uninterrupted running between samples. A no-progress response in the same tick
is conservatively refused; no automatic retry follows an uncertain mutation.

The source macro and faction are `ship_gen_m_tugboat_01_a_macro` and `pioneers`;
the seed 7183, local coordinates `(-400, 100000, 500)` and level-1 loadout are
artificial. The inspector compares against that requested position within two
metres. The created actor can move during a running simulation, so a refused
inspection may reflect normal motion; it is not proof that running creation is
impossible. Collision clearance is not established. This experiment does not
receive a server event or communicate with a second client; it cannot establish
universe coverage, cross-process frames, Windows, WAN, gameplay or persistence.

Before the native experiment the existing client and running inspector were
exercised together with the owner against a fake local C ABI. Only a fresh
private output and private display may be used for a future deliberate run;
the normal save/profile must remain untouched.

## Bounded native observation, 2026-11-16

One private Linux X4 run, `.local/authority-multi-create-running-01`, reported
`success: true` and no remaining owned processes. The engine log records the
load request, marker inspection and observed pause, followed by `RUNNING`
with game times 3.037 and 3.045304872, a create receipt for index 10055 in
`cluster_01_sector001_macro` at 3.09220202, and `DONE` at 3.595982207.

The owner code emits `RUNNING` after the unpause request, a reported unpaused
state and advancing game time. It emits the create row only after correlated
MD responses and the running FFI inspector accept the object; the individual
MD/FFI observations are not independently logged. Completion additionally
requires a later game-time sample greater than the create sample. These sampled
values do not prove uninterrupted running between observations, exact loaded
file identity or the absence of unrelated errors in the whole game log.

This was one synthetic local creation, with the artificial seed, coordinates
and loadout above. It is not an actual server-originated NPC event or a test of
TCP delivery, multiple clients, Windows, Internet, gameplay, persistence, full
ship state, cross-process coordinate frames or complete universe coverage.

